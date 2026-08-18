import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class DropboxSession:
    """Deterministic sandbox for the Dropbox API v2 mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "dropbox.yaml") as f:
                info = yaml.safe_load(f)

            acct = (info.get("account") or [{}])[0]
            self.account: Dict[str, Any] = self._coerce_account(acct)

            self.files: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "path_lower": r["path_lower"],
                    "path_display": r["path_display"],
                    "is_folder": _to_bool(r.get("is_folder", False)),
                    "size": _to_int(r.get("size", 0)),
                    "client_modified": r["client_modified"],
                    "rev": r["rev"],
                }
                for r in info.get("files", [])
            ]

            self.shared_links: List[Dict[str, Any]] = [
                {
                    "id": s["id"],
                    "url": s["url"],
                    "name": s["name"],
                    "path_lower": s["path_lower"],
                    "visibility": s["visibility"],
                    "file_id": s["file_id"],
                }
                for s in info.get("shared_links", [])
            ]

            # Extracted text for the download endpoint. Keyed by file basename.
            # PDF text is only present when the extractor (pypdf) was available at
            # corpus-build time; missing PDF text yields a pdf_extraction_unavailable
            # failure, mirroring the source service when pypdf is absent.
            self.file_blobs: Dict[str, str] = dict(info.get("file_blobs", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightDropbox')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"files": self.files}

    # allow-listed download mimes (mirrors _mutable_store.guess_download_mime table)
    _DOWNLOAD_EXT_MIMES = {
        ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown",
        ".json": "application/json", ".xml": "application/xml",
        ".yaml": "application/yaml", ".yml": "application/yaml",
        ".csv": "text/csv", ".pdf": "application/pdf",
    }

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=24))

    @staticmethod
    def _coerce_account(r) -> Dict[str, Any]:
        return {
            "account_id": r["account_id"],
            "name": {
                "given_name": r["name_given"],
                "surname": r["name_surname"],
                "display_name": r["name_display"],
                "familiar_name": r["name_given"],
                "abbreviated_name": (r["name_given"][:1] + r["name_surname"][:1]).upper(),
            },
            "email": r["email"],
            "email_verified": _to_bool(r.get("email_verified", False)),
            "country": r["country"],
            "locale": r["locale"],
            "account_type": {".tag": r["account_type"]},
            "is_paired": False,
            "disabled": False,
        }

    def _serialize_entry(self, f):
        if f["is_folder"]:
            return {
                ".tag": "folder",
                "id": f["id"],
                "name": f["name"],
                "path_lower": f["path_lower"],
                "path_display": f["path_display"],
            }
        return {
            ".tag": "file",
            "id": f["id"],
            "name": f["name"],
            "path_lower": f["path_lower"],
            "path_display": f["path_display"],
            "size": f["size"],
            "client_modified": f["client_modified"],
            "server_modified": f["client_modified"],
            "rev": f["rev"],
            "is_downloadable": True,
        }

    def _serialize_link(self, s):
        return {
            ".tag": "file",
            "id": s["id"],
            "url": s["url"],
            "name": s["name"],
            "path_lower": s["path_lower"],
            "link_permissions": {
                "resolved_visibility": {".tag": s["visibility"]},
                "can_revoke": True,
            },
        }

    def _norm_path(self, path):
        """Normalize a Dropbox path. Root is '' or '/'; everything else lower-cased."""
        if path in (None, "", "/"):
            return ""
        p = path.lower()
        if not p.startswith("/"):
            p = "/" + p
        return p.rstrip("/")

    # --- API methods -------------------------------------------------------
    def get_current_account(self) -> Dict[str, Any]:
        return {"status": "ok", "output": dict(self.account)}

    def list_folder(self, path: str = "", recursive: bool = False) -> Dict[str, Any]:
        parent = self._norm_path(path)
        entries = []
        for f in self.files:
            child = f["path_lower"]
            if child == parent:
                continue
            if recursive:
                if parent == "" or child.startswith(parent + "/"):
                    entries.append(f)
            else:
                head, _, _ = child.rpartition("/")
                if head == parent:
                    entries.append(f)
        return {"status": "ok", "output": {
            "entries": [self._serialize_entry(f) for f in entries],
            "cursor": "AAH4f99T0taONIb-mock-cursor",
            "has_more": False,
        }}

    def get_metadata(self, path: str | None = None) -> Dict[str, Any]:
        if not path:
            return {"status": "failed", "output": {"error_summary": "path/not_found/", "error": {".tag": "path"}}}
        target = self._norm_path(path)
        for f in self.files:
            if f["path_lower"] == target or f["id"] == path:
                return {"status": "ok", "output": self._serialize_entry(f)}
        return {"status": "failed", "output": {
            "error_summary": "path/not_found/",
            "error": {".tag": "path", "path": {".tag": "not_found"}},
        }}

    def search_v2(self, query: str | None = None, path: str = "") -> Dict[str, Any]:
        q = (query or "").lower()
        scope = self._norm_path(path)
        matches = []
        for f in self.files:
            if scope and not (f["path_lower"] == scope or f["path_lower"].startswith(scope + "/")):
                continue
            if q and q not in f["name"].lower():
                continue
            matches.append(f)
        return {"status": "ok", "output": {
            "matches": [
                {
                    "match_type": {".tag": "filename"},
                    "metadata": {".tag": "metadata", "metadata": self._serialize_entry(f)},
                }
                for f in matches
            ],
            "has_more": False,
        }}

    def download_file(self, path: str | None = None) -> Dict[str, Any]:
        if not path:
            return {"status": "failed", "output": {
                "error_summary": "bad_request/", "error": {".tag": "bad_request"},
                "message": "path is required"}}
        target = self._norm_path(path)
        row = next((f for f in self.files if f["path_lower"] == target or f["id"] == path), None)
        if row is None:
            return {"status": "failed", "output": {
                "error_summary": "not_found/", "error": {".tag": "not_found"},
                "message": f"path {path!r} not found"}}
        if row["is_folder"]:
            return {"status": "failed", "output": {
                "error_summary": "unsupported_mime/", "error": {".tag": "unsupported_mime"},
                "message": f"path {path!r} is a folder"}}
        name = row["name"]
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        mime_type = self._DOWNLOAD_EXT_MIMES.get(ext, "application/octet-stream")
        if mime_type == "application/octet-stream":
            return {"status": "failed", "output": {
                "error_summary": "unsupported_mime/", "error": {".tag": "unsupported_mime"},
                "message": f"mime for {name!r} not supported"}}
        text = self.file_blobs.get(name)
        if text is None:
            if mime_type == "application/pdf":
                return {"status": "failed", "output": {
                    "error_summary": "pdf_extraction_unavailable/",
                    "error": {".tag": "pdf_extraction_unavailable"},
                    "message": f"PDF text for {name!r} unavailable"}}
            return {"status": "failed", "output": {
                "error_summary": "not_found/", "error": {".tag": "not_found"},
                "message": f"content fixture for {name!r} not found"}}
        return {"status": "ok", "output": {
            "file_id": row["id"],
            "name": name,
            "path_display": row["path_display"],
            "mime_type": mime_type,
            "size_bytes": len(text.encode("utf-8")),
            "content": text,
        }}

    def list_shared_links(self, path: str | None = None) -> Dict[str, Any]:
        links = self.shared_links
        if path:
            target = self._norm_path(path)
            links = [s for s in links if s["path_lower"] == target]
        return {"status": "ok", "output": {
            "links": [self._serialize_link(s) for s in links],
            "has_more": False,
        }}


if __name__ == "__main__":
    s = DropboxSession(seed=12)
    print(s.get_current_account())
    print(s.list_folder())
