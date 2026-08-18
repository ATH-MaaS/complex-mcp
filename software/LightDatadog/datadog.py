import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import math
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
    return int(str(v).strip())


def _to_float(v) -> float:
    return float(str(v).strip())


def _split_tags(v) -> List[str]:
    if isinstance(v, list):
        return list(v)
    return [t for t in str(v).split(";") if t]


class DatadogSession:
    """Deterministic sandbox for the Datadog mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "datadog.yaml") as f:
                info = yaml.safe_load(f)

            self.monitors: List[Dict[str, Any]] = [
                {
                    **m,
                    "id": _to_int(m["id"]),
                    "priority": _to_int(m["priority"]),
                    "tags": _split_tags(m["tags"]),
                }
                for m in info.get("monitors", [])
            ]
            self.dashboards: List[Dict[str, Any]] = [
                {
                    **d,
                    "widget_count": _to_int(d["widget_count"]),
                    "is_read_only": _to_bool(d["is_read_only"]),
                }
                for d in info.get("dashboards", [])
            ]
            self.events: List[Dict[str, Any]] = [
                {
                    **e,
                    "id": _to_int(e["id"]),
                    "tags": _split_tags(e["tags"]),
                    "date_happened": _to_int(e["date_happened"]),
                }
                for e in info.get("events", [])
            ]
            self.hosts: List[Dict[str, Any]] = [
                {
                    **h,
                    "up": _to_bool(h["up"]),
                    "apps": _split_tags(h["apps"]),
                    "cpu_pct": _to_float(h["cpu_pct"]),
                    "mem_pct": _to_float(h["mem_pct"]),
                    "last_reported": _to_int(h["last_reported"]),
                }
                for h in info.get("hosts", [])
            ]
            self.metrics: List[Dict[str, Any]] = []
            for r in info.get("metrics", []):
                tags = r.get("tags") or []
                if isinstance(tags, str):
                    tags = _split_tags(tags)
                tag_string = ",".join(sorted(tags))
                self.metrics.append({
                    **r,
                    "tags": tags,
                    "_pk": f"{r['metric']}|{tag_string}",
                    "base_value": _to_float(r["base_value"]),
                    "amplitude": _to_float(r["amplitude"]),
                })
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightDatadog')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"monitors": self.monitors}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _match_metric(self, query):
        for m in self.metrics:
            if m["metric"] in query:
                return m
        return None

    # --- API methods -------------------------------------------------------
    def query_metrics(self, query: str, from_: int, to: int) -> Dict[str, Any]:
        try:
            from_ts = int(from_)
            to_ts = int(to)
        except (TypeError, ValueError):
            return {"status": "failed", "output": "from and to must be unix timestamps"}
        if to_ts <= from_ts:
            return {"status": "failed", "output": "to must be greater than from"}

        metric = self._match_metric(query)
        if not metric:
            return {"status": "ok", "output": {
                "status": "ok",
                "query": query,
                "from_date": from_ts * 1000,
                "to_date": to_ts * 1000,
                "series": [],
            }}

        step = max(60, (to_ts - from_ts) // 20)
        pointlist = []
        t = from_ts
        idx = 0
        while t <= to_ts:
            wave = math.sin(idx / 3.0)
            value = round(metric["base_value"] + metric["amplitude"] * wave, 4)
            pointlist.append([t * 1000, value])
            t += step
            idx += 1

        return {"status": "ok", "output": {
            "status": "ok",
            "query": query,
            "from_date": from_ts * 1000,
            "to_date": to_ts * 1000,
            "series": [{
                "metric": metric["metric"],
                "scope": metric["scope"],
                "unit": metric["unit"],
                "interval": step,
                "length": len(pointlist),
                "pointlist": pointlist,
            }],
        }}

    def list_monitors(self, overall_state: str | None = None) -> Dict[str, Any]:
        results = list(self.monitors)
        if overall_state:
            results = [m for m in results if m["overall_state"] == overall_state]
        return {"status": "ok", "output": results}

    def get_monitor(self, monitor_id: str) -> Dict[str, Any]:
        for m in self.monitors:
            if str(m["id"]) == str(monitor_id):
                return {"status": "ok", "output": m}
        return {"status": "failed", "output": f"Monitor {monitor_id} not found"}

    def create_monitor(self, name: str, type: str, query: str, message: str = "",
                        priority: int = 3, tags: List[str] | None = None) -> Dict[str, Any]:
        monitor = {
            "id": max((m["id"] for m in self.monitors), default=0) + 1,
            "name": name,
            "type": type,
            "query": query,
            "message": message or "",
            "overall_state": "OK",
            "priority": priority,
            "tags": tags or [],
            "created": self._now(),
            "modified": self._now(),
        }
        self.monitors.append(monitor)
        return {"status": "ok", "output": monitor}

    def update_monitor(self, monitor_id: str, name: str | None = None, query: str | None = None,
                       message: str | None = None, overall_state: str | None = None,
                       priority: int | None = None, tags: List[str] | None = None) -> Dict[str, Any]:
        for idx, m in enumerate(self.monitors):
            if str(m["id"]) == str(monitor_id):
                if name is not None:
                    self.monitors[idx]["name"] = name
                if query is not None:
                    self.monitors[idx]["query"] = query
                if message is not None:
                    self.monitors[idx]["message"] = message
                if overall_state is not None:
                    self.monitors[idx]["overall_state"] = overall_state
                if priority is not None:
                    self.monitors[idx]["priority"] = priority
                if tags is not None:
                    self.monitors[idx]["tags"] = tags
                self.monitors[idx]["modified"] = self._now()
                return {"status": "ok", "output": self.monitors[idx]}
        return {"status": "failed", "output": f"Monitor {monitor_id} not found"}

    def list_dashboards(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"dashboards": list(self.dashboards)}}

    def get_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        for d in self.dashboards:
            if d["id"] == dashboard_id:
                return {"status": "ok", "output": d}
        return {"status": "failed", "output": f"Dashboard {dashboard_id} not found"}

    def list_events(self, start: int | None = None, end: int | None = None) -> Dict[str, Any]:
        results = list(self.events)
        if start is not None:
            results = [e for e in results if e["date_happened"] >= int(start)]
        if end is not None:
            results = [e for e in results if e["date_happened"] <= int(end)]
        results.sort(key=lambda e: e["date_happened"], reverse=True)
        return {"status": "ok", "output": {"events": results}}

    def create_event(self, title: str, text: str, alert_type: str = "info",
                     priority: str = "normal", host: str | None = None,
                     tags: List[str] | None = None) -> Dict[str, Any]:
        event = {
            "id": max((e["id"] for e in self.events), default=0) + 1,
            "title": title,
            "text": text,
            "alert_type": alert_type,
            "priority": priority,
            "host": host or "",
            "tags": tags or [],
            "date_happened": int(datetime.strptime(self._now(), "%Y-%m-%d %H:%M:%S").timestamp()),
        }
        self.events.append(event)
        return {"status": "ok", "output": {"status": "ok", "event": event}}

    def list_hosts(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "host_list": list(self.hosts),
            "total_returned": len(self.hosts),
        }}


if __name__ == "__main__":
    s = DatadogSession(seed=12)
    print(s.list_monitors())
    print(s.list_hosts())
