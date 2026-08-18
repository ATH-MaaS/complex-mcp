from typing import Dict, List, Optional
from pathlib import Path
import random, sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


EXERCISE_KINDS = ("strength", "cardio", "flexibility")
PR_KINDS = ("max_weight", "max_reps", "best_time", "longest_distance")

SEED_EXERCISES = [
    ("Barbell Back Squat",  "legs",    "strength"),
    ("Bench Press",         "chest",   "strength"),
    ("Deadlift",            "back",    "strength"),
    ("Overhead Press",      "shoulders","strength"),
    ("Pull Up",             "back",    "strength"),
    ("Treadmill Run",       "cardio",  "cardio"),
    ("Cycling",             "cardio",  "cardio"),
    ("Yoga Flow",           "full_body","flexibility"),
]

SEED_WORKOUTS = [
    ("Push Day",  0,  60, "Chest+shoulders",
        [(1, 5, 60.0, 0.0, 0), (3, 8, 40.0, 0.0, 0)]),
    ("Pull Day",  2,  55, "Back focus",
        [(2, 5, 100.0, 0.0, 0), (4, 8, 0.0, 0.0, 0)]),
    ("Leg Day",   4,  70, "Heavy squats",
        [(0, 5, 80.0, 0.0, 0)]),
    ("Cardio",    6,  30, "Zone 2 run",
        [(5, 0, 0.0, 5.0, 1800)]),
]

SEED_PRS = [
    (0, "max_weight",       120.0),
    (1, "max_reps",         12.0),
    (5, "longest_distance", 10.0),
]

SEED_WEEKLY_STATS = [
    ("2025-12-29", 3, 165, 1400),
    ("2026-01-05", 4, 215, 1800),
]


@dataclass
class Exercise:
    exid: str
    name: str
    muscle_group: str
    kind: str


@dataclass
class WorkoutSet:
    exid: str
    reps: int = 0
    weight_kg: float = 0.0
    distance_km: float = 0.0
    duration_sec: int = 0


@dataclass
class Workout:
    wkid: str
    name: str
    date: str
    duration_min: int
    notes: str = ""
    sets: List[Dict] = field(default_factory=list)


@dataclass
class PersonalRecord:
    prid: str
    exid: str
    kind: str
    value: float
    achieved_at: str


@dataclass
class WeeklyStat:
    wsid: str
    week_start_date: str
    total_workouts: int
    total_duration_min: int
    calories_estimate: int


