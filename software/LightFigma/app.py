from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightFigmaSession
except ImportError:
    from software.LightFigma.session import LightFigmaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightFigma")

session_dict: Dict[str, LightFigmaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightFigmaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.figma_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_me()


@mcp.tool
async def get_team_projects(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_team_projects(team_id)


@mcp.tool
async def get_project_files(project_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_project_files(project_id)


@mcp.tool
async def get_file(file_key: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_file(file_key)


@mcp.tool
async def get_file_nodes(file_key: str, ids: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_file_nodes(file_key, ids)


@mcp.tool
async def get_comments(file_key: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_comments(file_key)


@mcp.tool
async def create_comment(file_key: str, message: str, session_id: str, node_id: str | None = None, user_id: str = "user-1001"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.create_comment(file_key, message, node_id, user_id)


@mcp.tool
async def get_components(file_key: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.figma_session.get_components(file_key)
