import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime, timedelta

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


def _strict_float(v) -> float:
    return float(str(v).strip())


class MyfitnesspalSession:
    """Deterministic sandbox for the MyFitnessPal mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "myfitnesspal.yaml") as f:
                info = yaml.safe_load(f)

            self.foods: List[Dict[str, Any]] = self._coerce_foods(info.get("foods", []))
            self.diary_entries: List[Dict[str, Any]] = self._coerce_diary_entries(info.get("diary_entries", []))
            self.exercise_types: List[Dict[str, Any]] = self._coerce_exercise_types(info.get("exercise_types", []))
            self.exercise_log: List[Dict[str, Any]] = self._coerce_exercise_log(info.get("exercise_log", []))
            self.weight_log: List[Dict[str, Any]] = self._coerce_weight_log(info.get("weight_log", []))
            self.water_log: List[Dict[str, Any]] = self._coerce_water_log(info.get("water_log", []))
            self.user_profile: Dict[str, Any] = dict(info.get("user_profile", {}))
            self.scenario_user_profile: Dict[str, Any] = dict(info.get("myfitnesspal_user_profile", {}))

            self._next_entry_id = max((e["entry_id"] for e in self.diary_entries), default=0) + 1
            self._next_exercise_id = max((e["exercise_id"] for e in self.exercise_log), default=0) + 1
            self._next_weight_id = max((w["weight_id"] for w in self.weight_log), default=0) + 1
            self._next_water_id = max((w["water_id"] for w in self.water_log), default=0) + 1
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMyFitnessPal')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"diary_entries": self.diary_entries}

    # --- load + coerce -----------------------------------------------------
    def _coerce_foods(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "food_id": _strict_int(r["food_id"]),
                "calories": _strict_float(r["calories"]),
                "total_fat_g": _strict_float(r["total_fat_g"]),
                "saturated_fat_g": _strict_float(r["saturated_fat_g"]),
                "cholesterol_mg": _strict_float(r["cholesterol_mg"]),
                "sodium_mg": _strict_float(r["sodium_mg"]),
                "total_carbs_g": _strict_float(r["total_carbs_g"]),
                "dietary_fiber_g": _strict_float(r["dietary_fiber_g"]),
                "sugars_g": _strict_float(r["sugars_g"]),
                "protein_g": _strict_float(r["protein_g"]),
                "potassium_mg": _strict_float(r["potassium_mg"]),
                "is_verified": _to_bool(r["is_verified"]),
            })
        return out

    def _coerce_diary_entries(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "entry_id": _strict_int(r["entry_id"]),
                "food_id": _strict_int(r["food_id"]),
                "servings": _strict_float(r["servings"]),
                "calories": _strict_float(r["calories"]),
                "total_fat_g": _strict_float(r["total_fat_g"]),
                "saturated_fat_g": _strict_float(r["saturated_fat_g"]),
                "cholesterol_mg": _strict_float(r["cholesterol_mg"]),
                "sodium_mg": _strict_float(r["sodium_mg"]),
                "total_carbs_g": _strict_float(r["total_carbs_g"]),
                "dietary_fiber_g": _strict_float(r["dietary_fiber_g"]),
                "sugars_g": _strict_float(r["sugars_g"]),
                "protein_g": _strict_float(r["protein_g"]),
            })
        return out

    def _coerce_exercise_types(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "exercise_type_id": _strict_int(r["exercise_type_id"]),
                "calories_per_minute_low": _strict_float(r["calories_per_minute_low"]),
                "calories_per_minute_high": _strict_float(r["calories_per_minute_high"]),
                "met_value": _strict_float(r["met_value"]),
            })
        return out

    def _coerce_exercise_log(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "exercise_id": _strict_int(r["exercise_id"]),
                "exercise_type_id": _strict_int(r["exercise_type_id"]),
                "duration_minutes": _strict_int(r["duration_minutes"]),
                "calories_burned": _strict_int(r["calories_burned"]),
            })
        return out

    def _coerce_weight_log(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "weight_id": _strict_int(r["weight_id"]),
                "weight_lbs": _strict_float(r["weight_lbs"]),
            })
        return out

    def _coerce_water_log(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "water_id": _strict_int(r["water_id"]),
                "cups": _strict_int(r["cups"]),
            })
        return out

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _empty_totals(self):
        return {
            "calories": 0, "total_fat_g": 0, "saturated_fat_g": 0,
            "cholesterol_mg": 0, "sodium_mg": 0, "total_carbs_g": 0,
            "dietary_fiber_g": 0, "sugars_g": 0, "protein_g": 0,
        }

    def _compute_totals(self, entries):
        totals = self._empty_totals()
        for e in entries:
            totals["calories"] += e["calories"]
            totals["total_fat_g"] += e["total_fat_g"]
            totals["saturated_fat_g"] += e["saturated_fat_g"]
            totals["cholesterol_mg"] += e["cholesterol_mg"]
            totals["sodium_mg"] += e["sodium_mg"]
            totals["total_carbs_g"] += e["total_carbs_g"]
            totals["dietary_fiber_g"] += e["dietary_fiber_g"]
            totals["sugars_g"] += e["sugars_g"]
            totals["protein_g"] += e["protein_g"]
        for k in totals:
            totals[k] = round(totals[k], 1)
        return totals

    # --- User Profile ------------------------------------------------------
    def get_user_profile(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"type": "user_profile", "user_profile": self.user_profile}}

    def get_scenario_user_profile(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.scenario_user_profile}

    def update_user_profile(self, display_name: str | None = None, daily_calorie_goal: int | None = None,
                            activity_level: str | None = None, current_weight_lbs: float | None = None,
                            goal_weight_lbs: float | None = None,
                            weekly_weight_goal_lbs: float | None = None) -> Dict[str, Any]:
        data = {}
        if display_name is not None:
            data["display_name"] = display_name
        if daily_calorie_goal is not None:
            data["daily_calorie_goal"] = daily_calorie_goal
        if activity_level is not None:
            data["activity_level"] = activity_level
        if current_weight_lbs is not None:
            data["current_weight_lbs"] = current_weight_lbs
        if goal_weight_lbs is not None:
            data["goal_weight_lbs"] = goal_weight_lbs
        if weekly_weight_goal_lbs is not None:
            data["weekly_weight_goal_lbs"] = weekly_weight_goal_lbs
        updatable = {
            "display_name", "daily_calorie_goal", "activity_level",
            "current_weight_lbs", "goal_weight_lbs", "weekly_weight_goal_lbs",
        }
        for k, v in data.items():
            if k in updatable:
                self.user_profile[k] = v
        return {"status": "ok", "output": {"type": "user_profile", "user_profile": self.user_profile}}

    # --- Goals -------------------------------------------------------------
    def get_goals(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "type": "goals",
            "goals": {
                "daily_calorie_goal": self.user_profile["daily_calorie_goal"],
                "macro_goals": self.user_profile["macro_goals"],
                "nutrient_goals": self.user_profile["nutrient_goals"],
                "weekly_weight_goal_lbs": self.user_profile["weekly_weight_goal_lbs"],
                "goal_weight_lbs": self.user_profile["goal_weight_lbs"],
            },
        }}

    def update_goals(self, daily_calorie_goal: int | None = None, macro_goals: Dict[str, Any] | None = None,
                     goal_weight_lbs: float | None = None,
                     weekly_weight_goal_lbs: float | None = None) -> Dict[str, Any]:
        if daily_calorie_goal is not None:
            self.user_profile["daily_calorie_goal"] = int(daily_calorie_goal)
            self.user_profile["nutrient_goals"]["calories"] = int(daily_calorie_goal)
        if macro_goals is not None:
            self.user_profile["macro_goals"].update({k: v for k, v in macro_goals.items() if v is not None})
        if weekly_weight_goal_lbs is not None:
            self.user_profile["weekly_weight_goal_lbs"] = float(weekly_weight_goal_lbs)
        if goal_weight_lbs is not None:
            self.user_profile["goal_weight_lbs"] = float(goal_weight_lbs)
        return self.get_goals()

    # --- Food Database -----------------------------------------------------
    def search_foods(self, q: str | None = None, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.foods)
        if q:
            q_l = q.lower()
            results = [f for f in results if q_l in f["food_name"].lower() or q_l in f.get("brand", "").lower()]
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "foods",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_food(self, food_id: int) -> Dict[str, Any]:
        for f in self.foods:
            if f["food_id"] == food_id:
                return {"status": "ok", "output": {"type": "food", "food": f}}
        return {"status": "failed", "output": f"Food {food_id} not found"}

    # --- Food Diary --------------------------------------------------------
    def get_diary(self, date: str, meal: str | None = None) -> Dict[str, Any]:
        entries = [e for e in self.diary_entries if e["date"] == date]
        if meal:
            entries = [e for e in entries if e["meal"].lower() == meal.lower()]

        if not entries and not any(e["date"] == date for e in self.diary_entries):
            return {"status": "ok", "output": {
                "type": "diary",
                "date": date,
                "meals": {"Breakfast": [], "Lunch": [], "Dinner": [], "Snacks": []},
                "totals": self._empty_totals(),
            }}

        meals = {"Breakfast": [], "Lunch": [], "Dinner": [], "Snacks": []}
        for e in entries:
            slot = e["meal"]
            if slot in meals:
                meals[slot].append(e)

        totals = self._compute_totals(entries)
        return {"status": "ok", "output": {
            "type": "diary",
            "date": date,
            "meals": meals,
            "totals": totals,
        }}

    def get_diary_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        entries = [e for e in self.diary_entries if start_date <= e["date"] <= end_date]
        dates = sorted(set(e["date"] for e in entries))
        days = []
        for d in dates:
            day_entries = [e for e in entries if e["date"] == d]
            meals = {"Breakfast": [], "Lunch": [], "Dinner": [], "Snacks": []}
            for e in day_entries:
                slot = e["meal"]
                if slot in meals:
                    meals[slot].append(e)
            days.append({
                "date": d,
                "meals": meals,
                "totals": self._compute_totals(day_entries),
            })
        return {"status": "ok", "output": {
            "type": "diary_range",
            "start_date": start_date,
            "end_date": end_date,
            "count": len(days),
            "results": days,
        }}

    def create_diary_entry(self, date: str, meal: str, food_id: int, servings: float) -> Dict[str, Any]:
        data = {"date": date, "meal": meal, "food_id": food_id, "servings": servings}
        required = ["date", "meal", "food_id", "servings"]
        for f in required:
            if f not in data or data[f] is None:
                return {"status": "failed", "output": f"Missing required field: {f}"}

        food_id = int(data["food_id"])
        food = None
        for f in self.foods:
            if f["food_id"] == food_id:
                food = f
                break

        if not food:
            return {"status": "failed", "output": f"Food {food_id} not found in database"}

        servings = float(data["servings"])
        entry = {
            "entry_id": self._next_entry_id,
            "date": data["date"],
            "meal": data["meal"],
            "food_id": food_id,
            "food_name": food["food_name"],
            "brand": food.get("brand", ""),
            "serving_size": food["serving_size"],
            "serving_unit": food["serving_unit"],
            "servings": servings,
            "calories": round(food["calories"] * servings, 1),
            "total_fat_g": round(food["total_fat_g"] * servings, 1),
            "saturated_fat_g": round(food["saturated_fat_g"] * servings, 1),
            "cholesterol_mg": round(food["cholesterol_mg"] * servings, 1),
            "sodium_mg": round(food["sodium_mg"] * servings, 1),
            "total_carbs_g": round(food["total_carbs_g"] * servings, 1),
            "dietary_fiber_g": round(food["dietary_fiber_g"] * servings, 1),
            "sugars_g": round(food["sugars_g"] * servings, 1),
            "protein_g": round(food["protein_g"] * servings, 1),
        }
        self.diary_entries.append(entry)
        self._next_entry_id += 1
        return {"status": "ok", "output": {"type": "diary_entry", "diary_entry": entry}}

    def update_diary_entry(self, entry_id: int, servings: float | None = None,
                           meal: str | None = None) -> Dict[str, Any]:
        data = {}
        if servings is not None:
            data["servings"] = servings
        if meal is not None:
            data["meal"] = meal
        for i, entry in enumerate(self.diary_entries):
            if entry["entry_id"] == entry_id:
                if "servings" in data:
                    new_servings = float(data["servings"])
                    food_id = entry["food_id"]
                    food = None
                    for f in self.foods:
                        if f["food_id"] == food_id:
                            food = f
                            break
                    if food:
                        self.diary_entries[i]["servings"] = new_servings
                        self.diary_entries[i]["calories"] = round(food["calories"] * new_servings, 1)
                        self.diary_entries[i]["total_fat_g"] = round(food["total_fat_g"] * new_servings, 1)
                        self.diary_entries[i]["saturated_fat_g"] = round(food["saturated_fat_g"] * new_servings, 1)
                        self.diary_entries[i]["cholesterol_mg"] = round(food["cholesterol_mg"] * new_servings, 1)
                        self.diary_entries[i]["sodium_mg"] = round(food["sodium_mg"] * new_servings, 1)
                        self.diary_entries[i]["total_carbs_g"] = round(food["total_carbs_g"] * new_servings, 1)
                        self.diary_entries[i]["dietary_fiber_g"] = round(food["dietary_fiber_g"] * new_servings, 1)
                        self.diary_entries[i]["sugars_g"] = round(food["sugars_g"] * new_servings, 1)
                        self.diary_entries[i]["protein_g"] = round(food["protein_g"] * new_servings, 1)
                if "meal" in data:
                    self.diary_entries[i]["meal"] = data["meal"]
                return {"status": "ok", "output": {"type": "diary_entry", "diary_entry": self.diary_entries[i]}}
        return {"status": "failed", "output": f"Diary entry {entry_id} not found"}

    def delete_diary_entry(self, entry_id: int) -> Dict[str, Any]:
        for i, entry in enumerate(self.diary_entries):
            if entry["entry_id"] == entry_id:
                self.diary_entries.pop(i)
                return {"status": "ok", "output": {"type": "diary_entry", "deleted": True, "entry_id": entry_id}}
        return {"status": "failed", "output": f"Diary entry {entry_id} not found"}

    # --- Nutrition Summary -------------------------------------------------
    def get_daily_totals(self, date: str) -> Dict[str, Any]:
        entries = [e for e in self.diary_entries if e["date"] == date]
        if not entries:
            return {"status": "ok", "output": {
                "type": "daily_totals",
                "date": date,
                "totals": self._empty_totals(),
                "goal": self.user_profile["nutrient_goals"],
                "remaining": self.user_profile["nutrient_goals"].copy(),
            }}
        totals = self._compute_totals(entries)
        goal = self.user_profile["nutrient_goals"]
        remaining = {}
        for k in totals:
            if k in goal:
                remaining[k] = round(goal[k] - totals[k], 1)
        return {"status": "ok", "output": {
            "type": "daily_totals",
            "date": date,
            "totals": totals,
            "goal": goal,
            "remaining": remaining,
        }}

    def get_weekly_summary(self, end_date: str) -> Dict[str, Any]:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as exc:
            return {"status": "failed", "output": str(exc)}
        start = end - timedelta(days=6)
        start_str = start.strftime("%Y-%m-%d")

        days = []
        current = start
        while current <= end:
            d = current.strftime("%Y-%m-%d")
            entries = [e for e in self.diary_entries if e["date"] == d]
            totals = self._compute_totals(entries) if entries else self._empty_totals()
            days.append({"date": d, "totals": totals, "entry_count": len(entries)})
            current += timedelta(days=1)

        avg_calories = round(sum(d["totals"]["calories"] for d in days) / 7, 1)
        avg_protein = round(sum(d["totals"]["protein_g"] for d in days) / 7, 1)
        avg_carbs = round(sum(d["totals"]["total_carbs_g"] for d in days) / 7, 1)
        avg_fat = round(sum(d["totals"]["total_fat_g"] for d in days) / 7, 1)

        return {"status": "ok", "output": {
            "type": "weekly_summary",
            "start_date": start_str,
            "end_date": end_date,
            "averages": {
                "calories": avg_calories,
                "protein_g": avg_protein,
                "total_carbs_g": avg_carbs,
                "total_fat_g": avg_fat,
            },
            "days": days,
        }}

    def get_progress(self, days: int = 30) -> Dict[str, Any]:
        end = datetime.strptime("2025-04-28", "%Y-%m-%d")
        start = end - timedelta(days=days - 1)

        daily_data = []
        current = start
        while current <= end:
            d = current.strftime("%Y-%m-%d")
            entries = [e for e in self.diary_entries if e["date"] == d]
            totals = self._compute_totals(entries) if entries else self._empty_totals()

            exercises = [ex for ex in self.exercise_log if ex["date"] == d]
            exercise_cals = sum(ex["calories_burned"] for ex in exercises)

            daily_data.append({
                "date": d,
                "calories_consumed": totals["calories"],
                "calories_burned": exercise_cals,
                "net_calories": round(totals["calories"] - exercise_cals, 1),
                "protein_g": totals["protein_g"],
                "total_carbs_g": totals["total_carbs_g"],
                "total_fat_g": totals["total_fat_g"],
            })
            current += timedelta(days=1)

        return {"status": "ok", "output": {
            "type": "progress",
            "period_days": days,
            "calorie_goal": self.user_profile["daily_calorie_goal"],
            "results": daily_data,
        }}

    # --- Exercise Types ----------------------------------------------------
    def list_exercise_types(self, category: str | None = None, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.exercise_types)
        if category:
            results = [e for e in results if e["category"].lower() == category.lower()]
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "exercise_types",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_exercise_type(self, exercise_type_id: int) -> Dict[str, Any]:
        for e in self.exercise_types:
            if e["exercise_type_id"] == exercise_type_id:
                return {"status": "ok", "output": {"type": "exercise_type", "exercise_type": e}}
        return {"status": "failed", "output": f"Exercise type {exercise_type_id} not found"}

    # --- Exercise Log ------------------------------------------------------
    def list_exercises(self, start_date: str | None = None, end_date: str | None = None,
                       limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.exercise_log)
        if start_date:
            results = [e for e in results if e["date"] >= start_date]
        if end_date:
            results = [e for e in results if e["date"] <= end_date]

        results = sorted(results, key=lambda x: x["date"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "exercises",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_exercise(self, exercise_id: int) -> Dict[str, Any]:
        for e in self.exercise_log:
            if e["exercise_id"] == exercise_id:
                return {"status": "ok", "output": {"type": "exercise", "exercise": e}}
        return {"status": "failed", "output": f"Exercise {exercise_id} not found"}

    def create_exercise(self, date: str, exercise_type_id: int, duration_minutes: int,
                        calories_burned: int, notes: str | None = None) -> Dict[str, Any]:
        data = {
            "date": date, "exercise_type_id": exercise_type_id,
            "duration_minutes": duration_minutes, "calories_burned": calories_burned,
            "notes": notes,
        }
        required = ["date", "exercise_type_id", "duration_minutes", "calories_burned"]
        for f in required:
            if f not in data or data[f] is None:
                return {"status": "failed", "output": f"Missing required field: {f}"}

        exercise_type_id = int(data["exercise_type_id"])
        ex_type = None
        for e in self.exercise_types:
            if e["exercise_type_id"] == exercise_type_id:
                ex_type = e
                break

        if not ex_type:
            return {"status": "failed", "output": f"Exercise type {exercise_type_id} not found"}

        exercise = {
            "exercise_id": self._next_exercise_id,
            "date": data["date"],
            "exercise_type_id": exercise_type_id,
            "exercise_name": ex_type["exercise_name"],
            "duration_minutes": int(data["duration_minutes"]),
            "calories_burned": int(data["calories_burned"]),
            "notes": data.get("notes") or "",
        }
        self.exercise_log.append(exercise)
        self._next_exercise_id += 1
        return {"status": "ok", "output": {"type": "exercise", "exercise": exercise}}

    # --- Weight Log --------------------------------------------------------
    def list_weight_entries(self, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = sorted(self.weight_log, key=lambda x: x["date"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "weight_entries",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_weight_entry(self, weight_id: int) -> Dict[str, Any]:
        for w in self.weight_log:
            if w["weight_id"] == weight_id:
                return {"status": "ok", "output": {"type": "weight_entry", "weight_entry": w}}
        return {"status": "failed", "output": f"Weight entry {weight_id} not found"}

    def create_weight_entry(self, date: str, weight_lbs: float, notes: str | None = None) -> Dict[str, Any]:
        data = {"date": date, "weight_lbs": weight_lbs, "notes": notes}
        required = ["date", "weight_lbs"]
        for f in required:
            if f not in data or data[f] is None:
                return {"status": "failed", "output": f"Missing required field: {f}"}

        entry = {
            "weight_id": self._next_weight_id,
            "date": data["date"],
            "weight_lbs": float(data["weight_lbs"]),
            "notes": data.get("notes") or "",
        }
        self.weight_log.append(entry)
        self._next_weight_id += 1
        return {"status": "ok", "output": {"type": "weight_entry", "weight_entry": entry}}

    # --- Water Intake ------------------------------------------------------
    def get_water(self, date: str) -> Dict[str, Any]:
        for w in self.water_log:
            if w["date"] == date:
                return {"status": "ok", "output": {"type": "water", "water": w}}
        return {"status": "failed", "output": f"Water entry for {date} not found"}

    def create_water(self, date: str, cups: int, notes: str | None = None) -> Dict[str, Any]:
        data = {"date": date, "cups": cups, "notes": notes}
        required = ["date", "cups"]
        for f in required:
            if f not in data or data[f] is None:
                return {"status": "failed", "output": f"Missing required field: {f}"}

        for w in self.water_log:
            if w["date"] == data["date"]:
                return {"status": "failed", "output": f"Water entry for {data['date']} already exists. Use PUT to update."}

        entry = {
            "water_id": self._next_water_id,
            "date": data["date"],
            "cups": int(data["cups"]),
            "notes": data.get("notes") or "",
        }
        self.water_log.append(entry)
        self._next_water_id += 1
        return {"status": "ok", "output": {"type": "water", "water": entry}}

    def update_water(self, date: str, cups: int | None = None, notes: str | None = None) -> Dict[str, Any]:
        data = {}
        if cups is not None:
            data["cups"] = cups
        if notes is not None:
            data["notes"] = notes
        for i, w in enumerate(self.water_log):
            if w["date"] == date:
                if "cups" in data:
                    self.water_log[i]["cups"] = int(data["cups"])
                if "notes" in data:
                    self.water_log[i]["notes"] = data["notes"]
                return {"status": "ok", "output": {"type": "water", "water": self.water_log[i]}}
        return {"status": "failed", "output": f"Water entry for {date} not found"}


if __name__ == "__main__":
    s = MyfitnesspalSession(seed=12)
    print(s.get_user_profile())
    print(s.search_foods(q="chicken"))
