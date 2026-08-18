from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGoogleCalendarSession
except ImportError:
    from software.LightGoogleCalendar.session import LightGoogleCalendarSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("google-calendar")

session_dict: Dict[str, LightGoogleCalendarSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None, fixture: str | None = None):
	session = LightGoogleCalendarSession(os_cfg=os_cfg, seed=seed, fixture=fixture)
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
        "output": session.google_calendar_session.get_session_dict(),
    }


@mcp.tool
async def list_calendars(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.list_calendars()


@mcp.tool
async def get_calendar(calendar_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.get_calendar(calendar_id)


@mcp.tool
async def list_events(calendar_id: str, session_id: str, time_min: str | None = None, time_max: str | None = None, q: str | None = None, single_events: bool = True, order_by: str = "startTime", max_results: int = 25, page_token: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.list_events(calendar_id, time_min, time_max, q, single_events, order_by, max_results, page_token)


@mcp.tool
async def get_event(calendar_id: str, event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.get_event(calendar_id, event_id)


@mcp.tool
async def create_event(calendar_id: str, summary: str, start: Dict[str, Any], end: Dict[str, Any], session_id: str, description: str = "", location: str = "", attendees: List[Dict[str, Any]] | None = None, recurrence: List[str] | None = None, visibility: str = "default"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.create_event(calendar_id, summary, start, end, description, location, attendees, recurrence, visibility)


@mcp.tool
async def update_event(calendar_id: str, event_id: str, session_id: str, summary: str | None = None, description: str | None = None, location: str | None = None, start: Dict[str, Any] | None = None, end: Dict[str, Any] | None = None, attendees: List[Dict[str, Any]] | None = None, status: str | None = None, visibility: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.update_event(calendar_id, event_id, summary, description, location, start, end, attendees, status, visibility)


@mcp.tool
async def delete_event(calendar_id: str, event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.delete_event(calendar_id, event_id)


@mcp.tool
async def freebusy(time_min: str, time_max: str, calendar_ids: List[str], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_calendar_session.freebusy(time_min, time_max, calendar_ids)
