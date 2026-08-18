from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightCalendlySession
except ImportError:
    from software.LightCalendly.session import LightCalendlySession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightCalendly")

session_dict: Dict[str, LightCalendlySession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightCalendlySession(os_cfg=os_cfg, seed=seed)
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
        "output": session.calendly_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.get_me()


@mcp.tool
async def list_event_types(session_id: str, user: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.list_event_types(user)


@mcp.tool
async def get_event_type(uuid_: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.get_event_type(uuid_)


@mcp.tool
async def list_scheduled_events(session_id: str, user: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.list_scheduled_events(user, status)


@mcp.tool
async def get_scheduled_event(uuid_: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.get_scheduled_event(uuid_)


@mcp.tool
async def list_invitees(uuid_: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.list_invitees(uuid_)


@mcp.tool
async def book_event(event_type: str, session_id: str, start_time: str | None = None, end_time: str | None = None, location_type: str = "zoom", location: str = "", invitee: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.book_event(event_type, start_time, end_time, location_type, location, invitee)


@mcp.tool
async def cancel_event(uuid_: str, session_id: str, reason: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.calendly_session.cancel_event(uuid_, reason)
