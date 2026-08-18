from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMondaySession
except ImportError:
    from software.LightMonday.session import LightMondaySession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightMonday")

session_dict: Dict[str, LightMondaySession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMondaySession(os_cfg=os_cfg, seed=seed)
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
        "output": session.monday_session.get_session_dict(),
    }


@mcp.tool
async def list_workspaces(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.list_workspaces()


@mcp.tool
async def list_boards(session_id: str, workspace_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.list_boards(workspace_id)


@mcp.tool
async def get_board(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.get_board(board_id)


@mcp.tool
async def get_board_items(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.get_board_items(board_id)


@mcp.tool
async def list_items(session_id: str, board_id: str | None = None, group_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.list_items(board_id, group_id)


@mcp.tool
async def get_item(item_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.get_item(item_id)


@mcp.tool
async def create_item(board_id: str, item_name: str, session_id: str, group_id: str | None = None, column_values: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.create_item(board_id, item_name, group_id, column_values)


@mcp.tool
async def update_item(item_id: str, session_id: str, column_id: str | None = None, text: str | None = None, value: str | None = None, group_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.update_item(item_id, column_id, text, value, group_id)


@mcp.tool
async def delete_item(item_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.delete_item(item_id)


@mcp.tool
async def list_users(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.monday_session.list_users()
