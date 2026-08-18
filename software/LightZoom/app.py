from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightZoomSession
except ImportError:
    from software.LightZoom.session import LightZoomSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightZoom")

session_dict: Dict[str, LightZoomSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightZoomSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.zoom_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.get_me()


@mcp.tool
async def list_meetings(user_id: str, session_id: str, meeting_type: str = "scheduled", page_size: int = 30):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.list_meetings(user_id, meeting_type, page_size)


@mcp.tool
async def create_meeting(user_id: str, topic: str, session_id: str, start_time: str | None = None, duration: int = 60, timezone: str = "UTC", agenda: str = "", meeting_type: int = 2):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.create_meeting(user_id, topic, start_time, duration, timezone, agenda, meeting_type)


@mcp.tool
async def get_meeting(meeting_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.get_meeting(meeting_id)


@mcp.tool
async def update_meeting(meeting_id: int, session_id: str, topic: str | None = None, start_time: str | None = None, duration: int | None = None, agenda: str | None = None, timezone: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.update_meeting(meeting_id, topic, start_time, duration, agenda, timezone)


@mcp.tool
async def delete_meeting(meeting_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.delete_meeting(meeting_id)


@mcp.tool
async def get_recordings(meeting_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.get_recordings(meeting_id)


@mcp.tool
async def list_registrants(meeting_id: int, session_id: str, status: str = "approved"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zoom_session.list_registrants(meeting_id, status)
