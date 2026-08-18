from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTicketmasterSession
except ImportError:
    from software.LightTicketmaster.session import LightTicketmasterSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTicketmaster")

session_dict: Dict[str, LightTicketmasterSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTicketmasterSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.ticketmaster_session.get_session_dict(),
    }


@mcp.tool
async def search_events(session_id: str, keyword: str | None = None, city: str | None = None, classificationName: str | None = None, startDateTime: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.search_events(keyword, city, classificationName, startDateTime)


@mcp.tool
async def get_event(event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.get_event(event_id)


@mcp.tool
async def search_venues(session_id: str, keyword: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.search_venues(keyword)


@mcp.tool
async def get_venue(venue_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.get_venue(venue_id)


@mcp.tool
async def search_attractions(session_id: str, keyword: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.search_attractions(keyword)


@mcp.tool
async def get_attraction(attraction_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.get_attraction(attraction_id)


@mcp.tool
async def list_classifications(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ticketmaster_session.list_classifications()
