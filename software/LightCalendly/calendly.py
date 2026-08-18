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

BASE_URI = "https://api.calendly.com"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _parse_qa(raw):
    out = []
    if not raw:
        return out
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair or "|" not in pair:
            continue
        q, a = pair.split("|", 1)
        out.append({"question": q, "answer": a})
    return out


class CalendlySession:
    """Deterministic sandbox for the Calendly mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "calendly.yaml") as f:
                info = yaml.safe_load(f)

            self.event_types: List[Dict[str, Any]] = [
                {
                    **e,
                    "duration": int(e.get("duration", 0)),
                    "active": _to_bool(e.get("active", False)),
                }
                for e in info.get("event_types", [])
            ]
            self.scheduled_events: List[Dict[str, Any]] = [
                {
                    **ev,
                    "canceled_reason": (str(ev.get("canceled_reason", "") or "") or None),
                }
                for ev in info.get("scheduled_events", [])
            ]
            self.invitees: List[Dict[str, Any]] = [
                {
                    **inv,
                    "questions_and_answers": _parse_qa(inv.get("questions_and_answers")),
                }
                for inv in info.get("invitees", [])
            ]
            self.availability: List[Dict[str, Any]] = list(info.get("availability", []))
            self.user: Dict[str, Any] = info.get("user", {})
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightCalendly')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"scheduled_events": self.scheduled_events, "invitees": self.invitees}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now().replace(" ", "T") + ".000000Z"

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_uuid(self) -> str:
        return self.uuid()

    def _user_uri(self, uuid_):
        return f"{BASE_URI}/users/{uuid_}"

    def _event_type_uri(self, uuid_):
        return f"{BASE_URI}/event_types/{uuid_}"

    def _event_uri(self, uuid_):
        return f"{BASE_URI}/scheduled_events/{uuid_}"

    def _invitee_uri(self, event_uuid, uuid_):
        return f"{BASE_URI}/scheduled_events/{event_uuid}/invitees/{uuid_}"

    def _strip_uri(self, value):
        # Accept either a bare uuid or a full Calendly URI; return the trailing segment.
        if not value:
            return value
        return value.rstrip("/").rsplit("/", 1)[-1]

    # --- serializers -------------------------------------------------------
    def _user_obj(self, u):
        return {
            "uri": self._user_uri(u["uuid"]),
            "name": u["name"],
            "slug": u["slug"],
            "email": u["email"],
            "scheduling_url": u["scheduling_url"],
            "timezone": u["timezone"],
            "current_organization": f"{BASE_URI}/organizations/{u['current_organization']}",
            "created_at": u["created_at"],
            "updated_at": u["updated_at"],
        }

    def _event_type_obj(self, e):
        return {
            "uri": self._event_type_uri(e["uuid"]),
            "name": e["name"],
            "slug": e["slug"],
            "duration": e["duration"],
            "kind": e["kind"],
            "color": e["color"],
            "active": e["active"],
            "description_plain": e["description"],
            "scheduling_url": e["scheduling_url"],
            "profile": {"owner": self._user_uri(e["owner"])},
            "created_at": e["created_at"],
        }

    def _event_obj(self, ev):
        return {
            "uri": self._event_uri(ev["uuid"]),
            "name": ev["name"],
            "status": ev["status"],
            "start_time": ev["start_time"],
            "end_time": ev["end_time"],
            "event_type": self._event_type_uri(ev["event_type"]),
            "location": {"type": ev["location_type"], "location": ev["location"]},
            "event_memberships": [{"user": self._user_uri(ev["owner"])}],
            "cancellation": ({"reason": ev["canceled_reason"], "canceler_type": "host"}
                             if ev["status"] == "canceled" and ev["canceled_reason"] else None),
            "created_at": ev["created_at"],
        }

    def _invitee_obj(self, inv):
        return {
            "uri": self._invitee_uri(inv["event"], inv["uuid"]),
            "name": inv["name"],
            "email": inv["email"],
            "status": inv["status"],
            "timezone": inv["timezone"],
            "event": self._event_uri(inv["event"]),
            "questions_and_answers": inv["questions_and_answers"],
            "created_at": inv["created_at"],
        }

    # --- API methods -------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"resource": self._user_obj(self.user)}}

    def list_event_types(self, user: str | None = None) -> Dict[str, Any]:
        owner = self._strip_uri(user) if user else None
        items = self.event_types
        if owner:
            items = [e for e in items if e["owner"] == owner]
        return {"status": "ok", "output": {
            "collection": [self._event_type_obj(e) for e in items],
            "pagination": {"count": len(items), "next_page": None},
        }}

    def get_event_type(self, uuid_: str) -> Dict[str, Any]:
        uuid_ = self._strip_uri(uuid_)
        for e in self.event_types:
            if e["uuid"] == uuid_:
                return {"status": "ok", "output": {"resource": self._event_type_obj(e)}}
        return {"status": "failed", "output": f"event type {uuid_} not found"}

    def list_scheduled_events(self, user: str | None = None, status: str | None = None) -> Dict[str, Any]:
        owner = self._strip_uri(user) if user else None
        items = self.scheduled_events
        if owner:
            items = [ev for ev in items if ev["owner"] == owner]
        if status:
            items = [ev for ev in items if ev["status"] == status]
        return {"status": "ok", "output": {
            "collection": [self._event_obj(ev) for ev in items],
            "pagination": {"count": len(items), "next_page": None},
        }}

    def get_scheduled_event(self, uuid_: str) -> Dict[str, Any]:
        uuid_ = self._strip_uri(uuid_)
        for ev in self.scheduled_events:
            if ev["uuid"] == uuid_:
                return {"status": "ok", "output": {"resource": self._event_obj(ev)}}
        return {"status": "failed", "output": f"scheduled event {uuid_} not found"}

    def list_invitees(self, uuid_: str) -> Dict[str, Any]:
        event_uuid = self._strip_uri(uuid_)
        if not any(ev["uuid"] == event_uuid for ev in self.scheduled_events):
            return {"status": "failed", "output": f"scheduled event {event_uuid} not found"}
        items = [inv for inv in self.invitees if inv["event"] == event_uuid]
        return {"status": "ok", "output": {
            "collection": [self._invitee_obj(inv) for inv in items],
            "pagination": {"count": len(items), "next_page": None},
        }}

    def book_event(self, event_type: str, start_time: str | None = None, end_time: str | None = None,
                   location_type: str = "zoom", location: str = "", invitee: Dict[str, Any] | None = None) -> Dict[str, Any]:
        event_type = self._strip_uri(event_type)
        et = next((e for e in self.event_types if e["uuid"] == event_type), None)
        if et is None:
            return {"status": "failed", "output": f"event type {event_type} not found"}

        uuid_ = f"sev-{self._new_uuid()}"
        now = self._now()
        event = {
            "uuid": uuid_,
            "owner": et["owner"],
            "event_type": event_type,
            "name": et["name"],
            "status": "active",
            "start_time": start_time if start_time is not None else now,
            "end_time": end_time if end_time is not None else now,
            "location_type": location_type if location_type is not None else "zoom",
            "location": location if location is not None else "",
            "created_at": now,
            "canceled_reason": None,
        }
        self.scheduled_events.append(event)

        invitee = invitee or {}
        if invitee.get("email"):
            self.invitees.append({
                "uuid": f"inv-{self._new_uuid()}",
                "event": uuid_,
                "name": invitee.get("name", ""),
                "email": invitee["email"],
                "status": "active",
                "timezone": invitee.get("timezone", self.user["timezone"]),
                "created_at": now,
                "questions_and_answers": [],
            })
        return {"status": "ok", "output": {"resource": self._event_obj(event)}}

    def cancel_event(self, uuid_: str, reason: str | None = None) -> Dict[str, Any]:
        uuid_ = self._strip_uri(uuid_)
        for ev in self.scheduled_events:
            if ev["uuid"] == uuid_:
                ev["status"] = "canceled"
                ev["canceled_reason"] = reason or "Canceled by host"
                for inv in self.invitees:
                    if inv["event"] == uuid_:
                        inv["status"] = "canceled"
                return {"status": "ok", "output": {"resource": {
                    "canceled_by": self.user["name"],
                    "reason": ev["canceled_reason"],
                    "canceler_type": "host",
                }}}
        return {"status": "failed", "output": f"scheduled event {uuid_} not found"}


if __name__ == "__main__":
    s = CalendlySession(seed=12)
    print(s.get_me())
    print(s.list_event_types())
