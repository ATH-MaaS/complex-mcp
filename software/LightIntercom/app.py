from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightIntercomSession
except ImportError:
    from software.LightIntercom.session import LightIntercomSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightIntercom")

session_dict: Dict[str, LightIntercomSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightIntercomSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.intercom_session.get_session_dict(),
    }


@mcp.tool
async def list_contacts(session_id: str, role: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.list_contacts(role)


@mcp.tool
async def get_contact(contact_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.get_contact(contact_id)


@mcp.tool
async def create_contact(session_id: str, role: str = "user", name: str = "", email: str | None = None, phone: str | None = None, company_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.create_contact(role, name, email, phone, company_id)


@mcp.tool
async def list_companies(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.list_companies()


@mcp.tool
async def get_company(company_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.get_company(company_id)


@mcp.tool
async def list_conversations(session_id: str, state: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.list_conversations(state)


@mcp.tool
async def get_conversation(conversation_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.get_conversation(conversation_id)


@mcp.tool
async def create_conversation(contact_id: str, body: str, session_id: str, title: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.create_conversation(contact_id, body, title)


@mcp.tool
async def reply_conversation(conversation_id: str, body: str, session_id: str, author_type: str = "admin", author_id: str = "admin-jonas"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.reply_conversation(conversation_id, body, author_type, author_id)


@mcp.tool
async def add_part(conversation_id: str, message_type: str, session_id: str, body: str | None = None, author_id: str = "admin-jonas", assignee_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.intercom_session.add_part(conversation_id, message_type, body, author_id, assignee_id)
