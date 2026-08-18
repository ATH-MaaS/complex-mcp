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


DEFAULT_CALENDARS = [
    {"cid": "cal_personal", "name": "Personal", "color": "#4285F4"},
    {"cid": "cal_work",     "name": "Work",     "color": "#DB4437"},
    {"cid": "cal_holidays", "name": "Holidays", "color": "#0F9D58"},
]

SEED_EVENTS = [
    ("Team standup",         "cal_work",     0,   9, 30,  30),
    ("Design review",        "cal_work",     1,  14,  0,  60),
    ("Sprint planning",      "cal_work",     3,  10,  0,  90),
    ("1:1 with manager",     "cal_work",     5,  15,  0,  30),
    ("Doctor appointment",   "cal_personal", 2,  11,  0,  60),
    ("Dinner with friends",  "cal_personal", 4,  19,  0, 120),
    ("Gym",                  "cal_personal", 6,   7,  0,  60),
    ("New Year",             "cal_holidays", 0,   0,  0,   0),
]


@dataclass
class Event:
    eid: str
    title: str
    calendar_id: str
    start: str
    end: str
    location: str = ""
    description: str = ""
    attendees: List[str] = field(default_factory=list)
    all_day: bool = False


@dataclass
class Calendar:
    cid: str
    name: str
    color: str


