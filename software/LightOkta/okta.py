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


class OktaSession:
    """Deterministic sandbox for the Okta Management API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "okta.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = [
                {
                    **u,
                    "activated": (str(u.get("activated") or "") or None),
                    "last_login": (str(u.get("last_login") or "") or None),
                }
                for u in info.get("users", [])
            ]
            self.groups: List[Dict[str, Any]] = list(info.get("groups", []))
            self.memberships: List[Dict[str, Any]] = list(info.get("group_memberships", []))
            self.apps: List[Dict[str, Any]] = list(info.get("apps", []))
            self.app_assignments: List[Dict[str, Any]] = list(info.get("app_assignments", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightOkta')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"users": self.users}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=9))

    def _serialize_user(self, u):
        return {
            "id": u["id"],
            "status": u["status"],
            "created": u["created"],
            "activated": u["activated"],
            "lastLogin": u["last_login"],
            "profile": {
                "firstName": u["first_name"],
                "lastName": u["last_name"],
                "email": u["email"],
                "login": u["login"],
            },
        }

    def _serialize_group(self, g):
        return {
            "id": g["id"],
            "type": g["type"],
            "created": g["created"],
            "profile": {"name": g["name"], "description": g["description"]},
        }

    def _serialize_app(self, a):
        return {
            "id": a["id"],
            "name": a["name"],
            "label": a["label"],
            "status": a["status"],
            "signOnMode": a["sign_on_mode"],
            "created": a["created"],
        }

    def _find_user(self, user_id):
        return next((u for u in self.users if u["id"] == user_id), None)

    def _find_group(self, group_id):
        return next((g for g in self.groups if g["id"] == group_id), None)

    def _set_user_status(self, user_id, status, set_activated=False):
        u = self._find_user(user_id)
        if not u:
            return {"status": "failed", "output": f"User {user_id} not found"}
        u["status"] = status
        if set_activated and not u["activated"]:
            u["activated"] = self._now()
        return {"status": "ok", "output": self._serialize_user(u)}

    # --- Users -------------------------------------------------------------
    def list_users(self, status: str | None = None, q: str | None = None) -> Dict[str, Any]:
        results = list(self.users)
        if status:
            results = [u for u in results if u["status"] == status]
        if q:
            ql = q.lower()
            results = [u for u in results
                       if ql in u["first_name"].lower()
                       or ql in u["last_name"].lower()
                       or ql in u["email"].lower()]
        return {"status": "ok", "output": [self._serialize_user(u) for u in results]}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        u = self._find_user(user_id)
        if not u:
            return {"status": "failed", "output": f"User {user_id} not found"}
        return {"status": "ok", "output": self._serialize_user(u)}

    def create_user(self, first_name: str, last_name: str, email: str,
                    login: str | None = None, activate: bool = True) -> Dict[str, Any]:
        user = {
            "id": f"00u{self.uuid()}",
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "login": login or email,
            "status": "ACTIVE" if activate else "STAGED",
            "created": self._now(),
            "activated": self._now() if activate else None,
            "last_login": None,
        }
        self.users.append(user)
        return {"status": "ok", "output": self._serialize_user(user)}

    def activate_user(self, user_id: str) -> Dict[str, Any]:
        u = self._find_user(user_id)
        if not u:
            return {"status": "failed", "output": f"User {user_id} not found"}
        if u["status"] not in ("STAGED", "PROVISIONED", "DEPROVISIONED"):
            return {"status": "failed", "output": f"User {user_id} cannot be activated from status {u['status']}"}
        return self._set_user_status(user_id, "ACTIVE", set_activated=True)

    def suspend_user(self, user_id: str) -> Dict[str, Any]:
        u = self._find_user(user_id)
        if not u:
            return {"status": "failed", "output": f"User {user_id} not found"}
        if u["status"] != "ACTIVE":
            return {"status": "failed", "output": f"User {user_id} cannot be suspended from status {u['status']}"}
        return self._set_user_status(user_id, "SUSPENDED")

    def deactivate_user(self, user_id: str) -> Dict[str, Any]:
        u = self._find_user(user_id)
        if not u:
            return {"status": "failed", "output": f"User {user_id} not found"}
        return self._set_user_status(user_id, "DEPROVISIONED")

    # --- Groups ------------------------------------------------------------
    def list_groups(self, q: str | None = None) -> Dict[str, Any]:
        results = list(self.groups)
        if q:
            ql = q.lower()
            results = [g for g in results if ql in g["name"].lower()]
        return {"status": "ok", "output": [self._serialize_group(g) for g in results]}

    def get_group(self, group_id: str) -> Dict[str, Any]:
        g = self._find_group(group_id)
        if not g:
            return {"status": "failed", "output": f"Group {group_id} not found"}
        return {"status": "ok", "output": self._serialize_group(g)}

    def list_group_users(self, group_id: str) -> Dict[str, Any]:
        g = self._find_group(group_id)
        if not g:
            return {"status": "failed", "output": f"Group {group_id} not found"}
        member_ids = [m["user_id"] for m in self.memberships if m["group_id"] == group_id]
        return {"status": "ok", "output": [self._serialize_user(u) for u in self.users if u["id"] in member_ids]}

    # --- Apps --------------------------------------------------------------
    def list_apps(self, status: str | None = None) -> Dict[str, Any]:
        results = list(self.apps)
        if status:
            results = [a for a in results if a["status"] == status]
        return {"status": "ok", "output": [self._serialize_app(a) for a in results]}


if __name__ == "__main__":
    s = OktaSession(seed=12)
    print(s.list_users())
    print(s.list_groups())
