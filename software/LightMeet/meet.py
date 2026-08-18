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


STATUSES = ("scheduled", "completed", "cancelled")

SEED_MEETINGS = [
    ("Kickoff: MCP benchmark",     "Kickoff for the new benchmark quarter.",   -5,  10,  0, 60,  "self", ["alice@example.com", "bob@example.com"],                 "completed"),
    ("1:1 with manager",           "Weekly one-on-one.",                       -1,  15,  0, 30,  "self", ["manager@example.com"],                                    "completed"),
    ("Sprint planning",            "Plan tickets for the next sprint.",         0,  10,  0, 90,  "self", ["alice@example.com", "carol@example.com"],                 "scheduled"),
    ("Design review: LightCRM",    "Review CRM data model and endpoints.",      2,  14,  0, 60,  "self", ["dan@example.com", "eve@example.com"],                     "scheduled"),
    ("Quarterly all-hands",        "Company-wide quarterly update.",            7,  16,  0, 60,  "self", ["all@example.com"],                                        "scheduled"),
]


@dataclass
class Meeting:
    mid: str
    title: str
    description: str
    start: str
    end: str
    host: str
    participants: List[str] = field(default_factory=list)
    meeting_link: str = ""
    notes: str = ""
    recording_url: str = ""
    transcript_text: str = ""
    status: str = "scheduled"


class MeetSession:
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
            self.meetings: Dict[str, Meeting] = {}
            self._today = datetime(2026, 1, 5)
            self._seed_meetings()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMeet')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed_meetings(self) -> None:
        for title, desc, day_offset, hh, mm, dur_min, host, parts, status in SEED_MEETINGS:
            start = self._today + timedelta(days=day_offset, hours=hh, minutes=mm)
            end = start + timedelta(minutes=dur_min)
            m = Meeting(
                mid=self.uuid(),
                title=title,
                description=desc,
                start=start.isoformat(timespec="minutes"),
                end=end.isoformat(timespec="minutes"),
                host=host,
                participants=list(parts),
                meeting_link=f"https://meet.example.com/{self.uuid()[:10]}",
                status=status,
            )
            self.meetings[m.mid] = m

    def get_session_dict(self) -> Dict:
        return {
            "meetings": {mid: asdict(m) for mid, m in self.meetings.items()},
        }

    def _meet_summary(self, m: Meeting) -> Dict:
        return {
            "mid": m.mid,
            "title": m.title,
            "start": m.start,
            "end": m.end,
            "host": m.host,
            "participants": list(m.participants),
            "status": m.status,
            "meeting_link": m.meeting_link,
        }

    def list_meetings(self, status: Optional[str] = None) -> Dict:
        items = list(self.meetings.values())
        if status:
            if status not in STATUSES:
                return {"status": "failed", "output": f"status must be one of {STATUSES}"}
            items = [m for m in items if m.status == status]
        items.sort(key=lambda m: m.start)
        return {"status": "ok", "output": [self._meet_summary(m) for m in items]}

    def get_meeting(self, mid: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        return {"status": "ok", "output": asdict(m)}

    def create_meeting(self, title: str, start: str, end: str,
                       description: str = "",
                       host: str = "self",
                       participants: Optional[List[str]] = None) -> Dict:
        m = Meeting(
            mid=self.uuid(),
            title=title,
            description=description,
            start=start,
            end=end,
            host=host,
            participants=list(participants) if participants else [],
            meeting_link=f"https://meet.example.com/{self.uuid()[:10]}",
            status="scheduled",
        )
        self.meetings[m.mid] = m
        return {"status": "ok", "output": self._meet_summary(m)}

    def update_meeting(self, mid: str,
                       title: Optional[str] = None,
                       description: Optional[str] = None,
                       start: Optional[str] = None,
                       end: Optional[str] = None,
                       host: Optional[str] = None,
                       notes: Optional[str] = None,
                       participants: Optional[List[str]] = None) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        for k, v in {
            "title": title, "description": description, "start": start,
            "end": end, "host": host, "notes": notes,
        }.items():
            if v is not None:
                setattr(m, k, v)
        if participants is not None:
            m.participants = list(participants)
        return {"status": "ok", "output": self._meet_summary(m)}

    def cancel_meeting(self, mid: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        m.status = "cancelled"
        return {"status": "ok", "output": self._meet_summary(m)}

    def list_upcoming(self, days: int = 7, today: Optional[str] = None) -> Dict:
        anchor = datetime.fromisoformat(today) if today else self._today
        horizon = anchor + timedelta(days=days)
        a = anchor.isoformat(timespec="minutes")
        h = horizon.isoformat(timespec="minutes")
        items = [m for m in self.meetings.values()
                 if m.status == "scheduled" and m.start >= a and m.start <= h]
        items.sort(key=lambda m: m.start)
        return {"status": "ok", "output": [self._meet_summary(m) for m in items]}

    def list_today(self, today: Optional[str] = None) -> Dict:
        day = today or self._today.date().isoformat()
        start = f"{day}T00:00"
        end = f"{day}T23:59"
        items = [m for m in self.meetings.values() if m.start >= start and m.start <= end]
        items.sort(key=lambda m: m.start)
        return {"status": "ok", "output": [self._meet_summary(m) for m in items]}

    def list_past(self, today: Optional[str] = None) -> Dict:
        anchor = today or self._today.isoformat(timespec="minutes")
        items = [m for m in self.meetings.values() if m.end < anchor]
        items.sort(key=lambda m: m.start, reverse=True)
        return {"status": "ok", "output": [self._meet_summary(m) for m in items]}

    def add_participant(self, mid: str, email: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        if email not in m.participants:
            m.participants.append(email)
        return {"status": "ok", "output": self._meet_summary(m)}

    def remove_participant(self, mid: str, email: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        if email in m.participants:
            m.participants.remove(email)
        return {"status": "ok", "output": self._meet_summary(m)}

    def generate_recording_link(self, mid: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        m.recording_url = f"https://meet.example.com/recording/{self.uuid()[:12]}"
        return {"status": "ok", "output": {"mid": mid, "recording_url": m.recording_url}}

    def set_transcript(self, mid: str, text: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        m.transcript_text = text
        return {"status": "ok", "output": {"mid": mid, "chars": len(text)}}

    def get_transcript(self, mid: str) -> Dict:
        m = self.meetings.get(mid)
        if not m:
            return {"status": "failed", "output": f"meeting {mid} not found"}
        return {"status": "ok", "output": {"mid": mid, "transcript_text": m.transcript_text}}

    def search_meetings(self, query: str) -> Dict:
        q = query.lower()
        items = [m for m in self.meetings.values()
                 if q in m.title.lower() or q in m.description.lower()
                 or q in m.notes.lower() or q in m.transcript_text.lower()]
        items.sort(key=lambda m: m.start)
        return {"status": "ok", "output": [self._meet_summary(m) for m in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in STATUSES}
        with_recording = 0
        with_transcript = 0
        for m in self.meetings.values():
            by_status[m.status] = by_status.get(m.status, 0) + 1
            if m.recording_url:
                with_recording += 1
            if m.transcript_text:
                with_transcript += 1
        return {
            "status": "ok",
            "output": {
                "total": len(self.meetings),
                "by_status": by_status,
                "with_recording": with_recording,
                "with_transcript": with_transcript,
            },
        }
