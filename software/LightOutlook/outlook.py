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

_ME_NAME = "Alex Carter"
_ME_ADDRESS = "alex.carter@contoso.com"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


class OutlookSession:
    """Deterministic sandbox for the Outlook (Microsoft Graph) mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "outlook.yaml") as f:
                info = yaml.safe_load(f)

            self.messages: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "subject": r["subject"],
                    "from_name": r["from_name"],
                    "from_address": r["from_address"],
                    "to_name": r["to_name"],
                    "to_address": r["to_address"],
                    "bodyPreview": r["body_preview"],
                    "contentType": r["content_type"],
                    "isRead": _to_bool(r.get("is_read", False)),
                    "importance": r["importance"],
                    "receivedDateTime": r["received_date"],
                }
                for r in info.get("messages", [])
            ]
            self.events: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "subject": r["subject"],
                    "organizer_name": r["organizer_name"],
                    "organizer_address": r["organizer_address"],
                    "location": r["location"],
                    "start": r["start_date"],
                    "end": r["end_date"],
                    "isAllDay": _to_bool(r.get("is_all_day", False)),
                    "isOnlineMeeting": _to_bool(r.get("is_online", False)),
                    "attendees": [x.strip() for x in str(r.get("attendees") or "").split(";") if x.strip()],
                }
                for r in info.get("events", [])
            ]
            self.contacts: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "displayName": r["display_name"],
                    "givenName": r["given_name"],
                    "surname": r["surname"],
                    "email": r["email"],
                    "jobTitle": r["job_title"],
                    "companyName": r["company"],
                    "mobilePhone": r["mobile_phone"],
                }
                for r in info.get("contacts", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightOutlook')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"messages": self.messages}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _serialize_message(self, m):
        return {
            "id": m["id"],
            "subject": m["subject"],
            "bodyPreview": m["bodyPreview"],
            "importance": m["importance"],
            "isRead": m["isRead"],
            "receivedDateTime": m["receivedDateTime"],
            "from": {"emailAddress": {"name": m["from_name"], "address": m["from_address"]}},
            "toRecipients": [{"emailAddress": {"name": m["to_name"], "address": m["to_address"]}}],
            "body": {"contentType": m["contentType"], "content": m["bodyPreview"]},
        }

    def _serialize_event(self, e):
        return {
            "id": e["id"],
            "subject": e["subject"],
            "isAllDay": e["isAllDay"],
            "isOnlineMeeting": e["isOnlineMeeting"],
            "start": {"dateTime": e["start"], "timeZone": "UTC"},
            "end": {"dateTime": e["end"], "timeZone": "UTC"},
            "location": {"displayName": e["location"]},
            "organizer": {"emailAddress": {"name": e["organizer_name"], "address": e["organizer_address"]}},
            "attendees": [
                {"emailAddress": {"address": a}, "type": "required"} for a in e["attendees"]
            ],
        }

    def _serialize_contact(self, c):
        return {
            "id": c["id"],
            "displayName": c["displayName"],
            "givenName": c["givenName"],
            "surname": c["surname"],
            "emailAddresses": [{"address": c["email"], "name": c["displayName"]}],
            "jobTitle": c["jobTitle"],
            "companyName": c["companyName"],
            "mobilePhone": c["mobilePhone"],
        }

    # --- Messages ----------------------------------------------------------
    def list_messages(self, is_read: bool | None = None) -> Dict[str, Any]:
        msgs = list(self.messages)
        if is_read is not None:
            msgs = [m for m in msgs if m["isRead"] == is_read]
        msgs = sorted(msgs, key=lambda m: m["receivedDateTime"], reverse=True)
        return {"status": "ok", "output": {"value": [self._serialize_message(m) for m in msgs]}}

    def get_message(self, message_id: str) -> Dict[str, Any]:
        for m in self.messages:
            if m["id"] == message_id:
                return {"status": "ok", "output": self._serialize_message(m)}
        return {"status": "failed", "output": f"Message {message_id} not found"}

    def send_mail(self, subject: str | None, content: str | None, to_recipients: List[str],
                  content_type: str = "HTML") -> Dict[str, Any]:
        if not to_recipients:
            return {"status": "failed", "output": "message.toRecipients is required"}
        to_address = to_recipients[0]
        msg = {
            "id": "AAMkAGsent" + self.uuid(),
            "subject": subject or "(no subject)",
            "from_name": _ME_NAME,
            "from_address": _ME_ADDRESS,
            "to_name": to_address,
            "to_address": to_address,
            "bodyPreview": (content or "")[:255],
            "contentType": (content_type or "HTML").lower(),
            "isRead": True,
            "importance": "normal",
            "receivedDateTime": self._now(),
        }
        self.messages.append(msg)
        return {"status": "ok", "output": {"status": "accepted", "id": msg["id"]}}

    # --- Events ------------------------------------------------------------
    def list_events(self) -> Dict[str, Any]:
        events = sorted(self.events, key=lambda e: e["start"])
        return {"status": "ok", "output": {"value": [self._serialize_event(e) for e in events]}}

    # --- Contacts ----------------------------------------------------------
    def list_contacts(self) -> Dict[str, Any]:
        contacts = sorted(self.contacts, key=lambda c: c["displayName"])
        return {"status": "ok", "output": {"value": [self._serialize_contact(c) for c in contacts]}}


if __name__ == "__main__":
    s = OutlookSession(seed=12)
    print(s.list_messages())
    print(s.list_contacts())