class FitnessSession:
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
            self._today = datetime(2026, 1, 5)
            self.exercises: Dict[str, Exercise] = {}
            self.workouts: Dict[str, Workout] = {}
            self.prs: Dict[str, PersonalRecord] = {}
            self.weekly_stats: Dict[str, WeeklyStat] = {}
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightFitness')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        seeded_ex: List[str] = []
        for name, mg, kind in SEED_EXERCISES:
            e = Exercise(exid=self.uuid(), name=name, muscle_group=mg, kind=kind)
            self.exercises[e.exid] = e
            seeded_ex.append(e.exid)

        for name, day_offset, dur, notes, sets in SEED_WORKOUTS:
            date = (self._today + timedelta(days=day_offset)).date().isoformat()
            wk_sets = []
            for idx, reps, wt, dist, dsec in sets:
                wk_sets.append(asdict(WorkoutSet(
                    exid=seeded_ex[idx], reps=reps,
                    weight_kg=wt, distance_km=dist, duration_sec=dsec,
                )))
            w = Workout(
                wkid=self.uuid(),
                name=name,
                date=date,
                duration_min=dur,
                notes=notes,
                sets=wk_sets,
            )
            self.workouts[w.wkid] = w

        for idx, kind, value in SEED_PRS:
            achieved = (self._today + timedelta(days=-idx)).isoformat(timespec="minutes")
            p = PersonalRecord(
                prid=self.uuid(),
                exid=seeded_ex[idx],
                kind=kind,
                value=value,
                achieved_at=achieved,
            )
            self.prs[p.prid] = p

        for wsd, tw, td, cal in SEED_WEEKLY_STATS:
            ws = WeeklyStat(
                wsid=self.uuid(),
                week_start_date=wsd,
                total_workouts=tw,
                total_duration_min=td,
                calories_estimate=cal,
            )
            self.weekly_stats[ws.wsid] = ws

    def get_session_dict(self) -> Dict:
        return {
            "exercises": {k: asdict(v) for k, v in self.exercises.items()},
            "workouts": {k: asdict(v) for k, v in self.workouts.items()},
            "prs": {k: asdict(v) for k, v in self.prs.items()},
            "weekly_stats": {k: asdict(v) for k, v in self.weekly_stats.items()},
        }

    def list_exercises(self, muscle_group: Optional[str] = None,
                       kind: Optional[str] = None) -> Dict:
        items = list(self.exercises.values())
        if muscle_group:
            items = [e for e in items if e.muscle_group == muscle_group]
        if kind:
            items = [e for e in items if e.kind == kind]
        items.sort(key=lambda e: e.name)
        return {"status": "ok", "output": [asdict(e) for e in items]}

    def get_exercise(self, exid: str) -> Dict:
        e = self.exercises.get(exid)
        if not e:
            return {"status": "failed", "output": f"exercise {exid} not found"}
        return {"status": "ok", "output": asdict(e)}

    def add_exercise(self, name: str, muscle_group: str, kind: str) -> Dict:
        if kind not in EXERCISE_KINDS:
            return {"status": "failed", "output": f"kind must be one of {EXERCISE_KINDS}"}
        e = Exercise(exid=self.uuid(), name=name, muscle_group=muscle_group, kind=kind)
        self.exercises[e.exid] = e
        return {"status": "ok", "output": asdict(e)}

    def list_workouts(self, start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> Dict:
        items = list(self.workouts.values())
        if start_date:
            items = [w for w in items if w.date >= start_date]
        if end_date:
            items = [w for w in items if w.date <= end_date]
        items.sort(key=lambda w: w.date)
        return {"status": "ok", "output": [asdict(w) for w in items]}

    def get_workout(self, wkid: str) -> Dict:
        w = self.workouts.get(wkid)
        if not w:
            return {"status": "failed", "output": f"workout {wkid} not found"}
        return {"status": "ok", "output": asdict(w)}

    def create_workout(self, name: str, date: str, duration_min: int,
                       sets: Optional[List[Dict]] = None, notes: str = "") -> Dict:
        wk_sets: List[Dict] = []
        for s in sets or []:
            exid = s.get("exid")
            if exid not in self.exercises:
                return {"status": "failed", "output": f"exercise {exid} not found"}
            wk_sets.append(asdict(WorkoutSet(
                exid=exid,
                reps=int(s.get("reps", 0)),
                weight_kg=float(s.get("weight_kg", 0.0)),
                distance_km=float(s.get("distance_km", 0.0)),
                duration_sec=int(s.get("duration_sec", 0)),
            )))
        w = Workout(
            wkid=self.uuid(),
            name=name,
            date=date,
            duration_min=duration_min,
            notes=notes,
            sets=wk_sets,
        )
        self.workouts[w.wkid] = w
        return {"status": "ok", "output": asdict(w)}

    def update_workout(self, wkid: str,
                       name: Optional[str] = None,
                       date: Optional[str] = None,
                       duration_min: Optional[int] = None,
                       notes: Optional[str] = None) -> Dict:
        w = self.workouts.get(wkid)
        if not w:
            return {"status": "failed", "output": f"workout {wkid} not found"}
        for k, v in {"name": name, "date": date,
                     "duration_min": duration_min, "notes": notes}.items():
            if v is not None:
                setattr(w, k, v)
        return {"status": "ok", "output": asdict(w)}

    def delete_workout(self, wkid: str) -> Dict:
        w = self.workouts.pop(wkid, None)
        if not w:
            return {"status": "failed", "output": f"workout {wkid} not found"}
        return {"status": "ok", "output": {"wkid": wkid, "deleted": True}}

    def add_set(self, wkid: str, exid: str, reps: int = 0,
                weight_kg: float = 0.0, distance_km: float = 0.0,
                duration_sec: int = 0) -> Dict:
        w = self.workouts.get(wkid)
        if not w:
            return {"status": "failed", "output": f"workout {wkid} not found"}
        if exid not in self.exercises:
            return {"status": "failed", "output": f"exercise {exid} not found"}
        s = WorkoutSet(
            exid=exid, reps=reps, weight_kg=weight_kg,
            distance_km=distance_km, duration_sec=duration_sec,
        )
        w.sets.append(asdict(s))
        return {"status": "ok", "output": asdict(w)}

    def list_prs(self, exid: Optional[str] = None) -> Dict:
        items = list(self.prs.values())
        if exid:
            items = [p for p in items if p.exid == exid]
        items.sort(key=lambda p: p.achieved_at, reverse=True)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def record_pr(self, exid: str, kind: str, value: float) -> Dict:
        if exid not in self.exercises:
            return {"status": "failed", "output": f"exercise {exid} not found"}
        if kind not in PR_KINDS:
            return {"status": "failed", "output": f"kind must be one of {PR_KINDS}"}
        p = PersonalRecord(
            prid=self.uuid(),
            exid=exid,
            kind=kind,
            value=float(value),
            achieved_at=self._now(),
        )
        self.prs[p.prid] = p
        return {"status": "ok", "output": asdict(p)}

    def list_weekly_stats(self, limit: int = 10) -> Dict:
        items = list(self.weekly_stats.values())
        items.sort(key=lambda s: s.week_start_date, reverse=True)
        return {"status": "ok", "output": [asdict(s) for s in items[:limit]]}

    def compute_weekly_stats(self, week_start_date: str) -> Dict:
        try:
            start = datetime.fromisoformat(week_start_date).date()
        except ValueError:
            return {"status": "failed", "output": "week_start_date must be ISO YYYY-MM-DD"}
        end = start + timedelta(days=7)
        total_workouts = 0
        total_duration = 0
        for w in self.workouts.values():
            try:
                d = datetime.fromisoformat(w.date).date()
            except ValueError:
                continue
            if start <= d < end:
                total_workouts += 1
                total_duration += int(w.duration_min or 0)
        cal_estimate = total_duration * 8
        ws = WeeklyStat(
            wsid=self.uuid(),
            week_start_date=start.isoformat(),
            total_workouts=total_workouts,
            total_duration_min=total_duration,
            calories_estimate=cal_estimate,
        )
        self.weekly_stats[ws.wsid] = ws
        return {"status": "ok", "output": asdict(ws)}

    def get_muscle_group_frequency(self, start_date: Optional[str] = None,
                                   end_date: Optional[str] = None) -> Dict:
        freq: Dict[str, int] = {}
        for w in self.workouts.values():
            if start_date and w.date < start_date:
                continue
            if end_date and w.date > end_date:
                continue
            for s in w.sets:
                e = self.exercises.get(s.get("exid", ""))
                if not e:
                    continue
                freq[e.muscle_group] = freq.get(e.muscle_group, 0) + 1
        return {"status": "ok", "output": freq}

    def search_exercises(self, query: str) -> Dict:
        q = query.lower()
        items = [e for e in self.exercises.values()
                 if q in e.name.lower() or q in e.muscle_group.lower() or q in e.kind.lower()]
        items.sort(key=lambda e: e.name)
        return {"status": "ok", "output": [asdict(e) for e in items]}

    def get_stats(self) -> Dict:
        by_kind: Dict[str, int] = {k: 0 for k in EXERCISE_KINDS}
        for e in self.exercises.values():
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        total_duration = sum(int(w.duration_min or 0) for w in self.workouts.values())
        return {
            "status": "ok",
            "output": {
                "exercises": len(self.exercises),
                "workouts": len(self.workouts),
                "prs": len(self.prs),
                "weekly_stats": len(self.weekly_stats),
                "total_workout_minutes": total_duration,
                "by_kind": by_kind,
            },
        }

    def get_calendar(self, month: str) -> Dict:
        try:
            year_s, mon_s = month.split("-")
            year, mon = int(year_s), int(mon_s)
        except Exception:
            return {"status": "failed", "output": "month must be 'YYYY-MM'"}
        days: Dict[str, List[Dict]] = {}
        for w in self.workouts.values():
            try:
                d = datetime.fromisoformat(w.date).date()
            except ValueError:
                continue
            if d.year == year and d.month == mon:
                key = d.isoformat()
                days.setdefault(key, []).append({
                    "wkid": w.wkid,
                    "name": w.name,
                    "duration_min": w.duration_min,
                })
        return {"status": "ok", "output": {"month": month, "days": days}}
