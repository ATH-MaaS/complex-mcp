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


def _strict_int(v) -> int:
    return int(v)


def _parse_props(raw) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    props: Dict[str, Any] = {}
    for pair in (raw or "").split(";"):
        if not pair:
            continue
        key, _, val = pair.partition("=")
        props[key] = val
    return props


class PosthogSession:
    """Deterministic sandbox for the PostHog mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "posthog.yaml") as f:
                info = yaml.safe_load(f)

            self.events: List[Dict[str, Any]] = [
                {
                    "id": e["id"],
                    "project_id": _strict_int(e["project_id"]),
                    "distinct_id": e["distinct_id"],
                    "event": e["event"],
                    "timestamp": e["timestamp"],
                    "properties": _parse_props(e.get("properties")),
                }
                for e in info.get("events", [])
            ]
            self.flags: List[Dict[str, Any]] = [
                {
                    "id": f["id"],
                    "project_id": _strict_int(f["project_id"]),
                    "key": f["key"],
                    "name": f["name"],
                    "active": _to_bool(f.get("active", False)),
                    "rollout_percentage": _strict_int(f["rollout_percentage"]),
                }
                for f in info.get("feature_flags", [])
            ]
            self.persons: List[Dict[str, Any]] = [
                {
                    "id": p["id"],
                    "project_id": _strict_int(p["project_id"]),
                    "distinct_id": p["distinct_id"],
                    "name": p["name"],
                    "email": p["email"],
                    "created_at": p["created_at"],
                }
                for p in info.get("persons", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPostHog')
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

    def _serialize_person(self, p) -> Dict[str, Any]:
        return {
            "id": p["id"],
            "distinct_ids": [p["distinct_id"]],
            "name": p["name"],
            "properties": {"email": p["email"], "name": p["name"]},
            "created_at": p["created_at"],
        }

    # --- API methods -------------------------------------------------------
    def capture(self, distinct_id: str | None = None, project_id: int | None = None,
                event: str | None = None, timestamp: str | None = None,
                properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        self.events.append({
            "id": f"evt_{len(self.events) + 1:05d}",
            "project_id": int(project_id or 1),
            "distinct_id": distinct_id,
            "event": event or "$pageview",
            "timestamp": timestamp or self._now(),
            "properties": properties or {},
        })
        return {"status": "ok", "output": {"status": 1}}

    def decide(self, distinct_id: str | None = None, project_id: int | None = None) -> Dict[str, Any]:
        pid = int(project_id or 1)
        flags = [f for f in self.flags if f["project_id"] == pid]
        enabled = {}
        for f in flags:
            enabled[f["key"]] = bool(f["active"] and f["rollout_percentage"] > 0)
        return {"status": "ok", "output": {
            "featureFlags": enabled,
            "distinctId": distinct_id,
        }}

    def list_events(self, project_id: int, event: str | None = None,
                    distinct_id: str | None = None) -> Dict[str, Any]:
        events = [e for e in self.events if e["project_id"] == int(project_id)]
        if event:
            events = [e for e in events if e["event"] == event]
        if distinct_id:
            events = [e for e in events if e["distinct_id"] == distinct_id]
        return {"status": "ok", "output": {"results": events, "count": len(events)}}

    def list_feature_flags(self, project_id: int) -> Dict[str, Any]:
        flags = [f for f in self.flags if f["project_id"] == int(project_id)]
        results = [
            {
                "id": f["id"],
                "key": f["key"],
                "name": f["name"],
                "active": f["active"],
                "rollout_percentage": f["rollout_percentage"],
            }
            for f in flags
        ]
        return {"status": "ok", "output": {"results": results, "count": len(results)}}

    def list_persons(self, project_id: int) -> Dict[str, Any]:
        persons = [p for p in self.persons if p["project_id"] == int(project_id)]
        results = [self._serialize_person(p) for p in persons]
        return {"status": "ok", "output": {"results": results, "count": len(results)}}


if __name__ == "__main__":
    s = PosthogSession(seed=12)
    print(s.list_events(1))
    print(s.list_feature_flags(1))
    print(s.decide(distinct_id="user_3001", project_id=1))
