from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightFreshdeskSession
except ImportError:
    from software.LightFreshdesk.session import LightFreshdeskSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightFreshdesk")

session_dict: Dict[str, LightFreshdeskSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightFreshdeskSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.freshdesk_session.get_session_dict(),
    }


@mcp.tool
async def list_tickets(session_id: str, status: int | None = None, priority: int | None = None, requester_id: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.list_tickets(status, priority, requester_id)


@mcp.tool
async def get_ticket(ticket_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.get_ticket(ticket_id)


@mcp.tool
async def create_ticket(session_id: str, subject: str | None = None, description: str | None = None, status: int | None = None, priority: int | None = None, requester_id: int | None = None, responder_id: int | None = None, type: str | None = None, tags: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.create_ticket(subject, description, status, priority, requester_id, responder_id, type, tags)


@mcp.tool
async def update_ticket(ticket_id: int, session_id: str, subject: str | None = None, description: str | None = None, status: int | None = None, priority: int | None = None, responder_id: int | None = None, requester_id: int | None = None, type: str | None = None, tags: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.update_ticket(ticket_id, subject, description, status, priority, responder_id, requester_id, type, tags)


@mcp.tool
async def list_contacts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.list_contacts()


@mcp.tool
async def list_agents(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.freshdesk_session.list_agents()
