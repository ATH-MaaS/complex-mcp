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


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    return int(v)


def _to_float(v) -> float:
    return float(v)


class EventbriteSession:
    """Deterministic sandbox for the Eventbrite mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "eventbrite.yaml") as f:
                info = yaml.safe_load(f)

            self.organizations: List[Dict[str, Any]] = list(info.get("organizations", []))
            self.events: List[Dict[str, Any]] = [
                {
                    **e,
                    "capacity": _to_int(e["capacity"]),
                    "is_free": _to_bool(e["is_free"]),
                    "online_event": _to_bool(e["online_event"]),
                }
                for e in info.get("events", [])
            ]
            self.venues: List[Dict[str, Any]] = [
                {
                    **v,
                    "latitude": _to_float(v["latitude"]),
                    "longitude": _to_float(v["longitude"]),
                }
                for v in info.get("venues", [])
            ]
            self.ticket_classes: List[Dict[str, Any]] = [
                {
                    **t,
                    "quantity_total": _to_int(t["quantity_total"]),
                    "quantity_sold": _to_int(t["quantity_sold"]),
                    "cost": _to_int(t["cost"]),
                    "fee": _to_int(t["fee"]),
                    "free": _to_bool(t["free"]),
                }
                for t in info.get("ticket_classes", [])
            ]
            self.attendees: List[Dict[str, Any]] = [
                {**a, "checked_in": _to_bool(a["checked_in"])} for a in info.get("attendees", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightEventbrite')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"events": self.events, "attendees": self.attendees}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix) -> str:
        return f"{prefix}-{self.uuid()}"

    def _serialize_event(self, e):
        venue = next((v for v in self.venues if v["id"] == e["venue_id"]), None)
        return {
            **e,
            "name": {"text": e["name"], "html": f"<p>{e['name']}</p>"},
            "summary": e["summary"],
            "start": {"timezone": e["timezone"], "utc": e["start_utc"]},
            "end": {"timezone": e["timezone"], "utc": e["end_utc"]},
            "venue": venue,
        }

    # --- Organizations -----------------------------------------------------
    def list_organizations(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "organizations": self.organizations,
            "pagination": {"object_count": len(self.organizations)},
        }}

    def get_organization(self, org_id: str) -> Dict[str, Any]:
        for o in self.organizations:
            if o["id"] == org_id:
                return {"status": "ok", "output": o}
        return {"status": "failed", "output": f"Organization {org_id} not found"}

    # --- Events ------------------------------------------------------------
    def list_events(self, organization_id: str | None = None, status: str | None = None,
                    q: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        results = list(self.events)
        if organization_id:
            results = [e for e in results if e["organization_id"] == organization_id]
        if status:
            results = [e for e in results if e["status"].lower() == status.lower()]
        if q:
            ql = q.lower()
            results = [e for e in results if ql in e["name"].lower() or ql in e["summary"].lower()]
        results.sort(key=lambda e: e["start_utc"])
        return {"status": "ok", "output": {
            "events": [self._serialize_event(e) for e in results[:page_size]],
            "pagination": {"object_count": len(results)},
        }}

    def search_events(self, q: str | None = None, status: str | None = None,
                      page_size: int = 50) -> Dict[str, Any]:
        return self.list_events(q=q, status=status, page_size=page_size)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        for e in self.events:
            if e["id"] == event_id:
                return {"status": "ok", "output": self._serialize_event(e)}
        return {"status": "failed", "output": f"Event {event_id} not found"}

    def create_event(self, organization_id: str, name: str, summary: str, start_utc: str,
                     end_utc: str, timezone: str = "America/Los_Angeles", venue_id: str | None = None,
                     capacity: int = 50, is_free: bool = True, online_event: bool = False) -> Dict[str, Any]:
        if not any(o["id"] == organization_id for o in self.organizations):
            return {"status": "failed", "output": f"Organization {organization_id} not found"}
        event = {
            "id": self._new_id("evt"),
            "organization_id": organization_id,
            "name": name,
            "summary": summary,
            "status": "draft",
            "start_utc": start_utc,
            "end_utc": end_utc,
            "timezone": timezone,
            "venue_id": venue_id or "",
            "capacity": int(capacity),
            "is_free": bool(is_free),
            "online_event": bool(online_event),
            "url": "",
            "created": self._now(),
        }
        self.events.append(event)
        return {"status": "ok", "output": self._serialize_event(event)}

    def publish_event(self, event_id: str) -> Dict[str, Any]:
        for i, e in enumerate(self.events):
            if e["id"] == event_id:
                if not any(t["event_id"] == event_id for t in self.ticket_classes):
                    return {"status": "failed", "output": "Event needs at least one ticket class before publish"}
                self.events[i]["status"] = "live"
                return {"status": "ok", "output": self._serialize_event(self.events[i])}
        return {"status": "failed", "output": f"Event {event_id} not found"}

    def cancel_event(self, event_id: str) -> Dict[str, Any]:
        for i, e in enumerate(self.events):
            if e["id"] == event_id:
                self.events[i]["status"] = "canceled"
                return {"status": "ok", "output": self._serialize_event(self.events[i])}
        return {"status": "failed", "output": f"Event {event_id} not found"}

    # --- Venues ------------------------------------------------------------
    def list_venues(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"venues": self.venues}}

    def get_venue(self, venue_id: str) -> Dict[str, Any]:
        for v in self.venues:
            if v["id"] == venue_id:
                return {"status": "ok", "output": v}
        return {"status": "failed", "output": f"Venue {venue_id} not found"}

    # --- Ticket classes ----------------------------------------------------
    def list_ticket_classes(self, event_id: str) -> Dict[str, Any]:
        if not any(e["id"] == event_id for e in self.events):
            return {"status": "failed", "output": f"Event {event_id} not found"}
        classes = [t for t in self.ticket_classes if t["event_id"] == event_id]
        return {"status": "ok", "output": {"ticket_classes": classes}}

    def create_ticket_class(self, event_id: str, name: str, quantity_total: int,
                            cost: int = 0, free: bool = True) -> Dict[str, Any]:
        if not any(e["id"] == event_id for e in self.events):
            return {"status": "failed", "output": f"Event {event_id} not found"}
        tc = {
            "id": self._new_id("tc"),
            "event_id": event_id,
            "name": name,
            "quantity_total": int(quantity_total),
            "quantity_sold": 0,
            "cost": int(cost),
            "fee": int(cost * 0.10) if cost else 0,
            "free": bool(free) or cost == 0,
            "sales_start": self._now(),
            "sales_end": self._now(),
        }
        self.ticket_classes.append(tc)
        return {"status": "ok", "output": tc}

    # --- Attendees ---------------------------------------------------------
    def list_attendees(self, event_id: str, status: str | None = None,
                       checked_in: bool | None = None) -> Dict[str, Any]:
        if not any(e["id"] == event_id for e in self.events):
            return {"status": "failed", "output": f"Event {event_id} not found"}
        results = [a for a in self.attendees if a["event_id"] == event_id]
        if status:
            results = [a for a in results if a["status"].lower() == status.lower()]
        if checked_in is not None:
            results = [a for a in results if a["checked_in"] is bool(checked_in)]
        return {"status": "ok", "output": {
            "attendees": results,
            "pagination": {"object_count": len(results)},
        }}

    def register_attendee(self, event_id: str, ticket_class_id: str, name: str,
                          email: str) -> Dict[str, Any]:
        if not any(e["id"] == event_id for e in self.events):
            return {"status": "failed", "output": f"Event {event_id} not found"}
        tc = next((t for t in self.ticket_classes if t["id"] == ticket_class_id), None)
        if not tc or tc["event_id"] != event_id:
            return {"status": "failed", "output": f"Ticket class {ticket_class_id} not found for event {event_id}"}
        if tc["quantity_sold"] >= tc["quantity_total"]:
            return {"status": "failed", "output": "Ticket class is sold out"}
        attendee = {
            "id": self._new_id("att"),
            "event_id": event_id,
            "ticket_class_id": ticket_class_id,
            "name": name,
            "email": email,
            "status": "attending",
            "checked_in": False,
            "created": self._now(),
        }
        self.attendees.append(attendee)
        for i, t in enumerate(self.ticket_classes):
            if t["id"] == ticket_class_id:
                self.ticket_classes[i]["quantity_sold"] += 1
        return {"status": "ok", "output": attendee}

    def check_in_attendee(self, attendee_id: str) -> Dict[str, Any]:
        for i, a in enumerate(self.attendees):
            if a["id"] == attendee_id:
                self.attendees[i]["checked_in"] = True
                return {"status": "ok", "output": self.attendees[i]}
        return {"status": "failed", "output": f"Attendee {attendee_id} not found"}


if __name__ == "__main__":
    s = EventbriteSession(seed=12)
    print(s.list_organizations())
    print(s.list_events())
