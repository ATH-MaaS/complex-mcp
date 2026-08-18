from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightEventbriteSession
except ImportError:
    from software.LightEventbrite.session import LightEventbriteSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightEventbrite")

session_dict: Dict[str, LightEventbriteSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightEventbriteSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.eventbrite_session.get_session_dict(),
    }


@mcp.tool
async def list_organizations(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.list_organizations()


@mcp.tool
async def get_organization(org_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.get_organization(org_id)


@mcp.tool
async def list_events(org_id: str, session_id: str, status: str | None = None, q: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.list_events(org_id, status, q, page_size)


@mcp.tool
async def search_events(session_id: str, q: str | None = None, status: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.search_events(q, status, page_size)


@mcp.tool
async def get_event(event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.get_event(event_id)


@mcp.tool
async def create_event(organization_id: str, name: str, summary: str, start_utc: str, end_utc: str, session_id: str, timezone: str = "America/Los_Angeles", venue_id: str | None = None, capacity: int = 50, is_free: bool = True, online_event: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.create_event(organization_id, name, summary, start_utc, end_utc, timezone, venue_id, capacity, is_free, online_event)


@mcp.tool
async def publish_event(event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.publish_event(event_id)


@mcp.tool
async def cancel_event(event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.cancel_event(event_id)


@mcp.tool
async def list_venues(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.list_venues()


@mcp.tool
async def get_venue(venue_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.get_venue(venue_id)


@mcp.tool
async def list_ticket_classes(event_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.list_ticket_classes(event_id)


@mcp.tool
async def create_ticket_class(event_id: str, name: str, quantity_total: int, session_id: str, cost: int = 0, free: bool = True):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.create_ticket_class(event_id, name, quantity_total, cost, free)


@mcp.tool
async def list_attendees(event_id: str, session_id: str, status: str | None = None, checked_in: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.list_attendees(event_id, status, checked_in)


@mcp.tool
async def register_attendee(event_id: str, ticket_class_id: str, name: str, email: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.register_attendee(event_id, ticket_class_id, name, email)


@mcp.tool
async def check_in_attendee(attendee_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.eventbrite_session.check_in_attendee(attendee_id)
