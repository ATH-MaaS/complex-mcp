from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightZendeskSession
except ImportError:
    from software.LightZendesk.session import LightZendeskSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightZendesk")

session_dict: Dict[str, LightZendeskSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightZendeskSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.zendesk_session.get_session_dict(),
    }


@mcp.tool
async def list_tickets(session_id: str, status: str | None = None, priority: str | None = None, assignee_id: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.list_tickets(status, priority, assignee_id)


@mcp.tool
async def get_ticket(ticket_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.get_ticket(ticket_id)


@mcp.tool
async def create_ticket(subject: str, session_id: str, description: str | None = None, priority: str = "normal", ticket_type: str = "question", requester_id: int | None = None, assignee_id: int | None = None, organization_id: int | None = None, tags: List[str] | None = None, comment_body: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.create_ticket(subject, description, priority, ticket_type, requester_id, assignee_id, organization_id, tags, comment_body)


@mcp.tool
async def update_ticket(ticket_id: int, session_id: str, status: str | None = None, priority: str | None = None, assignee_id: int | None = None, ticket_type: str | None = None, tags: List[str] | None = None, comment_body: str | None = None, comment_public: bool = True, comment_author_id: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.update_ticket(ticket_id, status, priority, assignee_id, ticket_type, tags, comment_body, comment_public, comment_author_id)


@mcp.tool
async def list_comments(ticket_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.list_comments(ticket_id)


@mcp.tool
async def create_comment(ticket_id: int, body: str, session_id: str, author_id: int | None = None, public: bool = True):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.create_comment(ticket_id, body, author_id, public)


@mcp.tool
async def list_users(session_id: str, role: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.list_users(role)


@mcp.tool
async def get_user(user_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.get_user(user_id)


@mcp.tool
async def list_organizations(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zendesk_session.list_organizations()
