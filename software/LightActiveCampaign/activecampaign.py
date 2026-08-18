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


class ActiveCampaignSession:
    """Deterministic sandbox for the ActiveCampaign mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "activecampaign.yaml") as f:
                info = yaml.safe_load(f)

            self.contacts: List[Dict[str, Any]] = list(info.get("contacts", []))
            self.lists: List[Dict[str, Any]] = list(info.get("lists", []))
            self.campaigns: List[Dict[str, Any]] = list(info.get("campaigns", []))
            self.deals: List[Dict[str, Any]] = list(info.get("deals", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightActiveCampaign')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"contacts": self.contacts}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _serialize_contact(self, c):
        return {
            "id": c["id"],
            "email": c["email"],
            "firstName": c["first_name"],
            "lastName": c["last_name"],
            "phone": c["phone"],
            "status": c["status"],
            "cdate": c["created_timestamp"],
            "udate": c["updated_timestamp"],
            "links": {
                "contactLists": f"/api/3/contacts/{c['id']}/contactLists",
                "deals": f"/api/3/contacts/{c['id']}/deals",
            },
        }

    def _serialize_list(self, l):
        return {
            "id": l["id"],
            "name": l["name"],
            "stringid": l["stringid"],
            "subscriber_count": l["subscriber_count"],
            "sender_url": l["sender_url"],
            "sender_reminder": l["sender_reminder"],
            "cdate": l["created_timestamp"],
        }

    def _serialize_campaign(self, c):
        return {
            "id": c["id"],
            "name": c["name"],
            "type": c["type"],
            "status": c["status"],
            "listid": c["list_id"],
            "subject": c["subject"],
            "send_amt": c["send_amt"],
            "opens": c["opens"],
            "linkclicks": c["clicks"],
            "sdate": c["sdate"],
            "cdate": c["created_timestamp"],
        }

    def _serialize_deal(self, d):
        return {
            "id": d["id"],
            "title": d["title"],
            "contact": d["contact_id"],
            "value": d["value"],
            "currency": d["currency"],
            "status": d["status"],
            "stage": d["stage"],
            "owner": d["owner"],
            "cdate": d["created_timestamp"],
            "mdate": d["updated_timestamp"],
        }

    def _meta(self, total, offset=0, limit=20):
        return {"total": str(total), "page_input": {"offset": offset, "limit": limit}}

    # --- API methods -------------------------------------------------------
    def list_contacts(self, email: str | None = None, status: str | None = None,
                      limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        contacts = self.contacts
        if email:
            contacts = [c for c in contacts if c["email"].lower() == email.lower()]
        if status is not None:
            contacts = [c for c in contacts if c["status"] == str(status)]
        total = len(contacts)
        window = contacts[offset:offset + limit]
        return {"status": "ok", "output": {
            "contacts": [self._serialize_contact(c) for c in window],
            "meta": self._meta(total, offset=offset, limit=limit),
        }}

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        c = next((x for x in self.contacts if x["id"] == str(contact_id)), None)
        if not c:
            return {"status": "failed", "output": f"Contact {contact_id} not found"}
        return {"status": "ok", "output": {"contact": self._serialize_contact(c)}}

    def create_contact(self, email: str, first_name: str = "", last_name: str = "",
                       phone: str = "", status: str = "1") -> Dict[str, Any]:
        if not email:
            return {"status": "failed", "output": "email is required"}
        existing = next((c for c in self.contacts if c["email"].lower() == email.lower()), None)
        if existing:
            return {"status": "failed", "output": f"Contact with email {email} already exists"}
        now = self._now()
        new_id = str(max((int(c["id"]) for c in self.contacts), default=0) + 1)
        contact = {
            "id": new_id,
            "email": email,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "phone": phone or "",
            "status": str(status),
            "created_timestamp": now,
            "updated_timestamp": now,
        }
        self.contacts.append(contact)
        return {"status": "ok", "output": {"contact": self._serialize_contact(contact)}}

    def list_lists(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        total = len(self.lists)
        window = self.lists[offset:offset + limit]
        return {"status": "ok", "output": {
            "lists": [self._serialize_list(l) for l in window],
            "meta": self._meta(total, offset=offset, limit=limit),
        }}

    def list_campaigns(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        total = len(self.campaigns)
        window = self.campaigns[offset:offset + limit]
        return {"status": "ok", "output": {
            "campaigns": [self._serialize_campaign(c) for c in window],
            "meta": self._meta(total, offset=offset, limit=limit),
        }}

    def list_deals(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        total = len(self.deals)
        window = self.deals[offset:offset + limit]
        return {"status": "ok", "output": {
            "deals": [self._serialize_deal(d) for d in window],
            "meta": self._meta(total, offset=offset, limit=limit),
        }}


if __name__ == "__main__":
    s = ActiveCampaignSession(seed=12)
    print(s.list_contacts())
    print(s.list_deals())
