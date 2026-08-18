from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightStravaSession
except ImportError:
    from software.LightStrava.session import LightStravaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightStrava")

session_dict: Dict[str, LightStravaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightStravaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.strava_session.get_session_dict(),
    }


@mcp.tool
async def get_athlete(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.get_athlete()


@mcp.tool
async def list_activities(session_id: str, before: int | None = None, after: int | None = None, page: int = 1, per_page: int = 30):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.list_activities(before, after, page, per_page)


@mcp.tool
async def athlete_stats(athlete_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.athlete_stats(athlete_id)


@mcp.tool
async def get_activity(activity_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.get_activity(activity_id)


@mcp.tool
async def update_activity(activity_id: int, session_id: str, name: str | None = None, type: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.update_activity(activity_id, name, type)


@mcp.tool
async def activity_kudos(activity_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.activity_kudos(activity_id)


@mcp.tool
async def get_segment(segment_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.strava_session.get_segment(segment_id)
