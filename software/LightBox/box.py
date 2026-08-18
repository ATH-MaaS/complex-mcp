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


def _to_int(v) -> int:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return 0
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


_DOWNLOAD_TEXT_MIMES = (
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "text/yaml",
    "text/csv",
    "application/csv",
)
_DOWNLOAD_PDF_MIME = "application/pdf"
_DOWNLOAD_MAX_TEXT_BYTES_DEFAULT = 30_000_000
_DOWNLOAD_EXT_MIMES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".pdf": "application/pdf",
}


def _is_downloadable_text_mime(mime: str) -> bool:
    m = (mime or "").split(";", 1)[0].strip().lower()
    if not m:
        return False
    if m.startswith("text/"):
        return True
    return m in _DOWNLOAD_TEXT_MIMES


def _guess_download_mime(name: str) -> str:
    import mimetypes
    ext = Path(name).suffix.lower()
    if ext in _DOWNLOAD_EXT_MIMES:
        return _DOWNLOAD_EXT_MIMES[ext]
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"


# The user whose token is used (the "me" of /2.0/users/me).
_ME = "11446498"


class BoxSession:
    """Deterministic sandbox for the Box mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "box.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "login": r["login"],
                    "role": r["role"],
                    "status": r["status"],
                    "language": r["language"],
                    "timezone": r["timezone"],
                    "space_amount": _to_int(r.get("space_amount", 0)),
                    "space_used": _to_int(r.get("space_used", 0)),
                    "max_upload_size": _to_int(r.get("max_upload_size", 0)),
                    "job_title": r["job_title"],
                    "phone": r["phone"],
                    "created_at": r["created_at"],
                }
                for r in info.get("users", [])
            ]
            self.folders: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "parent_id": r["parent_id"],
                    "owner_id": r["owner_id"],
                    "description": r["description"],
                    "created_at": r["created_at"],
                    "modified_at": r["modified_at"],
                    "item_count": _to_int(r.get("item_count", 0)),
                }
                for r in info.get("folders", [])
            ]
            self.files: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "parent_id": r["parent_id"],
                    "owner_id": r["owner_id"],
                    "description": r["description"],
                    "size": _to_int(r.get("size", 0)),
                    "extension": r["extension"],
                    "sha1": r["sha1"],
                    "created_at": r["created_at"],
                    "modified_at": r["modified_at"],
                }
                for r in info.get("files", [])
            ]
            self.file_blobs: Dict[str, str] = dict(info.get("file_blobs", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightBox')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"files": self.files}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=6))

    def _user_mini(self, user_id):
        u = next((x for x in self.users if x["id"] == user_id), None)
        if not u:
            return None
        return {"type": "user", "id": u["id"], "name": u["name"], "login": u["login"]}

    def _folder_mini(self, folder_id):
        f = next((x for x in self.folders if x["id"] == folder_id), None)
        if not f:
            return None
        return {"type": "folder", "id": f["id"], "name": f["name"]}

    def _serialize_user(self, u):
        return {
            "type": "user",
            "id": u["id"],
            "name": u["name"],
            "login": u["login"],
            "role": u["role"],
            "status": u["status"],
            "language": u["language"],
            "timezone": u["timezone"],
            "space_amount": u["space_amount"],
            "space_used": u["space_used"],
            "max_upload_size": u["max_upload_size"],
            "job_title": u["job_title"],
            "phone": u["phone"],
            "created_at": u["created_at"],
        }

    def _serialize_folder(self, f):
        return {
            "type": "folder",
            "id": f["id"],
            "name": f["name"],
            "description": f["description"],
            "size": sum(x["size"] for x in self.files if x["parent_id"] == f["id"]),
            "created_at": f["created_at"],
            "modified_at": f["modified_at"],
            "item_count": f["item_count"],
            "parent": self._folder_mini(f["parent_id"]) if f["parent_id"] else None,
            "owned_by": self._user_mini(f["owner_id"]),
        }

    def _serialize_file(self, f):
        return {
            "type": "file",
            "id": f["id"],
            "name": f["name"],
            "description": f["description"],
            "size": f["size"],
            "extension": f["extension"],
            "sha1": f["sha1"],
            "created_at": f["created_at"],
            "modified_at": f["modified_at"],
            "parent": self._folder_mini(f["parent_id"]),
            "owned_by": self._user_mini(f["owner_id"]),
        }

    def _extract_file_content_text(self, basename, mime_type, max_text_bytes=None):
        import os
        if max_text_bytes is None:
            env_v = os.environ.get("WCB_DOWNLOAD_MAX_BYTES", "").strip()
            try:
                max_text_bytes = int(env_v) if env_v else _DOWNLOAD_MAX_TEXT_BYTES_DEFAULT
            except ValueError:
                max_text_bytes = _DOWNLOAD_MAX_TEXT_BYTES_DEFAULT

        if (
            "/" in basename
            or "\\" in basename
            or basename in ("", ".", "..")
            or basename.startswith(".")
        ):
            return {"error": True, "message": f"basename {basename!r} is not a single safe path component"}

        mime = (mime_type or "").split(";", 1)[0].strip().lower()
        is_pdf = mime == _DOWNLOAD_PDF_MIME

        if not is_pdf and not _is_downloadable_text_mime(mime):
            return {"error": True, "message": (
                f"mime {mime!r} not supported; only text/*, "
                "application/json|xml|yaml|csv, and application/pdf are downloadable"
            )}

        if basename not in self.file_blobs:
            return {"error": True, "message": f"file_blob {basename!r} not found in corpus"}

        raw = self.file_blobs[basename]

        if is_pdf:
            try:
                from pypdf import PdfReader  # type: ignore
                import io
                reader = PdfReader(io.BytesIO(raw.encode("utf-8", errors="replace")))
                parts = []
                for idx, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text() or ""
                    parts.append(f"--- page {idx} ---\n{page_text}".rstrip())
                text = "\n\n".join(parts)
            except ImportError as exc:
                return {"error": True, "message": f"pypdf not installed in this container: {exc}"}
            except Exception as exc:
                return {"error": True, "message": f"could not parse PDF: {exc}"}
        else:
            text = raw

        size_bytes = len(text.encode("utf-8"))
        if size_bytes > max_text_bytes:
            return {"error": True, "message": (
                f"extracted text {size_bytes} bytes exceeds cap {max_text_bytes}"
            )}

        return {"error": False, "text": text}

    # --- API methods -------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        u = next((x for x in self.users if x["id"] == _ME), self.users[0])
        return {"status": "ok", "output": self._serialize_user(u)}

    def get_folder(self, folder_id: str) -> Dict[str, Any]:
        f = next((x for x in self.folders if x["id"] == str(folder_id)), None)
        if not f:
            return {"status": "failed", "output": f"Folder {folder_id} not found"}
        return {"status": "ok", "output": self._serialize_folder(f)}

    def get_folder_items(self, folder_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        if not any(x["id"] == str(folder_id) for x in self.folders):
            return {"status": "failed", "output": f"Folder {folder_id} not found"}
        folders = [self._serialize_folder(x) for x in self.folders
                   if x["parent_id"] == str(folder_id)]
        files = [self._serialize_file(x) for x in self.files
                 if x["parent_id"] == str(folder_id)]
        entries = folders + files
        total = len(entries)
        page = entries[offset:offset + limit]
        return {"status": "ok", "output": {
            "total_count": total,
            "entries": page,
            "offset": offset,
            "limit": limit,
        }}

    def get_file(self, file_id: str) -> Dict[str, Any]:
        f = next((x for x in self.files if x["id"] == str(file_id)), None)
        if not f:
            return {"status": "failed", "output": f"File {file_id} not found"}
        return {"status": "ok", "output": self._serialize_file(f)}

    def download_file(self, file_id: str) -> Dict[str, Any]:
        f = next((x for x in self.files if x["id"] == str(file_id)), None)
        if not f:
            return {"status": "failed", "output": f"File {file_id} not found"}
        name = f["name"]
        mime_type = _guess_download_mime(name)
        res = self._extract_file_content_text(name, mime_type)
        if res.get("error"):
            return {"status": "failed", "output": res["message"]}
        text = res["text"]
        return {"status": "ok", "output": {
            "file_id": str(file_id),
            "name": name,
            "mime_type": mime_type,
            "size_bytes": len(text.encode("utf-8")),
            "content": text,
        }}

    def search(self, query: str | None = None, type: str | None = None,
               limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        q = (query or "").lower()
        type_filter = type
        entries = []
        if type_filter in (None, "folder"):
            for f in self.folders:
                if q in f["name"].lower():
                    entries.append(self._serialize_folder(f))
        if type_filter in (None, "file"):
            for f in self.files:
                if q in f["name"].lower():
                    entries.append(self._serialize_file(f))
        total = len(entries)
        page = entries[offset:offset + limit]
        return {"status": "ok", "output": {
            "total_count": total,
            "entries": page,
            "offset": offset,
            "limit": limit,
        }}


if __name__ == "__main__":
    s = BoxSession(seed=12)
    print(s.get_me())
    print(s.get_folder("0"))
    print(s.search(query="a"))
