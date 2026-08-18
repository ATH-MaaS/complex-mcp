from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightDocuSignSession
except ImportError:
    from software.LightDocuSign.session import LightDocuSignSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightDocuSign")

session_dict: Dict[str, LightDocuSignSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightDocuSignSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.docusign_session.get_session_dict(),
    }


@mcp.tool
async def list_envelopes(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.list_envelopes(status)


@mcp.tool
async def get_envelope(envelope_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.get_envelope(envelope_id)


@mcp.tool
async def create_envelope(session_id: str, email_subject: str = "", status: str = "created", template_id: str | None = None, sender_name: str | None = None, sender_email: str | None = None, recipients: Dict[str, Any] | None = None, documents: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.create_envelope(email_subject, status, template_id, sender_name, sender_email, recipients, documents)


@mcp.tool
async def update_envelope(envelope_id: str, status: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.update_envelope(envelope_id, status)


@mcp.tool
async def list_recipients(envelope_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.list_recipients(envelope_id)


@mcp.tool
async def list_documents(envelope_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.list_documents(envelope_id)


@mcp.tool
async def list_templates(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.docusign_session.list_templates()
