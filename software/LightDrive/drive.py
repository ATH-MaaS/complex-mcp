from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


TARGET_KINDS = ("file", "folder")

DEFAULT_FOLDERS = [
    {"fdid": "fd_root",      "name": "My Drive",  "parent_id": "", "path": "/"},
    {"fdid": "fd_documents", "name": "Documents", "parent_id": "fd_root", "path": "/Documents"},
    {"fdid": "fd_photos",    "name": "Photos",    "parent_id": "fd_root", "path": "/Photos"},
]

SEED_FILES = [
    ("resume.pdf",     "fd_documents",  184320,  "application/pdf",         -10, False, False),
    ("notes.txt",      "fd_documents",    4096,  "text/plain",              -20, True,  False),
    ("photo1.jpg",     "fd_photos",    2097152,  "image/jpeg",              -30, False, False),
    ("photo2.jpg",     "fd_photos",    3145728,  "image/jpeg",              -25, False, False),
    ("budget.xlsx",    "fd_root",        65536,  "application/vnd.ms-excel", -5, False, False),
    ("old_draft.docx", "fd_root",        20480,  "application/msword",       -3, False, True),
]

SEED_VERSIONS = [
    (0, 1, 100000, -20, "initial upload"),
    (0, 2, 184320, -10, "final revisions"),
    (4, 1,  40000, -8,  "first pass"),
    (4, 2,  65536, -5,  "added Q1 numbers"),
]

SEED_SHARE_LINKS = [
    ("file",   0, True,  10, 5),
    ("folder", "fd_photos", False, 30, 12),
]


@dataclass
class Folder:
    fdid: str
    name: str
    parent_id: str
    path: str
    created_at: str = ""


@dataclass
class File:
    fid: str
    name: str
    folder_id: str
    path: str
    size_bytes: int
    mime_type: str
    created_at: str
    updated_at: str
    is_starred: bool = False
    is_trashed: bool = False
    current_version_id: str = ""


@dataclass
class Version:
    vid: str
    file_id: str
    version_number: int
    size_bytes: int
    created_at: str
    comment: str = ""


@dataclass
class ShareLink:
    slid: str
    target_kind: str
    target_id: str
    url: str
    can_edit: bool
    expires_at: str
    view_count: int = 0


class DriveSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"],
            ) if os_cfg else DummyOSConnector()
            self._today = datetime(2026, 1, 5)
            self.folders: Dict[str, Folder] = {}
            self.files: Dict[str, File] = {}
            self.versions: Dict[str, Version] = {}
            self.share_links: Dict[str, ShareLink] = {}
            self._file_order: List[str] = []
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightDrive')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _shift(self, days: int = 0) -> str:
        return (self._today + timedelta(days=days)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        for f in DEFAULT_FOLDERS:
            self.folders[f["fdid"]] = Folder(
                fdid=f["fdid"], name=f["name"],
                parent_id=f["parent_id"], path=f["path"],
                created_at=self._shift(days=-60),
            )
        for name, folder_id, size, mime, created_offset, is_starred, is_trashed in SEED_FILES:
            fid = self.uuid()
            parent_path = self.folders[folder_id].path
            path = ("/" + name) if parent_path == "/" else f"{parent_path}/{name}"
            f = File(
                fid=fid,
                name=name,
                folder_id=folder_id,
                path=path,
                size_bytes=size,
                mime_type=mime,
                created_at=self._shift(days=created_offset),
                updated_at=self._shift(days=created_offset),
                is_starred=is_starred,
                is_trashed=is_trashed,
            )
            self.files[fid] = f
            self._file_order.append(fid)
        for file_idx, version_number, size, offset, comment in SEED_VERSIONS:
            fid = self._file_order[file_idx]
            v = Version(
                vid="v_" + self.uuid()[:10],
                file_id=fid,
                version_number=version_number,
                size_bytes=size,
                created_at=self._shift(days=offset),
                comment=comment,
            )
            self.versions[v.vid] = v
            self.files[fid].current_version_id = v.vid
            self.files[fid].size_bytes = size
        for kind, target_ref, can_edit, expires_offset, view_count in SEED_SHARE_LINKS:
            if kind == "file":
                target_id = self._file_order[target_ref]
            else:
                target_id = target_ref
            sl = ShareLink(
                slid="sl_" + self.uuid()[:10],
                target_kind=kind,
                target_id=target_id,
                url=f"https://drive.example.com/s/{self.uuid()[:12]}",
                can_edit=can_edit,
                expires_at=self._shift(days=expires_offset),
                view_count=view_count,
            )
            self.share_links[sl.slid] = sl

    def get_session_dict(self) -> Dict:
        return {
            "folders":     {fdid: asdict(f) for fdid, f in self.folders.items()},
            "files":       {fid: asdict(f) for fid, f in self.files.items()},
            "versions":    {vid: asdict(v) for vid, v in self.versions.items()},
            "share_links": {sid: asdict(s) for sid, s in self.share_links.items()},
        }

    def _file_summary(self, f: File) -> Dict:
        return {
            "fid": f.fid,
            "name": f.name,
            "folder_id": f.folder_id,
            "path": f.path,
            "size_bytes": f.size_bytes,
            "mime_type": f.mime_type,
            "is_starred": f.is_starred,
            "is_trashed": f.is_trashed,
            "updated_at": f.updated_at,
        }

    def _build_path(self, name: str, parent_id: str) -> str:
        parent = self.folders.get(parent_id)
        if parent is None:
            return "/" + name
        if parent.path == "/":
            return "/" + name
        return f"{parent.path}/{name}"

    def list_folders(self, parent_id: Optional[str] = None) -> Dict:
        items = list(self.folders.values())
        if parent_id is not None:
            items = [f for f in items if f.parent_id == parent_id]
        items.sort(key=lambda f: f.name.lower())
        return {"status": "ok", "output": [asdict(f) for f in items]}

    def get_folder(self, fdid: str) -> Dict:
        f = self.folders.get(fdid)
        if not f:
            return {"status": "failed", "output": f"folder {fdid} not found"}
        return {"status": "ok", "output": asdict(f)}

    def create_folder(self, name: str, parent_id: str = "fd_root") -> Dict:
        if parent_id and parent_id not in self.folders:
            return {"status": "failed", "output": f"parent folder {parent_id} not found"}
        fdid = "fd_" + self.uuid()[:8]
        parent = self.folders.get(parent_id)
        path = ("/" + name) if (not parent or parent.path == "/") else f"{parent.path}/{name}"
        f = Folder(fdid=fdid, name=name, parent_id=parent_id, path=path, created_at=self._now())
        self.folders[fdid] = f
        return {"status": "ok", "output": asdict(f)}

    def delete_folder(self, fdid: str) -> Dict:
        if fdid not in self.folders:
            return {"status": "failed", "output": f"folder {fdid} not found"}
        if fdid == "fd_root":
            return {"status": "failed", "output": "cannot delete root folder"}
        child_folders = [c for c in self.folders.values() if c.parent_id == fdid]
        if child_folders:
            return {"status": "failed", "output": f"folder {fdid} has sub-folders; delete them first"}
        removed_files = [fid for fid, f in self.files.items() if f.folder_id == fdid]
        for fid in removed_files:
            del self.files[fid]
        removed_versions = [vid for vid, v in self.versions.items() if v.file_id in removed_files]
        for vid in removed_versions:
            del self.versions[vid]
        del self.folders[fdid]
        return {"status": "ok", "output": {"fdid": fdid, "removed_files": len(removed_files)}}

    def list_files(self, folder_id: Optional[str] = None,
                   is_trashed: Optional[bool] = None,
                   is_starred: Optional[bool] = None) -> Dict:
        items = list(self.files.values())
        if folder_id is not None:
            items = [f for f in items if f.folder_id == folder_id]
        if is_trashed is not None:
            items = [f for f in items if f.is_trashed == is_trashed]
        if is_starred is not None:
            items = [f for f in items if f.is_starred == is_starred]
        items.sort(key=lambda f: f.name.lower())
        return {"status": "ok", "output": [self._file_summary(f) for f in items]}

    def get_file(self, fid: str) -> Dict:
        f = self.files.get(fid)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        return {"status": "ok", "output": asdict(f)}

    def upload_file(self, name: str, folder_id: str = "fd_root",
                    size_bytes: int = 0, mime_type: str = "application/octet-stream") -> Dict:
        if folder_id not in self.folders:
            return {"status": "failed", "output": f"folder {folder_id} not found"}
        fid = self.uuid()
        path = self._build_path(name, folder_id)
        f = File(
            fid=fid,
            name=name,
            folder_id=folder_id,
            path=path,
            size_bytes=size_bytes,
            mime_type=mime_type,
            created_at=self._now(),
            updated_at=self._now(),
        )
        v = Version(
            vid="v_" + self.uuid()[:10],
            file_id=fid,
            version_number=1,
            size_bytes=size_bytes,
            created_at=self._now(),
            comment="initial upload",
        )
        f.current_version_id = v.vid
        self.files[fid] = f
        self.versions[v.vid] = v
        return {"status": "ok", "output": self._file_summary(f)}

    def delete_file(self, fid: str) -> Dict:
        f = self.files.pop(fid, None)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        removed_versions = [vid for vid, v in self.versions.items() if v.file_id == fid]
        for vid in removed_versions:
            del self.versions[vid]
        removed_links = [sid for sid, s in self.share_links.items() if s.target_kind == "file" and s.target_id == fid]
        for sid in removed_links:
            del self.share_links[sid]
        return {"status": "ok", "output": {"fid": fid, "deleted": True, "removed_versions": len(removed_versions)}}

    def star_file(self, fid: str) -> Dict:
        f = self.files.get(fid)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        f.is_starred = True
        f.updated_at = self._now()
        return {"status": "ok", "output": self._file_summary(f)}

    def unstar_file(self, fid: str) -> Dict:
        f = self.files.get(fid)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        f.is_starred = False
        f.updated_at = self._now()
        return {"status": "ok", "output": self._file_summary(f)}

    def move_to_trash(self, fid: str) -> Dict:
        f = self.files.get(fid)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        f.is_trashed = True
        f.updated_at = self._now()
        return {"status": "ok", "output": self._file_summary(f)}

    def restore_from_trash(self, fid: str) -> Dict:
        f = self.files.get(fid)
        if not f:
            return {"status": "failed", "output": f"file {fid} not found"}
        f.is_trashed = False
        f.updated_at = self._now()
        return {"status": "ok", "output": self._file_summary(f)}

    def list_versions(self, file_id: str) -> Dict:
        if file_id not in self.files:
            return {"status": "failed", "output": f"file {file_id} not found"}
        items = [v for v in self.versions.values() if v.file_id == file_id]
        items.sort(key=lambda v: v.version_number)
        return {"status": "ok", "output": [asdict(v) for v in items]}

    def create_version(self, file_id: str, size_bytes: int = 0, comment: str = "") -> Dict:
        f = self.files.get(file_id)
        if not f:
            return {"status": "failed", "output": f"file {file_id} not found"}
        existing = [v for v in self.versions.values() if v.file_id == file_id]
        next_number = max((v.version_number for v in existing), default=0) + 1
        v = Version(
            vid="v_" + self.uuid()[:10],
            file_id=file_id,
            version_number=next_number,
            size_bytes=size_bytes,
            created_at=self._now(),
            comment=comment,
        )
        self.versions[v.vid] = v
        f.current_version_id = v.vid
        f.size_bytes = size_bytes
        f.updated_at = self._now()
        return {"status": "ok", "output": asdict(v)}

    def rollback_version(self, file_id: str, version_id: str) -> Dict:
        f = self.files.get(file_id)
        if not f:
            return {"status": "failed", "output": f"file {file_id} not found"}
        v = self.versions.get(version_id)
        if not v or v.file_id != file_id:
            return {"status": "failed", "output": f"version {version_id} not found for file {file_id}"}
        f.current_version_id = v.vid
        f.size_bytes = v.size_bytes
        f.updated_at = self._now()
        return {"status": "ok", "output": {"fid": file_id, "current_version_id": v.vid, "version_number": v.version_number}}

    def list_share_links(self, target_kind: Optional[str] = None,
                         target_id: Optional[str] = None) -> Dict:
        items = list(self.share_links.values())
        if target_kind:
            items = [s for s in items if s.target_kind == target_kind]
        if target_id:
            items = [s for s in items if s.target_id == target_id]
        items.sort(key=lambda s: s.slid)
        return {"status": "ok", "output": [asdict(s) for s in items]}

    def create_share_link(self, target_kind: str, target_id: str,
                          can_edit: bool = False, expires_at: str = "") -> Dict:
        if target_kind not in TARGET_KINDS:
            return {"status": "failed", "output": f"target_kind must be one of {TARGET_KINDS}"}
        if target_kind == "file" and target_id not in self.files:
            return {"status": "failed", "output": f"file {target_id} not found"}
        if target_kind == "folder" and target_id not in self.folders:
            return {"status": "failed", "output": f"folder {target_id} not found"}
        sl = ShareLink(
            slid="sl_" + self.uuid()[:10],
            target_kind=target_kind,
            target_id=target_id,
            url=f"https://drive.example.com/s/{self.uuid()[:12]}",
            can_edit=can_edit,
            expires_at=expires_at,
            view_count=0,
        )
        self.share_links[sl.slid] = sl
        return {"status": "ok", "output": asdict(sl)}

    def search(self, query: str) -> Dict:
        q = query.lower()
        file_hits = [
            self._file_summary(f) for f in self.files.values()
            if q in f.name.lower() or q in f.path.lower() or q in f.mime_type.lower()
        ]
        folder_hits = [
            asdict(f) for f in self.folders.values()
            if q in f.name.lower() or q in f.path.lower()
        ]
        file_hits.sort(key=lambda x: x["name"].lower())
        folder_hits.sort(key=lambda x: x["name"].lower())
        return {"status": "ok", "output": {"files": file_hits, "folders": folder_hits}}

    def get_stats(self) -> Dict:
        total_size = sum(f.size_bytes for f in self.files.values() if not f.is_trashed)
        trashed_size = sum(f.size_bytes for f in self.files.values() if f.is_trashed)
        starred = sum(1 for f in self.files.values() if f.is_starred)
        trashed = sum(1 for f in self.files.values() if f.is_trashed)
        by_folder: Dict[str, int] = {fdid: 0 for fdid in self.folders}
        for f in self.files.values():
            by_folder[f.folder_id] = by_folder.get(f.folder_id, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total_folders": len(self.folders),
                "total_files": len(self.files),
                "total_versions": len(self.versions),
                "total_share_links": len(self.share_links),
                "total_size_bytes": total_size,
                "trashed_size_bytes": trashed_size,
                "starred_count": starred,
                "trashed_count": trashed,
                "by_folder": by_folder,
            },
        }
