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


STRENGTHS = ("weak", "medium", "strong")

DEFAULT_FOLDERS = [
    {"fdid": "fd_personal", "name": "Personal", "color": "#4285F4"},
    {"fdid": "fd_work",     "name": "Work",     "color": "#DB4437"},
    {"fdid": "fd_social",   "name": "Social",   "color": "#0F9D58"},
]

SEED_ENTRIES = [
    ("Gmail",      "alice@gmail.com",  "GsuperSecr3t1!x", "https://mail.google.com", "primary email",      ["email", "google"],   "fd_personal", "strong",  -30, -3),
    ("Bank Portal","alice.smith",      "B4nkPassw0rdY",   "https://bank.example.com","checking account",   ["finance", "bank"],   "fd_personal", "strong",  -60, -1),
    ("Slack Work", "alice@corp.com",   "SlackW0rk#42a",   "https://corp.slack.com",  "sso enabled",        ["work", "chat"],      "fd_work",     "medium", -20,  0),
    ("GitHub",     "alicecodes",       "Git!hubTok0nzP",  "https://github.com",      "with 2fa",           ["work", "dev"],       "fd_work",     "strong",  -90, -5),
    ("Twitter",    "@alicetweets",     "twt123abc",       "https://twitter.com",     "public account",     ["social"],            "fd_social",   "weak",   -10, -2),
    ("Reddit",     "alice_reads",      "R3dd1tCoolPWq",   "https://reddit.com",      "lurker",             ["social"],            "fd_social",   "medium", -14, -7),
]

SEED_SHARES = [
    (0, "bob@corp.com",   5, False),
    (2, "team@corp.com", 30, True),
]

SEED_AUDIT = [
    ("created", 0, "self", -30),
    ("viewed",  0, "self", -3),
    ("updated", 1, "self", -14),
    ("shared",  2, "self", 0),
    ("viewed",  3, "self", -5),
]


@dataclass
class Entry:
    entid: str
    title: str
    username: str
    password_masked: str
    url: str
    notes: str
    tags: List[str]
    folder_id: str
    created_at: str
    updated_at: str
    last_used_at: str
    strength: str


@dataclass
class Folder:
    fdid: str
    name: str
    color: str


@dataclass
class Share:
    shid: str
    entry_id: str
    shared_with: str
    shared_at: str
    expires_at: str
    can_edit: bool


@dataclass
class AuditLog:
    audit_id: str
    action: str
    entry_id: str
    actor: str
    timestamp: str


def _mask_password(pw: str) -> str:
    if not pw:
        return ""
    if len(pw) == 1:
        return pw
    if len(pw) == 2:
        return pw[0] + pw[-1]
    return pw[0] + ("*" * (len(pw) - 2)) + pw[-1]


