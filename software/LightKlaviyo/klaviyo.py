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
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class KlaviyoSession:
    """Deterministic sandbox for the Klaviyo mock, ported from the FastAPI service.

    Mirrors a subset of the Klaviyo API (JSON:API style): profiles, lists, and
    campaigns. State is loaded from the corpus at init; subsequent calls read and
    mutate the in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "klaviyo.yaml") as f:
                info = yaml.safe_load(f)

            self.profiles: List[Dict[str, Any]] = [
                {
                    "id": p["id"],
                    "email": p["email"],
                    "phone_number": p["phone_number"],
                    "first_name": p["first_name"],
                    "last_name": p["last_name"],
                    "organization": p["organization"],
                    "title": p["title"],
                    "city": p["city"],
                    "region": p["region"],
                    "country": p["country"],
                    "created": p["created"],
                    "updated": p["updated"],
                }
                for p in info.get("profiles", [])
            ]
            self.lists: List[Dict[str, Any]] = [
                {
                    "id": l["id"],
                    "name": l["name"],
                    "profile_count": _to_int(l.get("profile_count", 0)),
                    "created": l["created"],
                    "updated": l["updated"],
                }
                for l in info.get("lists", [])
            ]
            self.campaigns: List[Dict[str, Any]] = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "status": c["status"],
                    "channel": c["channel"],
                    "subject": c["subject"],
                    "from_email": c["from_email"],
                    "from_label": c["from_label"],
                    "list_id": c["list_id"],
                    "send_time": (c.get("send_time") or None),
                    "created": c["created"],
                    "updated": c["updated"],
                }
                for c in info.get("campaigns", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightKlaviyo')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"profiles": self.profiles}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "01HZPROF" + ''.join(self.rng.choices(alphabet, k=18))

    def _serialize_profile(self, p):
        return {
            "type": "profile",
            "id": p["id"],
            "attributes": {
                "email": p["email"],
                "phone_number": p["phone_number"],
                "first_name": p["first_name"],
                "last_name": p["last_name"],
                "organization": p["organization"],
                "title": p["title"],
                "location": {
                    "city": p["city"],
                    "region": p["region"],
                    "country": p["country"],
                },
                "created": p["created"],
                "updated": p["updated"],
            },
        }

    def _serialize_list(self, l):
        return {
            "type": "list",
            "id": l["id"],
            "attributes": {
                "name": l["name"],
                "profile_count": l["profile_count"],
                "created": l["created"],
                "updated": l["updated"],
            },
        }

    def _serialize_campaign(self, c):
        return {
            "type": "campaign",
            "id": c["id"],
            "attributes": {
                "name": c["name"],
                "status": c["status"],
                "channel": c["channel"],
                "subject": c["subject"],
                "from_email": c["from_email"],
                "from_label": c["from_label"],
                "send_time": c["send_time"],
                "created": c["created"],
                "updated": c["updated"],
            },
            "relationships": {
                "list": {"data": {"type": "list", "id": c["list_id"]}}
            },
        }

    # --- Profiles ----------------------------------------------------------
    def list_profiles(self, email: str | None = None) -> Dict[str, Any]:
        profiles = list(self.profiles)
        if email:
            profiles = [p for p in profiles if p["email"].lower() == email.lower()]
        return {"status": "ok", "output": [self._serialize_profile(p) for p in profiles]}

    def get_profile(self, profile_id: str) -> Dict[str, Any]:
        for p in self.profiles:
            if p["id"] == profile_id:
                return {"status": "ok", "output": self._serialize_profile(p)}
        return {"status": "failed", "output": f"Profile {profile_id} not found"}

    def create_profile(self, email: str, first_name: str = "", last_name: str = "",
                       phone_number: str = "", organization: str = "", title: str = "",
                       city: str = "", region: str = "", country: str = "") -> Dict[str, Any]:
        if not email:
            return {"status": "failed", "output": "attributes.email is required"}
        if any(p["email"].lower() == email.lower() for p in self.profiles):
            return {"status": "failed", "output": f"Profile with email {email} already exists"}
        now = self._now()
        profile = {
            "id": self.uuid(),
            "email": email,
            "phone_number": phone_number or "",
            "first_name": first_name or "",
            "last_name": last_name or "",
            "organization": organization or "",
            "title": title or "",
            "city": city or "",
            "region": region or "",
            "country": country or "",
            "created": now,
            "updated": now,
        }
        self.profiles.append(profile)
        return {"status": "ok", "output": self._serialize_profile(profile)}

    # --- Lists -------------------------------------------------------------
    def list_lists(self) -> Dict[str, Any]:
        return {"status": "ok", "output": [self._serialize_list(l) for l in self.lists]}

    # --- Campaigns ---------------------------------------------------------
    def list_campaigns(self, status: str | None = None, channel: str | None = None) -> Dict[str, Any]:
        campaigns = list(self.campaigns)
        if status:
            campaigns = [c for c in campaigns if c["status"].lower() == status.lower()]
        if channel:
            campaigns = [c for c in campaigns if c["channel"].lower() == channel.lower()]
        return {"status": "ok", "output": [self._serialize_campaign(c) for c in campaigns]}


if __name__ == "__main__":
    s = KlaviyoSession(seed=12)
    print(s.list_profiles())
    print(s.list_campaigns(status="Sent", channel="email"))
