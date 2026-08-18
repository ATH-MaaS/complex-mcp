import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from copy import deepcopy
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"

_TRUE_TOKENS = {"true", "1", "yes", "y", "t"}
_FALSE_TOKENS = {"false", "0", "no", "n", "f"}


def _opt_int(v, default=0):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_float(v, default=0.0):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_str(v, default=""):
    if v is None:
        return default
    return str(v)


def _strict_bool(v) -> bool:
    token = str(v).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return False


class IntercomSession:
    """Deterministic sandbox for the Intercom mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "intercom.yaml") as f:
                info = yaml.safe_load(f)

            self.contacts: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "role": r["role"],
                    "name": r["name"],
                    "email": _opt_str(r.get("email"), default="") or None,
                    "phone": _opt_str(r.get("phone"), default="") or None,
                    "company_id": _opt_str(r.get("company_id"), default="") or None,
                    "created_at": r["created_at"],
                    "last_seen_at": _opt_str(r.get("last_seen_at"), default="") or None,
                }
                for r in info.get("contacts", [])
            ]
            self.companies: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "company_id": r["company_id"],
                    "name": r["name"],
                    "plan": r["plan"],
                    "monthly_spend": _opt_float(r.get("monthly_spend"), default=0.0),
                    "user_count": _opt_int(r.get("user_count"), default=0),
                    "industry": r["industry"],
                    "created_at": r["created_at"],
                }
                for r in info.get("companies", [])
            ]
            self.conversations: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "contact_id": r["contact_id"],
                    "state": r["state"],
                    "title": r["title"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "assignee_id": _opt_str(r.get("assignee_id"), default="") or None,
                    "open": _strict_bool(r["open"]),
                }
                for r in info.get("conversations", [])
            ]
            self.parts: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "conversation_id": r["conversation_id"],
                    "part_type": r["part_type"],
                    "author_type": r["author_type"],
                    "author_id": r["author_id"],
                    "body": _opt_str(r.get("body"), default="") or None,
                    "created_at": r["created_at"],
                }
                for r in info.get("conversation_parts", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightIntercom')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"conversations": self.conversations, "parts": self.parts}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _get_contact(self, contact_id):
        for c in self.contacts:
            if c["id"] == contact_id:
                return c
        return None

    def _find_conversation(self, conversation_id):
        for c in self.conversations:
            if c["id"] == conversation_id:
                return c
        return None

    def _conversation_obj(self, conv, with_parts=False):
        obj = {
            "type": "conversation",
            "id": conv["id"],
            "state": conv["state"],
            "open": conv["open"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "contact_id": conv["contact_id"],
            "admin_assignee_id": conv["assignee_id"],
        }
        if with_parts:
            parts = [p for p in self.parts if p["conversation_id"] == conv["id"]]
            parts = sorted(parts, key=lambda p: p["created_at"])
            obj["conversation_parts"] = {
                "type": "conversation_part.list",
                "total_count": len(parts),
                "conversation_parts": [deepcopy(p) for p in parts],
            }
        return obj

    # --- API methods -------------------------------------------------------
    def list_contacts(self, role: str | None = None) -> Dict[str, Any]:
        contacts = list(self.contacts)
        if role:
            contacts = [c for c in contacts if c["role"] == role]
        return {"status": "ok", "output": {
            "type": "list",
            "data": contacts,
            "total_count": len(contacts),
        }}

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        c = self._get_contact(contact_id)
        if c:
            return {"status": "ok", "output": {"type": "contact", **c}}
        return {"status": "failed", "output": f"Contact {contact_id} not found"}

    def create_contact(self, role: str = "user", name: str = "", email: str | None = None,
                       phone: str | None = None, company_id: str | None = None) -> Dict[str, Any]:
        contact = {
            "id": self._new_id("contact"),
            "role": role,
            "name": name or "",
            "email": email,
            "phone": phone,
            "company_id": company_id,
            "created_at": self._now(),
            "last_seen_at": None,
        }
        self.contacts.append(contact)
        return {"status": "ok", "output": {"type": "contact", **contact}}

    def list_companies(self) -> Dict[str, Any]:
        rows = list(self.companies)
        return {"status": "ok", "output": {
            "type": "list",
            "data": rows,
            "total_count": len(rows),
        }}

    def get_company(self, company_id: str) -> Dict[str, Any]:
        for c in self.companies:
            if c["id"] == company_id or c["company_id"] == company_id:
                return {"status": "ok", "output": {"type": "company", **c}}
        return {"status": "failed", "output": f"Company {company_id} not found"}

    def list_conversations(self, state: str | None = None) -> Dict[str, Any]:
        convs = list(self.conversations)
        if state:
            convs = [c for c in convs if c["state"] == state]
        return {"status": "ok", "output": {
            "type": "conversation.list",
            "conversations": [self._conversation_obj(c) for c in convs],
            "total_count": len(convs),
        }}

    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        c = self._find_conversation(conversation_id)
        if c:
            return {"status": "ok", "output": self._conversation_obj(c, with_parts=True)}
        return {"status": "failed", "output": f"Conversation {conversation_id} not found"}

    def create_conversation(self, contact_id: str, body: str, title: str = "") -> Dict[str, Any]:
        if not self._get_contact(contact_id):
            return {"status": "failed", "output": f"Contact {contact_id} not found"}
        now = self._now()
        conv = {
            "id": self._new_id("conv"),
            "contact_id": contact_id,
            "state": "open",
            "title": title or (body[:60] if body else "New conversation"),
            "created_at": now,
            "updated_at": now,
            "assignee_id": None,
            "open": True,
        }
        self.conversations.append(conv)
        part = {
            "id": self._new_id("part"),
            "conversation_id": conv["id"],
            "part_type": "comment",
            "author_type": "user",
            "author_id": contact_id,
            "body": body,
            "created_at": now,
        }
        self.parts.append(part)
        return {"status": "ok", "output": self._conversation_obj(conv, with_parts=True)}

    def reply_conversation(self, conversation_id: str, body: str, author_type: str = "admin",
                          author_id: str = "admin-jonas") -> Dict[str, Any]:
        conv = self._find_conversation(conversation_id)
        if not conv:
            return {"status": "failed", "output": f"Conversation {conversation_id} not found"}
        now = self._now()
        part = {
            "id": self._new_id("part"),
            "conversation_id": conversation_id,
            "part_type": "comment",
            "author_type": author_type,
            "author_id": author_id,
            "body": body,
            "created_at": now,
        }
        self.parts.append(part)
        conv["updated_at"] = now
        return {"status": "ok", "output": self._conversation_obj(conv, with_parts=True)}

    def add_part(self, conversation_id: str, message_type: str, body: str | None = None,
                 author_id: str = "admin-jonas", assignee_id: str | None = None) -> Dict[str, Any]:
        conv = self._find_conversation(conversation_id)
        if not conv:
            return {"status": "failed", "output": f"Conversation {conversation_id} not found"}
        now = self._now()
        part = {
            "id": self._new_id("part"),
            "conversation_id": conversation_id,
            "part_type": message_type,
            "author_type": "admin",
            "author_id": author_id,
            "body": body,
            "created_at": now,
        }
        self.parts.append(part)

        conv["updated_at"] = now
        if message_type == "close":
            conv["state"] = "closed"
            conv["open"] = False
        elif message_type == "open":
            conv["state"] = "open"
            conv["open"] = True
        elif message_type == "assignment":
            conv["assignee_id"] = assignee_id or author_id
        return {"status": "ok", "output": self._conversation_obj(conv, with_parts=True)}


if __name__ == "__main__":
    s = IntercomSession(seed=12)
    print(s.list_contacts())
    print(s.list_conversations(state="open"))
