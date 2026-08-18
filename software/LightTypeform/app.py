from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTypeformSession
except ImportError:
    from software.LightTypeform.session import LightTypeformSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTypeform")

session_dict: Dict[str, LightTypeformSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTypeformSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.typeform_session.get_session_dict(),
    }


@mcp.tool
async def list_forms(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.list_forms()


@mcp.tool
async def get_form(form_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.get_form(form_id)


@mcp.tool
async def create_form(title: str, session_id: str, workspace: str = "ws-orbit-labs", language: str = "en", is_public: bool = False, fields: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.create_form(title, workspace, language, is_public, fields)


@mcp.tool
async def update_form(form_id: str, session_id: str, title: str | None = None, language: str | None = None, is_public: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.update_form(form_id, title, language, is_public)


@mcp.tool
async def delete_form(form_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.delete_form(form_id)


@mcp.tool
async def list_responses(form_id: str, session_id: str, completed: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.list_responses(form_id, completed)


@mcp.tool
async def insights_summary(form_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.typeform_session.insights_summary(form_id)
