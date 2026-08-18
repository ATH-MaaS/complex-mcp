import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime, timezone

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _strict_int(v) -> int:
    return int(v)


def _strict_float(v) -> float:
    return float(v)


def _opt_int(v):
    if v is None or v == "":
        return None
    return int(v)


class StravaSession:
    """Deterministic sandbox for the Strava mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "strava.yaml") as f:
                info = yaml.safe_load(f)

            self.athlete: Dict[str, Any] = dict(info.get("athlete", {}))
            self.activities: List[Dict[str, Any]] = [
                {
                    "id": _strict_int(r["id"]),
                    "name": r["name"],
                    "type": r["type"],
                    "sport_type": r["type"],
                    "distance": _strict_float(r["distance"]),
                    "moving_time": _strict_int(r["moving_time"]),
                    "elapsed_time": _strict_int(r["elapsed_time"]),
                    "total_elevation_gain": _strict_float(r["total_elevation_gain"]),
                    "average_speed": _strict_float(r["average_speed"]),
                    "start_date": r["start_date"],
                    "kudos_count": _strict_int(r["kudos_count"]),
                    "segment_id": _opt_int(r.get("segment_id")),
                }
                for r in info.get("activities", [])
            ]
            self.segments: List[Dict[str, Any]] = [
                {
                    "id": _strict_int(r["id"]),
                    "name": r["name"],
                    "activity_type": r["activity_type"],
                    "distance": _strict_float(r["distance"]),
                    "average_grade": _strict_float(r["average_grade"]),
                    "maximum_grade": _strict_float(r["maximum_grade"]),
                    "elevation_high": _strict_float(r["elevation_high"]),
                    "elevation_low": _strict_float(r["elevation_low"]),
                    "climb_category": _strict_int(r["climb_category"]),
                    "city": r["city"],
                    "state": r["state"],
                }
                for r in info.get("segments", [])
            ]
            self.kudoers: List[Dict[str, Any]] = [
                {
                    "activity_id": _strict_int(r["activity_id"]),
                    "athlete_id": _strict_int(r["athlete_id"]),
                    "firstname": r["firstname"],
                    "lastname": r["lastname"],
                }
                for r in info.get("kudoers", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightStrava')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"activities": self.activities}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _epoch(self, iso) -> float:
        try:
            return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, TypeError):
            return 0.0

    # --- API methods -------------------------------------------------------
    def get_athlete(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.athlete}

    def list_activities(self, before: int | None = None, after: int | None = None,
                        page: int = 1, per_page: int = 30) -> Dict[str, Any]:
        acts = list(self.activities)
        if before is not None:
            acts = [a for a in acts if self._epoch(a["start_date"]) <= float(before)]
        if after is not None:
            acts = [a for a in acts if self._epoch(a["start_date"]) >= float(after)]
        acts.sort(key=lambda a: a["start_date"], reverse=True)
        page = max(1, page)
        per_page = max(1, per_page)
        start = (page - 1) * per_page
        return {"status": "ok", "output": acts[start: start + per_page]}

    def athlete_stats(self, athlete_id: int) -> Dict[str, Any]:
        if athlete_id != self.athlete["id"]:
            return {"status": "failed", "output": f"Athlete {athlete_id} not found"}

        def _totals(act_type):
            acts = [a for a in self.activities if a["type"] == act_type]
            return {
                "count": len(acts),
                "distance": round(sum(a["distance"] for a in acts), 1),
                "moving_time": sum(a["moving_time"] for a in acts),
                "elevation_gain": round(sum(a["total_elevation_gain"] for a in acts), 1),
            }

        return {"status": "ok", "output": {
            "all_run_totals": _totals("Run"),
            "all_ride_totals": _totals("Ride"),
            "all_swim_totals": _totals("Swim"),
        }}

    def get_activity(self, activity_id: int) -> Dict[str, Any]:
        a = next((x for x in self.activities if x["id"] == activity_id), None)
        if not a:
            return {"status": "failed", "output": f"Activity {activity_id} not found"}
        out = dict(a)
        out["athlete"] = {"id": self.athlete["id"]}
        return {"status": "ok", "output": out}

    def update_activity(self, activity_id: int, name: str | None = None,
                        type: str | None = None) -> Dict[str, Any]:
        for a in self.activities:
            if a["id"] == activity_id:
                if name is not None:
                    a["name"] = name
                if type is not None:
                    a["type"] = type
                    a["sport_type"] = type
                out = dict(a)
                out["athlete"] = {"id": self.athlete["id"]}
                return {"status": "ok", "output": out}
        return {"status": "failed", "output": f"Activity {activity_id} not found"}

    def activity_kudos(self, activity_id: int) -> Dict[str, Any]:
        if not any(a["id"] == activity_id for a in self.activities):
            return {"status": "failed", "output": f"Activity {activity_id} not found"}
        return {"status": "ok", "output": [
            {"firstname": k["firstname"], "lastname": k["lastname"]}
            for k in self.kudoers if k["activity_id"] == activity_id
        ]}

    def get_segment(self, segment_id: int) -> Dict[str, Any]:
        s = next((x for x in self.segments if x["id"] == segment_id), None)
        if not s:
            return {"status": "failed", "output": f"Segment {segment_id} not found"}
        return {"status": "ok", "output": s}


if __name__ == "__main__":
    s = StravaSession(seed=12)
    print(s.get_athlete())
    print(s.list_activities())
