from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightOktaSession
except ImportError:
    from software.LightOkta.session import LightOktaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightOkta")

session_dict: Dict[str, LightOktaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightOktaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.okta_session.get_session_dict(),
    }


@mcp.tool
async def list_users(session_id: str, status: str | None = None, q: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.list_users(status, q)


@mcp.tool
async def get_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.get_user(user_id)


@mcp.tool
async def create_user(first_name: str, last_name: str, email: str, session_id: str, login: str | None = None, activate: bool = True):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.create_user(first_name, last_name, email, login, activate)


@mcp.tool
async def activate_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.activate_user(user_id)


@mcp.tool
async def suspend_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.suspend_user(user_id)


@mcp.tool
async def deactivate_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.deactivate_user(user_id)


@mcp.tool
async def list_groups(session_id: str, q: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.list_groups(q)


@mcp.tool
async def get_group(group_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.get_group(group_id)


@mcp.tool
async def list_group_users(group_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.list_group_users(group_id)


@mcp.tool
async def list_apps(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.okta_session.list_apps(status)
