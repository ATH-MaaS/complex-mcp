from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightSendGridSession
except ImportError:
    from software.LightSendGrid.session import LightSendGridSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightSendGrid")

session_dict: Dict[str, LightSendGridSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightSendGridSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.sendgrid_session.get_session_dict(),
    }


@mcp.tool
async def send_mail(personalizations: List[Dict[str, Any]], from_email: str, session_id: str, subject: str | None = None, content: List[Dict[str, Any]] | None = None, template_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.send_mail(personalizations, from_email, subject, content, template_id)


@mcp.tool
async def list_templates(session_id: str, generation: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.list_templates(generation)


@mcp.tool
async def get_template(template_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.get_template(template_id)


@mcp.tool
async def create_template(name: str, session_id: str, generation: str = "dynamic", subject: str = "", html_content: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.create_template(name, generation, subject, html_content)


@mcp.tool
async def list_contacts(session_id: str, email: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.list_contacts(email)


@mcp.tool
async def upsert_contacts(contacts: List[Dict[str, Any]], session_id: str, list_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.upsert_contacts(contacts, list_ids)


@mcp.tool
async def list_lists(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.list_lists()


@mcp.tool
async def get_stats(start_date: str, session_id: str, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.sendgrid_session.get_stats(start_date, end_date)