class CalendarSession:
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
            self.calendars: Dict[str, Calendar] = {
                c["cid"]: Calendar(**c) for c in DEFAULT_CALENDARS
            }
            self.events: Dict[str, Event] = {}
            self._seed_events()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightCalendar')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed_events(self) -> None:
        base = datetime(2026, 1, 5, 0, 0, 0)
        for title, cid, day_offset, hh, mm, dur_min in SEED_EVENTS:
            start = base + timedelta(days=day_offset, hours=hh, minutes=mm)
            end = start + timedelta(minutes=dur_min) if dur_min else start + timedelta(days=1)
            e = Event(
                eid=self.uuid(),
                title=title,
                calendar_id=cid,
                start=start.isoformat(timespec="minutes"),
                end=end.isoformat(timespec="minutes"),
                all_day=(dur_min == 0),
            )
            self.events[e.eid] = e

    def get_session_dict(self) -> Dict:
        return {
            "calendars": {cid: asdict(c) for cid, c in self.calendars.items()},
            "events": {eid: asdict(e) for eid, e in self.events.items()},
        }

    def _evt_summary(self, e: Event) -> Dict:
        return {
            "eid": e.eid,
            "title": e.title,
            "calendar_id": e.calendar_id,
            "start": e.start,
            "end": e.end,
            "location": e.location,
            "all_day": e.all_day,
            "attendees": list(e.attendees),
        }

    def list_calendars(self) -> Dict:
        return {
            "status": "ok",
            "output": [asdict(c) for c in self.calendars.values()],
        }

    def create_calendar(self, name: str, color: str = "#888888") -> Dict:
        cid = "cal_" + self.uuid()[:8]
        c = Calendar(cid=cid, name=name, color=color)
        self.calendars[cid] = c
        return {"status": "ok", "output": asdict(c)}

    def delete_calendar(self, cid: str) -> Dict:
        if cid not in self.calendars:
            return {"status": "failed", "output": f"calendar {cid} not found"}
        del self.calendars[cid]
        removed = [eid for eid, e in self.events.items() if e.calendar_id == cid]
        for eid in removed:
            del self.events[eid]
        return {"status": "ok", "output": {"cid": cid, "removed_events": len(removed)}}

    def list_events(self, calendar_id: Optional[str] = None,
                    start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        items = list(self.events.values())
        if calendar_id:
            items = [e for e in items if e.calendar_id == calendar_id]
        if start_date:
            items = [e for e in items if e.end >= start_date]
        if end_date:
            items = [e for e in items if e.start <= end_date]
        items.sort(key=lambda e: e.start)
        return {"status": "ok", "output": [self._evt_summary(e) for e in items]}

    def get_event(self, eid: str) -> Dict:
        e = self.events.get(eid)
        if not e:
            return {"status": "failed", "output": f"event {eid} not found"}
        return {"status": "ok", "output": asdict(e)}

    def create_event(self, title: str, start: str, end: str,
                     calendar_id: str = "cal_personal",
                     location: str = "", description: str = "",
                     attendees: Optional[List[str]] = None,
                     all_day: bool = False) -> Dict:
        if calendar_id not in self.calendars:
            return {"status": "failed", "output": f"calendar {calendar_id} not found"}
        e = Event(
            eid=self.uuid(),
            title=title,
            calendar_id=calendar_id,
            start=start,
            end=end,
            location=location,
            description=description,
            attendees=list(attendees) if attendees else [],
            all_day=all_day,
        )
        self.events[e.eid] = e
        return {"status": "ok", "output": self._evt_summary(e)}

    def update_event(self, eid: str, **fields) -> Dict:
        e = self.events.get(eid)
        if not e:
            return {"status": "failed", "output": f"event {eid} not found"}
        for k, v in fields.items():
            if v is None:
                continue
            if k in {"title", "start", "end", "location", "description", "calendar_id", "all_day"}:
                setattr(e, k, v)
            elif k == "attendees":
                e.attendees = list(v)
        return {"status": "ok", "output": self._evt_summary(e)}

    def delete_event(self, eid: str) -> Dict:
        e = self.events.pop(eid, None)
        if not e:
            return {"status": "failed", "output": f"event {eid} not found"}
        return {"status": "ok", "output": {"eid": eid, "deleted": True}}

    def move_event(self, eid: str, new_start: str, new_end: str) -> Dict:
        return self.update_event(eid, start=new_start, end=new_end)

    def search_events(self, query: str) -> Dict:
        q = query.lower()
        items = [e for e in self.events.values()
                 if q in e.title.lower() or q in e.description.lower() or q in e.location.lower()]
        items.sort(key=lambda e: e.start)
        return {"status": "ok", "output": [self._evt_summary(e) for e in items]}

    def list_upcoming(self, limit: int = 5, from_date: Optional[str] = None) -> Dict:
        anchor = from_date or datetime(2026, 1, 1).isoformat(timespec="minutes")
        items = [e for e in self.events.values() if e.start >= anchor]
        items.sort(key=lambda e: e.start)
        return {"status": "ok", "output": [self._evt_summary(e) for e in items[:limit]]}

    def list_today(self, today: Optional[str] = None) -> Dict:
        day = today or "2026-01-05"
        start = f"{day}T00:00"
        end = f"{day}T23:59"
        items = [e for e in self.events.values() if e.start >= start and e.start <= end]
        items.sort(key=lambda e: e.start)
        return {"status": "ok", "output": [self._evt_summary(e) for e in items]}

    def check_availability(self, start: str, end: str) -> Dict:
        conflicts = [self._evt_summary(e) for e in self.events.values()
                     if not (e.end <= start or e.start >= end)]
        return {
            "status": "ok",
            "output": {"free": len(conflicts) == 0, "conflicts": conflicts},
        }

    def find_free_slot(self, duration_min: int, start_date: str, end_date: str,
                       working_hours_start: int = 9, working_hours_end: int = 18) -> Dict:
        try:
            d0 = datetime.fromisoformat(start_date)
            d1 = datetime.fromisoformat(end_date)
        except Exception:
            return {"status": "failed", "output": "start_date/end_date must be ISO datetimes"}
        step = timedelta(minutes=30)
        need = timedelta(minutes=duration_min)
        cur = d0
        while cur + need <= d1:
            if working_hours_start <= cur.hour < working_hours_end:
                s = cur.isoformat(timespec="minutes")
                e = (cur + need).isoformat(timespec="minutes")
                busy = any(not (ev.end <= s or ev.start >= e) for ev in self.events.values())
                if not busy:
                    return {"status": "ok", "output": {"start": s, "end": e}}
            cur += step
        return {"status": "ok", "output": None}
