from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAsanaSession
except ImportError:
    from software.LightAsana.session import LightAsanaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAsana")

session_dict: Dict[str, LightAsanaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAsanaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.asana_session.get_session_dict(),
    }


@mcp.tool
async def list_workspaces(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_workspaces()


@mcp.tool
async def list_users(session_id: str, workspace_gid: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_users(workspace_gid)


@mcp.tool
async def list_projects(session_id: str, workspace_gid: str | None = None, archived: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_projects(workspace_gid, archived)


@mcp.tool
async def get_project(project_gid: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.get_project(project_gid)


@mcp.tool
async def list_project_sections(project_gid: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_project_sections(project_gid)


@mcp.tool
async def list_project_tasks(project_gid: str, session_id: str, completed_since: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_project_tasks(project_gid, completed_since)


@mcp.tool
async def list_tasks(session_id: str, project_gid: str | None = None, assignee_gid: str | None = None, completed: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.list_tasks(project_gid, assignee_gid, completed)


@mcp.tool
async def get_task(task_gid: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.get_task(task_gid)


@mcp.tool
async def create_task(name: str, session_id: str, project_gid: str | None = None, section_gid: str | None = None, assignee_gid: str | None = None, due_on: str | None = None, notes: str = "", completed: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.create_task(name, project_gid, section_gid, assignee_gid, due_on, notes, completed)


@mcp.tool
async def update_task(task_gid: str, session_id: str, name: str | None = None, completed: bool | None = None, assignee_gid: str | None = None, due_on: str | None = None, section_gid: str | None = None, notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.asana_session.update_task(task_gid, name, completed, assignee_gid, due_on, section_gid, notes)
