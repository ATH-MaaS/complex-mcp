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


def _parse_props(raw) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    props: Dict[str, Any] = {}
    for pair in (raw or "").split(";"):
        if not pair:
            continue
        key, _, val = pair.partition("=")
        props[key] = val
    return props


class SegmentSession:
    """Deterministic sandbox for the Segment mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "segment.yaml") as f:
                info = yaml.safe_load(f)

            self.events: List[Dict[str, Any]] = [
                {
                    "messageId": e["messageId"],
                    "type": e["type"],
                    "userId": (e.get("userId") or "") or None,
                    "event": (e.get("event") or "") or None,
                    "timestamp": e["timestamp"],
                    "properties": _parse_props(e.get("properties")),
                }
                for e in info.get("events", [])
            ]
            self.sources: List[Dict[str, Any]] = [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "slug": s["slug"],
                    "enabled": _to_bool(s.get("enabled", False)),
                    "type": s["type"],
                    "createdAt": s["created_at"],
                }
                for s in info.get("sources", [])
            ]
            self.destinations: List[Dict[str, Any]] = [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "slug": d["slug"],
                    "enabled": _to_bool(d.get("enabled", False)),
                    "sourceId": d["source_id"],
                    "createdAt": d["created_at"],
                }
                for d in info.get("destinations", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSegment')
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
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _new_message_id(self) -> str:
        return "msg_" + self.uuid()

    def _ingest(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        props = payload.get("properties") or payload.get("traits") or {}
        props = dict(props) if isinstance(props, dict) else _parse_props(props)
        entry = {
            "messageId": payload.get("messageId") or self._new_message_id(),
            "type": event_type,
            "userId": payload.get("userId") or payload.get("anonymousId"),
            "event": payload.get("event"),
            "timestamp": payload.get("timestamp") or self._now(),
            "properties": props,
        }
        if event_type == "page" and payload.get("name"):
            entry["properties"].setdefault("name", payload["name"])
        self.events.append(entry)
        return entry

    # --- Tracking API (writes) --------------------------------------------
    def track(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ingest("track", body or {})
        return {"status": "ok", "output": {"success": True}}

    def identify(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ingest("identify", body or {})
        return {"status": "ok", "output": {"success": True}}

    def page(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ingest("page", body or {})
        return {"status": "ok", "output": {"success": True}}

    def batch(self, body: Dict[str, Any]) -> Dict[str, Any]:
        items = (body or {}).get("batch") or []
        for item in items:
            self._ingest(item.get("type") or "track", item)
        return {"status": "ok", "output": {"success": True, "ingested": len(items)}}

    # --- Read-only convenience endpoints ----------------------------------
    def list_events(self, event_type: str | None = None, user_id: str | None = None) -> Dict[str, Any]:
        events = list(self.events)
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        if user_id:
            events = [e for e in events if e["userId"] == user_id]
        return {"status": "ok", "output": {"events": events, "count": len(events)}}

    def list_sources(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"sources": list(self.sources), "count": len(self.sources)}}

    def list_destinations(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"destinations": list(self.destinations), "count": len(self.destinations)}}


if __name__ == "__main__":
    s = SegmentSession(seed=12)
    print(s.list_sources())
    print(s.list_events(event_type="track"))
