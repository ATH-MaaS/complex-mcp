import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from collections import defaultdict
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
    return int(str(v).strip())


class MixpanelSession:
    """Deterministic sandbox for the Mixpanel mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "mixpanel.yaml") as f:
                info = yaml.safe_load(f)

            self.events: List[Dict[str, Any]] = self._coerce_events(info.get("events", []))
            self.funnels: Dict[str, Any] = self._coerce_funnels(info.get("funnels", []))
            self.profiles: List[Dict[str, Any]] = self._coerce_profiles(info.get("profiles", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMixpanel')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"events": self.events}

    # --- load + coerce -----------------------------------------------------
    def _coerce_events(self, rows):
        out = []
        for r in rows:
            props = {k: r[k] for k in ("country", "plan", "platform", "utm_source") if r.get(k)}
            out.append({
                "event_id": r["event_id"],
                "event": r["event"],
                "distinct_id": r["distinct_id"],
                "time": r["time"],
                "properties": props,
            })
        return out

    def _coerce_funnels(self, rows):
        grouped = {}
        for r in rows:
            fid = r["funnel_id"]
            f = grouped.setdefault(fid, {"funnel_id": fid, "name": r["name"], "steps": []})
            f["steps"].append({
                "order": _strict_int(r["step_order"]),
                "event": r["step_event"],
                "count": _strict_int(r["count"]),
            })
        for f in grouped.values():
            f["steps"].sort(key=lambda s: s["order"])
        return grouped

    def _coerce_profiles(self, rows):
        out = []
        for r in rows:
            out.append({
                "distinct_id": r["distinct_id"],
                "properties": {
                    "$name": r["name"],
                    "$email": r["email"],
                    "country": r["country"],
                    "plan": r["plan"],
                    "total_events": _strict_int(r["total_events"]),
                    "$last_seen": r["last_seen"],
                },
            })
        return out

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _day(self, ts):
        return (ts or "")[:10]

    def _in_range(self, ts, from_date, to_date):
        d = self._day(ts)
        if from_date and d < from_date:
            return False
        if to_date and d > to_date:
            return False
        return True

    # --- API methods -------------------------------------------------------
    def track(self, event: str, distinct_id: str | None = None, time: str | None = None,
              properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not event:
            return {"status": "failed", "output": "event name is required"}
        record = {
            "event_id": f"evt-{self.uuid()}",
            "event": event,
            "distinct_id": distinct_id or "anonymous",
            "time": time or self._now(),
            "properties": dict(properties or {}),
        }
        self.events.append(record)
        return {"status": "ok", "output": {"status": 1, "event_id": record["event_id"]}}

    def events_counts(self, event: str | None = None, from_date: str | None = None,
                      to_date: str | None = None) -> Dict[str, Any]:
        wanted = set()
        if event:
            wanted = {e.strip() for e in event.split(",") if e.strip()}
        series = sorted({self._day(e["time"]) for e in self.events
                         if self._in_range(e["time"], from_date, to_date)})
        names = wanted or {e["event"] for e in self.events}
        values = {}
        for name in names:
            per_day = {d: 0 for d in series}
            for e in self.events:
                if e["event"] != name:
                    continue
                if not self._in_range(e["time"], from_date, to_date):
                    continue
                per_day[self._day(e["time"])] += 1
            values[name] = per_day
        return {"status": "ok", "output": {
            "data": {"series": series, "values": values},
            "legend_size": len(values),
        }}

    def funnels_list(self) -> Dict[str, Any]:
        return {"status": "ok", "output": [
            {"funnel_id": int(f["funnel_id"]), "name": f["name"]}
            for f in sorted(self.funnels.values(), key=lambda x: x["funnel_id"])
        ]}

    def funnel(self, funnel_id: int) -> Dict[str, Any]:
        f = self.funnels.get(str(funnel_id))
        if not f:
            return {"status": "failed", "output": f"Funnel {funnel_id} not found"}
        steps = f["steps"]
        top = steps[0]["count"] if steps else 0
        out_steps = []
        prev = None
        for s in steps:
            step_conv = round(s["count"] / prev, 4) if prev else 1.0
            overall = round(s["count"] / top, 4) if top else 0.0
            out_steps.append({
                "step_label": s["event"],
                "event": s["event"],
                "count": s["count"],
                "step_conv_ratio": step_conv,
                "overall_conv_ratio": overall,
            })
            prev = s["count"]
        return {"status": "ok", "output": {
            "funnel_id": int(f["funnel_id"]),
            "name": f["name"],
            "steps": out_steps,
            "analysis": {
                "completion": out_steps[-1]["count"] if out_steps else 0,
                "starting_amount": top,
                "conversion": out_steps[-1]["overall_conv_ratio"] if out_steps else 0.0,
            },
        }}

    def segmentation(self, event: str | None = None, from_date: str | None = None,
                     to_date: str | None = None, on: str | None = None) -> Dict[str, Any]:
        if not event:
            return {"status": "failed", "output": "event is required"}
        prop = (on or "").strip() or None
        series = sorted({self._day(e["time"]) for e in self.events
                         if e["event"] == event and self._in_range(e["time"], from_date, to_date)})
        values = defaultdict(lambda: {d: 0 for d in series})
        for e in self.events:
            if e["event"] != event:
                continue
            if not self._in_range(e["time"], from_date, to_date):
                continue
            bucket = e["properties"].get(prop, "$none") if prop else event
            values[bucket][self._day(e["time"])] += 1
        return {"status": "ok", "output": {
            "data": {"series": series, "values": {k: dict(v) for k, v in values.items()}}
        }}

    def engage(self, distinct_id: str | None = None, where: str | None = None,
               page_size: int = 50) -> Dict[str, Any]:
        results = list(self.profiles)
        if distinct_id:
            results = [p for p in results if p["distinct_id"] == distinct_id]
        if where:
            if "==" in where:
                key, _, val = where.partition("==")
                key = key.strip()
                val = val.strip().strip('"')
                results = [p for p in results if str(p["properties"].get(key)) == val]
        results = results[: max(1, page_size)]
        return {"status": "ok", "output": {
            "results": results,
            "page": 0,
            "page_size": page_size,
            "total": len(results),
        }}


if __name__ == "__main__":
    s = MixpanelSession(seed=12)
    print(s.funnels_list())
    print(s.events_counts())
