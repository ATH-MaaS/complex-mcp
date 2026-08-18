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


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _opt_str(v):
    s = "" if v is None else str(v)
    return s or None


class ZoomSession:
    """Deterministic sandbox for the Zoom API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "zoom.yaml") as f:
                info = yaml.safe_load(f)

            self.meetings: List[Dict[str, Any]] = [{
                **r,
                "id": _to_int(r.get("id")),
                "type": _to_int(r.get("type")),
                "duration": _to_int(r.get("duration")),
                "agenda": r.get("agenda") or "",
            } for r in info.get("meetings", [])]
            self.recordings: List[Dict[str, Any]] = [{
                **r,
                "meeting_id": _to_int(r.get("meeting_id")),
                "file_size": _to_int(r.get("file_size")),
            } for r in info.get("recordings", [])]
            self.registrants: List[Dict[str, Any]] = [{
                **r,
                "meeting_id": _to_int(r.get("meeting_id")),
                "join_time": _opt_str(r.get("join_time")),
            } for r in info.get("registrants", [])]
            self.user: Dict[str, Any] = dict(info.get("user", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightZoom')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"meetings": self.meetings}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _new_meeting_id(self):
        existing = {m["id"] for m in self.meetings}
        while True:
            mid = self.rng.randint(80000000000, 89999999999)
            if mid not in existing:
                return mid

    def _serialize_meeting(self, m):
        return {
            "id": m["id"],
            "host_id": m["host_id"],
            "topic": m["topic"],
            "type": m["type"],
            "status": m["status"],
            "start_time": m["start_time"],
            "duration": m["duration"],
            "timezone": m["timezone"],
            "agenda": m["agenda"],
            "join_url": m["join_url"],
            "created_at": m["created_at"],
        }

    # --- Users -------------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": dict(self.user)}

    # --- Meetings ----------------------------------------------------------
    def list_meetings(self, user_id: str, meeting_type: str = "scheduled", page_size: int = 30) -> Dict[str, Any]:
        if user_id != "me" and user_id != self.user["id"]:
            return {"status": "failed", "output": f"User {user_id} not found"}
        host = self.user["id"]
        meetings = [m for m in self.meetings if m["host_id"] == host]
        if meeting_type == "scheduled":
            meetings = [m for m in meetings if m["status"] == "waiting"]
        elif meeting_type == "previous_meetings":
            meetings = [m for m in meetings if m["status"] == "finished"]
        meetings = sorted(meetings, key=lambda m: m["start_time"])
        meetings = meetings[:page_size]
        return {"status": "ok", "output": {
            "page_count": 1,
            "page_size": page_size,
            "total_records": len(meetings),
            "meetings": [self._serialize_meeting(m) for m in meetings],
        }}

    def get_meeting(self, meeting_id: int) -> Dict[str, Any]:
        for m in self.meetings:
            if m["id"] == int(meeting_id):
                return {"status": "ok", "output": self._serialize_meeting(m)}
        return {"status": "failed", "output": {"error": f"Meeting {meeting_id} not found", "code": 3001}}

    def create_meeting(self, user_id: str, topic: str, start_time: str | None = None,
                       duration: int = 60, timezone: str = "UTC", agenda: str = "",
                       meeting_type: int = 2) -> Dict[str, Any]:
        if user_id != "me" and user_id != self.user["id"]:
            return {"status": "failed", "output": f"User {user_id} not found"}
        mid = self._new_meeting_id()
        meeting = {
            "id": mid,
            "host_id": self.user["id"],
            "topic": topic,
            "type": meeting_type,
            "status": "waiting",
            "start_time": start_time or self._now(),
            "duration": duration,
            "timezone": timezone,
            "agenda": agenda or "",
            "join_url": f"https://zoom.us/j/{mid}",
            "created_at": self._now(),
        }
        self.meetings.append(meeting)
        return {"status": "ok", "output": self._serialize_meeting(meeting)}

    def update_meeting(self, meeting_id: int, topic: str | None = None, start_time: str | None = None,
                       duration: int | None = None, agenda: str | None = None,
                       timezone: str | None = None) -> Dict[str, Any]:
        for m in self.meetings:
            if m["id"] == int(meeting_id):
                if topic is not None:
                    m["topic"] = topic
                if start_time is not None:
                    m["start_time"] = start_time
                if duration is not None:
                    m["duration"] = duration
                if agenda is not None:
                    m["agenda"] = agenda
                if timezone is not None:
                    m["timezone"] = timezone
                return {"status": "ok", "output": self._serialize_meeting(m)}
        return {"status": "failed", "output": {"error": f"Meeting {meeting_id} not found", "code": 3001}}

    def delete_meeting(self, meeting_id: int) -> Dict[str, Any]:
        for i, m in enumerate(self.meetings):
            if m["id"] == int(meeting_id):
                self.meetings.pop(i)
                return {"status": "ok", "output": {"deleted": True, "id": int(meeting_id)}}
        return {"status": "failed", "output": {"error": f"Meeting {meeting_id} not found", "code": 3001}}

    # --- Recordings --------------------------------------------------------
    def get_recordings(self, meeting_id: int) -> Dict[str, Any]:
        meeting = next((m for m in self.meetings if m["id"] == int(meeting_id)), None)
        if not meeting:
            return {"status": "failed", "output": {"error": f"Meeting {meeting_id} not found", "code": 3001}}
        files = [r for r in self.recordings if r["meeting_id"] == int(meeting_id)]
        if not files:
            return {"status": "failed", "output": {"error": f"No recordings for meeting {meeting_id}", "code": 3301}}
        total = sum(f["file_size"] for f in files)
        return {"status": "ok", "output": {
            "id": int(meeting_id),
            "uuid": f"uuid-{meeting_id}",
            "host_id": meeting["host_id"],
            "topic": meeting["topic"],
            "start_time": meeting["start_time"],
            "duration": meeting["duration"],
            "total_size": total,
            "recording_count": len(files),
            "recording_files": files,
        }}

    # --- Registrants -------------------------------------------------------
    def list_registrants(self, meeting_id: int, status: str = "approved") -> Dict[str, Any]:
        if not any(m["id"] == int(meeting_id) for m in self.meetings):
            return {"status": "failed", "output": {"error": f"Meeting {meeting_id} not found", "code": 3001}}
        regs = [r for r in self.registrants if r["meeting_id"] == int(meeting_id)]
        if status:
            regs = [r for r in regs if r["status"] == status]
        return {"status": "ok", "output": {
            "page_count": 1,
            "page_size": len(regs),
            "total_records": len(regs),
            "registrants": regs,
        }}


if __name__ == "__main__":
    s = ZoomSession(seed=12)
    print(s.get_me())
    print(s.list_meetings("me"))
