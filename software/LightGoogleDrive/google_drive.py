import random
from typing import Dict, List, Any
from pathlib import Path
import re
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

_TEXT_MIMES = {
    "text/markdown", "text/plain", "application/json",
    "application/xml", "text/xml", "text/yaml", "application/yaml",
    "text/csv",
}


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


class GoogleDriveSession:
    """Deterministic sandbox for the Google Drive mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "google_drive.yaml") as f:
                info = yaml.safe_load(f)

            self.about: Dict[str, Any] = info.get("about", {})
            self.files: List[Dict[str, Any]] = [
                {
                    **{k: v for k, v in r.items()},
                    "size": int(r.get("size") or 0),
                    "starred": _to_bool(r.get("starred", False)),
                    "trashed": _to_bool(r.get("trashed", False)),
                    "parent_id": (str(r.get("parent_id") or "") or None),
                }
                for r in info.get("files", [])
            ]
            self.permissions: List[Dict[str, Any]] = list(info.get("permissions", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGoogleDrive')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"files": self.files, "permissions": self.permissions}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=10))

    def _serialize_file(self, f):
        return {
            "kind": "drive#file",
            "id": f["id"],
            "name": f["name"],
            "mimeType": f["mime_type"],
            "parents": [f["parent_id"]] if f["parent_id"] else [],
            "size": str(f["size"]) if f["size"] else "0",
            "createdTime": f["created_time"],
            "modifiedTime": f["modified_time"],
            "owners": [{"emailAddress": f["owner_email"]}],
            "starred": f["starred"],
            "trashed": f["trashed"],
            "webViewLink": f.get("web_view_link") or None,
        }

    _Q_TOKEN = re.compile(r"(\w+)\s*=\s*'([^']*)'")

    def _matches_query(self, file, q):
        if not q:
            return True
        clauses = [c.strip() for c in q.split(" and ")]
        for clause in clauses:
            if not clause:
                continue
            if clause == "trashed = false":
                if file["trashed"]:
                    return False
                continue
            if clause == "trashed = true":
                if not file["trashed"]:
                    return False
                continue
            if clause == "starred = true":
                if not file["starred"]:
                    return False
                continue
            m = self._Q_TOKEN.match(clause)
            if m:
                key, val = m.group(1), m.group(2)
                if key == "mimeType" and file["mime_type"] != val:
                    return False
                if key == "name" and file["name"] != val:
                    return False
                continue
            m_in = re.match(r"'([^']*)'\s+in\s+parents", clause)
            if m_in:
                if file["parent_id"] != m_in.group(1):
                    return False
                continue
            m_contains = re.match(r"name\s+contains\s+'([^']*)'", clause)
            if m_contains:
                if m_contains.group(1).lower() not in file["name"].lower():
                    return False
                continue
        return True

    # --- About -------------------------------------------------------------
    def get_about(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.about}

    # --- Files -------------------------------------------------------------
    def list_files(self, q: str = "", page_size: int = 100, page_token: str | None = None,
                   order_by: str = "modifiedTime desc") -> Dict[str, Any]:
        results = [f for f in self.files if self._matches_query(f, q)]
        if order_by:
            order_map = {
                "modifiedTime": "modified_time",
                "createdTime": "created_time",
                "name": "name",
            }
            field, _, direction = order_by.partition(" ")
            key = order_map.get(field, "modified_time")
            results.sort(key=lambda f: f[key], reverse=(direction.lower() == "desc"))
        try:
            offset = int(page_token or 0)
        except ValueError:
            offset = 0
        page = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < len(results) else None
        return {"status": "ok", "output": {
            "kind": "drive#fileList",
            "files": [self._serialize_file(f) for f in page],
            "nextPageToken": next_token,
        }}

    def get_file(self, file_id: str) -> Dict[str, Any]:
        for f in self.files:
            if f["id"] == file_id:
                return {"status": "ok", "output": self._serialize_file(f)}
        return {"status": "failed", "output": f"File {file_id} not found"}

    def download_file(self, file_id: str) -> Dict[str, Any]:
        row = next((f for f in self.files if f["id"] == file_id), None)
        if row is None:
            return {"status": "failed", "output": f"File {file_id} not found"}
        name = row["name"]
        mime_type = row.get("mime_type") or "application/octet-stream"
        if mime_type not in _TEXT_MIMES and mime_type != "application/pdf":
            return {"status": "failed", "output": f"Unsupported mime type {mime_type}"}
        blob = CORPUS_PATH / "file_blobs" / name
        if not blob.exists():
            return {"status": "failed", "output": f"File {file_id} not found"}
        try:
            text = blob.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {"status": "failed", "output": f"File {file_id} not found"}
        return {"status": "ok", "output": {
            "file_id": file_id,
            "name": name,
            "mime_type": mime_type,
            "size_bytes": len(text.encode("utf-8")),
            "content": text,
        }}

    def create_file(self, name: str, mime_type: str, parent_id: str | None = None,
                    owner_email: str = "amelia@orbit-labs.com", size: int = 0) -> Dict[str, Any]:
        if parent_id and not any(f["id"] == parent_id for f in self.files):
            return {"status": "failed", "output": f"Parent {parent_id} not found"}
        now = self._now()
        new_file = {
            "id": f"file-{self.uuid()}",
            "name": name,
            "mime_type": mime_type,
            "parent_id": parent_id,
            "size": int(size),
            "created_time": now,
            "modified_time": now,
            "owner_email": owner_email,
            "starred": False,
            "trashed": False,
            "web_view_link": "",
        }
        self.files.append(new_file)
        self.permissions.append({
            "id": f"perm-{self.uuid()[:6]}",
            "file_id": new_file["id"],
            "type": "user",
            "role": "owner",
            "email": owner_email,
            "display_name": owner_email,
        })
        return {"status": "ok", "output": self._serialize_file(new_file)}

    def update_file(self, file_id: str, name: str | None = None, parent_id: str | None = None,
                    starred: bool | None = None, trashed: bool | None = None) -> Dict[str, Any]:
        for f in self.files:
            if f["id"] == file_id:
                if name is not None:
                    f["name"] = name
                if parent_id is not None:
                    f["parent_id"] = parent_id
                if starred is not None:
                    f["starred"] = bool(starred)
                if trashed is not None:
                    f["trashed"] = bool(trashed)
                f["modified_time"] = self._now()
                return {"status": "ok", "output": self._serialize_file(f)}
        return {"status": "failed", "output": f"File {file_id} not found"}

    def trash_file(self, file_id: str) -> Dict[str, Any]:
        return self.update_file(file_id, trashed=True)

    def delete_file(self, file_id: str) -> Dict[str, Any]:
        for i, f in enumerate(self.files):
            if f["id"] == file_id:
                self.files.pop(i)
                self.permissions[:] = [p for p in self.permissions if p["file_id"] != file_id]
                return {"status": "ok", "output": {"deleted": True, "id": file_id}}
        return {"status": "failed", "output": f"File {file_id} not found"}

    # --- Permissions -------------------------------------------------------
    def list_permissions(self, file_id: str) -> Dict[str, Any]:
        if not any(f["id"] == file_id for f in self.files):
            return {"status": "failed", "output": f"File {file_id} not found"}
        perms = [p for p in self.permissions if p["file_id"] == file_id]
        return {"status": "ok", "output": {"kind": "drive#permissionList", "permissions": perms}}

    def create_permission(self, file_id: str, type: str, role: str,
                          email_address: str | None = None, display_name: str | None = None) -> Dict[str, Any]:
        if not any(f["id"] == file_id for f in self.files):
            return {"status": "failed", "output": f"File {file_id} not found"}
        perm = {
            "id": f"perm-{self.uuid()[:6]}",
            "file_id": file_id,
            "type": type,
            "role": role,
            "email": email_address or "",
            "display_name": display_name or email_address or "",
        }
        self.permissions.append(perm)
        return {"status": "ok", "output": perm}

    def delete_permission(self, file_id: str, permission_id: str) -> Dict[str, Any]:
        for i, p in enumerate(self.permissions):
            if p["id"] == permission_id and p["file_id"] == file_id:
                self.permissions.pop(i)
                return {"status": "ok", "output": {"deleted": True, "id": permission_id}}
        return {"status": "failed", "output": f"Permission {permission_id} not found on {file_id}"}


if __name__ == "__main__":
    s = GoogleDriveSession(seed=12)
    print(s.get_about())
    print(s.list_files(q="trashed = false"))
