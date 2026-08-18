from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMyFitnessPalSession
except ImportError:
    from software.LightMyFitnessPal.session import LightMyFitnessPalSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightMyFitnessPal")

session_dict: Dict[str, LightMyFitnessPalSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMyFitnessPalSession(os_cfg=os_cfg, seed=seed)
	session_dict[session.session_id] = session
	logger.info(f"A new user logged in! [{session.session_id}]")
	return {
		"status": "ok",
		"session_id": session.session_id,
		"session_info": {
			"status": "ok",
			"output": {}
        }
    }


@mcp.tool
async def logout(session_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	del session_dict[session_id]
	logger.info(f"A user logged out! [{session_id}]")
	return {
        "status": "ok",
        "output": session.myfitnesspal_session.get_session_dict(),
    }


@mcp.tool
async def get_user_profile(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_user_profile()


@mcp.tool
async def get_scenario_user_profile(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_scenario_user_profile()


@mcp.tool
async def update_user_profile(session_id: str, display_name: str | None = None, daily_calorie_goal: int | None = None, activity_level: str | None = None, current_weight_lbs: float | None = None, goal_weight_lbs: float | None = None, weekly_weight_goal_lbs: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.update_user_profile(display_name, daily_calorie_goal, activity_level, current_weight_lbs, goal_weight_lbs, weekly_weight_goal_lbs)


@mcp.tool
async def get_goals(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_goals()


@mcp.tool
async def update_goals(session_id: str, daily_calorie_goal: int | None = None, macro_goals: Dict[str, Any] | None = None, goal_weight_lbs: float | None = None, weekly_weight_goal_lbs: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.update_goals(daily_calorie_goal, macro_goals, goal_weight_lbs, weekly_weight_goal_lbs)


@mcp.tool
async def search_foods(session_id: str, q: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.search_foods(q, limit, offset)


@mcp.tool
async def get_food(food_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_food(food_id)


@mcp.tool
async def get_diary(date: str, session_id: str, meal: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_diary(date, meal)


@mcp.tool
async def get_diary_range(start_date: str, end_date: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_diary_range(start_date, end_date)


@mcp.tool
async def create_diary_entry(date: str, meal: str, food_id: int, servings: float, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.create_diary_entry(date, meal, food_id, servings)


@mcp.tool
async def update_diary_entry(entry_id: int, session_id: str, servings: float | None = None, meal: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.update_diary_entry(entry_id, servings, meal)


@mcp.tool
async def delete_diary_entry(entry_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.delete_diary_entry(entry_id)


@mcp.tool
async def get_daily_totals(date: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_daily_totals(date)


@mcp.tool
async def get_weekly_summary(end_date: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_weekly_summary(end_date)


@mcp.tool
async def get_progress(session_id: str, days: int = 30):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_progress(days)


@mcp.tool
async def list_exercise_types(session_id: str, category: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.list_exercise_types(category, limit, offset)


@mcp.tool
async def get_exercise_type(exercise_type_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_exercise_type(exercise_type_id)


@mcp.tool
async def list_exercises(session_id: str, start_date: str | None = None, end_date: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.list_exercises(start_date, end_date, limit, offset)


@mcp.tool
async def get_exercise(exercise_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_exercise(exercise_id)


@mcp.tool
async def create_exercise(date: str, exercise_type_id: int, duration_minutes: int, calories_burned: int, session_id: str, notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.create_exercise(date, exercise_type_id, duration_minutes, calories_burned, notes)


@mcp.tool
async def list_weight_entries(session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.list_weight_entries(limit, offset)


@mcp.tool
async def get_weight_entry(weight_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_weight_entry(weight_id)


@mcp.tool
async def create_weight_entry(date: str, weight_lbs: float, session_id: str, notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.create_weight_entry(date, weight_lbs, notes)


@mcp.tool
async def get_water(date: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.get_water(date)


@mcp.tool
async def create_water(date: str, cups: int, session_id: str, notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.create_water(date, cups, notes)


@mcp.tool
async def update_water(date: str, session_id: str, cups: int | None = None, notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.myfitnesspal_session.update_water(date, cups, notes)
