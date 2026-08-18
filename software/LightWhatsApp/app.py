from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightWhatsAppSession
except ImportError:
    from software.LightWhatsApp.session import LightWhatsAppSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightWhatsApp")

session_dict: Dict[str, LightWhatsAppSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None, fixture: str | None = None):
	session = LightWhatsAppSession(os_cfg=os_cfg, seed=seed, fixture=fixture)
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
        "output": session.whatsapp_session.get_session_dict(),
    }


@mcp.tool
async def get_business(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.get_business()


@mcp.tool
async def list_contacts(session_id: str, opted_in_only: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.list_contacts(opted_in_only)


@mcp.tool
async def get_contact(wa_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.get_contact(wa_id)


@mcp.tool
async def list_templates(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.list_templates(status)


@mcp.tool
async def get_template(name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.get_template(name)


@mcp.tool
async def list_conversations(session_id: str, wa_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.list_conversations(wa_id)


@mcp.tool
async def list_messages(session_id: str, conversation_id: str | None = None, wa_id: str | None = None, limit: int = 20):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.list_messages(conversation_id, wa_id, limit)


@mcp.tool
async def send_text(to_wa_id: str, body: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.send_text(to_wa_id, body)


@mcp.tool
async def send_template(to_wa_id: str, template_name: str, session_id: str, components: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.send_template(to_wa_id, template_name, components)


@mcp.tool
async def mark_read(message_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.whatsapp_session.mark_read(message_id)
