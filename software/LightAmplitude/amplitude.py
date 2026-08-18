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


def _parse_props(raw) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    for pair in (raw or "").split(";"):
        if not pair:
            continue
        key, _, val = pair.partition("=")
        props[key] = val
    return props


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class AmplitudeSession:
    """Deterministic sandbox for the Amplitude mock, ported from the FastAPI service.

    Covers the HTTP V2 event-upload API, the event segmentation chart API and the
    user-activity stream. State is loaded from the corpus at init; uploads mutate
    the in-memory events table so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "amplitude.yaml") as f:
                info = yaml.safe_load(f)

            self.events: List[Dict[str, Any]] = [
                {
                    "event_id": r["event_id"],
                    "user_id": r["user_id"],
                    "device_id": r["device_id"],
                    "event_type": r["event_type"],
                    "event_time": r["event_time"],
                    "event_properties": _parse_props(r.get("event_properties")),
                }
                for r in info.get("events", [])
            ]
            self.users: List[Dict[str, Any]] = list(info.get("users", []))
            self.segmentation: List[Dict[str, Any]] = [
                {
                    "event_type": r["event_type"],
                    "date": r["date"],
                    "count": _to_int(r.get("count")),
                }
                for r in info.get("segmentation", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAmplitude')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"events": self.events}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    # --- API methods -------------------------------------------------------
    def ingest(self, events: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        raw_events = events or []
        ingested = 0
        for ev in raw_events:
            self.events.append({
                "event_id": ev.get("insert_id") or f"ev_{len(self.events) + 1:06d}",
                "user_id": ev.get("user_id"),
                "device_id": ev.get("device_id"),
                "event_type": ev.get("event_type") or "unknown",
                "event_time": ev.get("time") or self._now(),
                "event_properties": ev.get("event_properties") or {},
            })
            ingested += 1
        return {"status": "ok", "output": {
            "code": 200,
            "events_ingested": ingested,
            "server_upload_time": self._now(),
        }}

    def segmentation(self, event: str | None = None, start: str | None = None,
                     end: str | None = None) -> Dict[str, Any]:
        rows = list(self.segmentation)
        if event:
            rows = [r for r in rows if r["event_type"] == event]
        if start:
            rows = [r for r in rows if r["date"] >= start]
        if end:
            rows = [r for r in rows if r["date"] <= end]
        by_event: Dict[str, Any] = {}
        for r in rows:
            by_event.setdefault(r["event_type"], []).append(r)
        series = []
        series_labels = []
        xvalues = sorted({r["date"] for r in rows})
        for et in sorted(by_event):
            by_date = {r["date"]: r["count"] for r in by_event[et]}
            series.append([by_date.get(d, 0) for d in xvalues])
            series_labels.append(et)
        return {"status": "ok", "output": {
            "series": series,
            "seriesLabels": series_labels,
            "xValues": xvalues,
        }}

    def user_activity(self, user: str) -> Dict[str, Any]:
        matched = next((u for u in self.users if u["user_id"] == user), None)
        if not matched:
            return {"status": "failed", "output": f"User {user} not found"}
        user_events = [e for e in self.events if e["user_id"] == user]
        user_events = sorted(user_events, key=lambda e: e["event_time"])
        return {"status": "ok", "output": {
            "userData": matched,
            "events": user_events,
        }}


if __name__ == "__main__":
    s = AmplitudeSession(seed=12)
    print(s.segmentation())
    print(s.user_activity("user_2001"))
