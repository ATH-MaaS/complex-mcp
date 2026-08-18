from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightServiceNowSession
except ImportError:
    from software.LightServiceNow.session import LightServiceNowSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightServiceNow")

session_dict: Dict[str, LightServiceNowSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightServiceNowSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.servicenow_session.get_session_dict(),
    }


@mcp.tool
async def list_incidents(session_id: str, sysparm_query: str | None = None, sysparm_limit: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.list_incidents(sysparm_query, sysparm_limit)


@mcp.tool
async def get_incident(sys_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.get_incident(sys_id)


@mcp.tool
async def create_incident(short_description: str, session_id: str, description: str | None = None, priority: str = "3", impact: str = "3", urgency: str = "3", category: str = "inquiry", assigned_to: str | None = None, opened_by: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.create_incident(short_description, description, priority, impact, urgency, category, assigned_to, opened_by)


@mcp.tool
async def update_incident(sys_id: str, session_id: str, short_description: str | None = None, description: str | None = None, state: str | None = None, priority: str | None = None, impact: str | None = None, urgency: str | None = None, category: str | None = None, assigned_to: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.update_incident(sys_id, short_description, description, state, priority, impact, urgency, category, assigned_to)


@mcp.tool
async def list_change_requests(session_id: str, sysparm_query: str | None = None, sysparm_limit: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.list_change_requests(sysparm_query, sysparm_limit)


@mcp.tool
async def get_change_request(sys_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.get_change_request(sys_id)


@mcp.tool
async def list_problems(session_id: str, sysparm_query: str | None = None, sysparm_limit: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.list_problems(sysparm_query, sysparm_limit)


@mcp.tool
async def get_problem(sys_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.get_problem(sys_id)


@mcp.tool
async def list_users(session_id: str, sysparm_query: str | None = None, sysparm_limit: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.list_users(sysparm_query, sysparm_limit)


@mcp.tool
async def get_user(sys_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.servicenow_session.get_user(sys_id)