class VaultSession:
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
            self.folders: Dict[str, Folder] = {
                f["fdid"]: Folder(**f) for f in DEFAULT_FOLDERS
            }
            self.entries: Dict[str, Entry] = {}
            self.shares: Dict[str, Share] = {}
            self.audit_logs: Dict[str, AuditLog] = {}
            self._entry_order: List[str] = []
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightVault')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _shift(self, days: int = 0, hours: int = 0) -> str:
        return (self._today + timedelta(days=days, hours=hours)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        for title, user, pw, url, notes, tags, folder_id, strength, created_offset, used_offset in SEED_ENTRIES:
            e = Entry(
                entid=self.uuid(),
                title=title,
                username=user,
                password_masked=_mask_password(pw),
                url=url,
                notes=notes,
                tags=list(tags),
                folder_id=folder_id,
                created_at=self._shift(days=created_offset),
                updated_at=self._shift(days=created_offset),
                last_used_at=self._shift(days=used_offset),
                strength=strength,
            )
            self.entries[e.entid] = e
            self._entry_order.append(e.entid)
        for entry_idx, shared_with, expires_offset, can_edit in SEED_SHARES:
            entid = self._entry_order[entry_idx]
            s = Share(
                shid="sh_" + self.uuid()[:10],
                entry_id=entid,
                shared_with=shared_with,
                shared_at=self._now(),
                expires_at=self._shift(days=expires_offset),
                can_edit=can_edit,
            )
            self.shares[s.shid] = s
        for action, entry_idx, actor, ts_offset in SEED_AUDIT:
            entid = self._entry_order[entry_idx]
            a = AuditLog(
                audit_id="au_" + self.uuid()[:10],
                action=action,
                entry_id=entid,
                actor=actor,
                timestamp=self._shift(days=ts_offset),
            )
            self.audit_logs[a.audit_id] = a

    def get_session_dict(self) -> Dict:
        return {
            "folders":    {fdid: asdict(f) for fdid, f in self.folders.items()},
            "entries":    {eid: asdict(e) for eid, e in self.entries.items()},
            "shares":     {sid: asdict(s) for sid, s in self.shares.items()},
            "audit_logs": {aid: asdict(a) for aid, a in self.audit_logs.items()},
        }

    def _entry_summary(self, e: Entry) -> Dict:
        return {
            "entid": e.entid,
            "title": e.title,
            "username": e.username,
            "url": e.url,
            "folder_id": e.folder_id,
            "tags": list(e.tags),
            "strength": e.strength,
            "last_used_at": e.last_used_at,
        }

    def _log(self, action: str, entry_id: str, actor: str = "self") -> None:
        a = AuditLog(
            audit_id="au_" + self.uuid()[:10],
            action=action,
            entry_id=entry_id,
            actor=actor,
            timestamp=self._now(),
        )
        self.audit_logs[a.audit_id] = a

    def list_entries(self, folder_id: Optional[str] = None, tag: Optional[str] = None) -> Dict:
        items = list(self.entries.values())
        if folder_id:
            items = [e for e in items if e.folder_id == folder_id]
        if tag:
            items = [e for e in items if tag in e.tags]
        items.sort(key=lambda e: e.title.lower())
        return {"status": "ok", "output": [self._entry_summary(e) for e in items]}

    def get_entry(self, entid: str) -> Dict:
        e = self.entries.get(entid)
        if not e:
            return {"status": "failed", "output": f"entry {entid} not found"}
        return {"status": "ok", "output": asdict(e)}

    def create_entry(self, title: str, username: str, password: str,
                     url: str = "", notes: str = "",
                     tags: Optional[List[str]] = None,
                     folder_id: str = "fd_personal") -> Dict:
        if folder_id not in self.folders:
            return {"status": "failed", "output": f"folder {folder_id} not found"}
        if len(password) < 8:
            strength = "weak"
        elif len(password) < 12:
            strength = "medium"
        else:
            strength = "strong"
        e = Entry(
            entid=self.uuid(),
            title=title,
            username=username,
            password_masked=_mask_password(password),
            url=url,
            notes=notes,
            tags=list(tags) if tags else [],
            folder_id=folder_id,
            created_at=self._now(),
            updated_at=self._now(),
            last_used_at="",
            strength=strength,
        )
        self.entries[e.entid] = e
        self._log("created", e.entid)
        return {"status": "ok", "output": self._entry_summary(e)}

    def update_entry(self, entid: str,
                     title: Optional[str] = None,
                     username: Optional[str] = None,
                     password: Optional[str] = None,
                     url: Optional[str] = None,
                     notes: Optional[str] = None,
                     tags: Optional[List[str]] = None,
                     folder_id: Optional[str] = None) -> Dict:
        e = self.entries.get(entid)
        if not e:
            return {"status": "failed", "output": f"entry {entid} not found"}
        if folder_id is not None and folder_id not in self.folders:
            return {"status": "failed", "output": f"folder {folder_id} not found"}
        if title is not None:
            e.title = title
        if username is not None:
            e.username = username
        if password is not None:
            e.password_masked = _mask_password(password)
            if len(password) < 8:
                e.strength = "weak"
            elif len(password) < 12:
                e.strength = "medium"
            else:
                e.strength = "strong"
        if url is not None:
            e.url = url
        if notes is not None:
            e.notes = notes
        if tags is not None:
            e.tags = list(tags)
        if folder_id is not None:
            e.folder_id = folder_id
        e.updated_at = self._now()
        self._log("updated", entid)
        return {"status": "ok", "output": self._entry_summary(e)}

    def delete_entry(self, entid: str) -> Dict:
        e = self.entries.pop(entid, None)
        if not e:
            return {"status": "failed", "output": f"entry {entid} not found"}
        removed_shares = [sid for sid, s in self.shares.items() if s.entry_id == entid]
        for sid in removed_shares:
            del self.shares[sid]
        self._log("deleted", entid)
        return {"status": "ok", "output": {"entid": entid, "deleted": True, "removed_shares": len(removed_shares)}}

    def copy_password(self, entid: str) -> Dict:
        e = self.entries.get(entid)
        if not e:
            return {"status": "failed", "output": f"entry {entid} not found"}
        e.last_used_at = self._now()
        self._log("copied", entid)
        return {"status": "ok", "output": {"entid": entid, "password_masked": e.password_masked, "copied_at": e.last_used_at}}

    def mark_used(self, entid: str) -> Dict:
        e = self.entries.get(entid)
        if not e:
            return {"status": "failed", "output": f"entry {entid} not found"}
        e.last_used_at = self._now()
        self._log("viewed", entid)
        return {"status": "ok", "output": {"entid": entid, "last_used_at": e.last_used_at}}

    def list_folders(self) -> Dict:
        return {"status": "ok", "output": [asdict(f) for f in self.folders.values()]}

    def create_folder(self, name: str, color: str = "#888888") -> Dict:
        fdid = "fd_" + self.uuid()[:8]
        f = Folder(fdid=fdid, name=name, color=color)
        self.folders[fdid] = f
        return {"status": "ok", "output": asdict(f)}

    def delete_folder(self, fdid: str) -> Dict:
        if fdid not in self.folders:
            return {"status": "failed", "output": f"folder {fdid} not found"}
        remaining = [f for f in self.folders if f != fdid]
        if not remaining:
            return {"status": "failed", "output": "cannot delete the last folder"}
        fallback = "fd_personal" if "fd_personal" in remaining else remaining[0]
        moved = 0
        for e in self.entries.values():
            if e.folder_id == fdid:
                e.folder_id = fallback
                e.updated_at = self._now()
                moved += 1
        del self.folders[fdid]
        return {"status": "ok", "output": {"fdid": fdid, "moved": moved, "reassigned_to": fallback}}

    def list_shares(self, entry_id: Optional[str] = None) -> Dict:
        items = list(self.shares.values())
        if entry_id:
            items = [s for s in items if s.entry_id == entry_id]
        items.sort(key=lambda s: s.shared_at)
        return {"status": "ok", "output": [asdict(s) for s in items]}

    def share_entry(self, entry_id: str, shared_with: str,
                    expires_at: str = "", can_edit: bool = False) -> Dict:
        if entry_id not in self.entries:
            return {"status": "failed", "output": f"entry {entry_id} not found"}
        s = Share(
            shid="sh_" + self.uuid()[:10],
            entry_id=entry_id,
            shared_with=shared_with,
            shared_at=self._now(),
            expires_at=expires_at,
            can_edit=can_edit,
        )
        self.shares[s.shid] = s
        self._log("shared", entry_id)
        return {"status": "ok", "output": asdict(s)}

    def revoke_share(self, shid: str) -> Dict:
        s = self.shares.pop(shid, None)
        if not s:
            return {"status": "failed", "output": f"share {shid} not found"}
        self._log("revoked_share", s.entry_id)
        return {"status": "ok", "output": {"shid": shid, "revoked": True}}

    def list_audit_logs(self, entry_id: Optional[str] = None) -> Dict:
        items = list(self.audit_logs.values())
        if entry_id:
            items = [a for a in items if a.entry_id == entry_id]
        items.sort(key=lambda a: a.timestamp, reverse=True)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def search_entries(self, query: str) -> Dict:
        q = query.lower()
        items = [
            e for e in self.entries.values()
            if q in e.title.lower()
            or q in e.username.lower()
            or q in e.url.lower()
            or q in e.notes.lower()
            or any(q in tag.lower() for tag in e.tags)
        ]
        items.sort(key=lambda e: e.title.lower())
        return {"status": "ok", "output": [self._entry_summary(e) for e in items]}

    def get_stats(self) -> Dict:
        by_folder: Dict[str, int] = {fdid: 0 for fdid in self.folders}
        by_strength: Dict[str, int] = {s: 0 for s in STRENGTHS}
        for e in self.entries.values():
            by_folder[e.folder_id] = by_folder.get(e.folder_id, 0) + 1
            by_strength[e.strength] = by_strength.get(e.strength, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total_entries": len(self.entries),
                "total_folders": len(self.folders),
                "total_shares": len(self.shares),
                "total_audit_logs": len(self.audit_logs),
                "by_folder": by_folder,
                "by_strength": by_strength,
            },
        }
