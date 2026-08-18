from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightObsidianSession
except ImportError:
    from software.LightObsidian.session import LightObsidianSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightObsidian")

session_dict: Dict[str, LightObsidianSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightObsidianSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.obsidian_session.get_session_dict(),
    }


@mcp.tool
async def get_vault(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.get_vault()


@mcp.tool
async def list_notes(session_id: str, folder: str | None = None, tag: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.list_notes(folder, tag)


@mcp.tool
async def get_note(path: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.get_note(path)


@mcp.tool
async def create_note(path: str, content: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.create_note(path, content)


@mcp.tool
async def update_note(path: str, session_id: str, content: str | None = None, append: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.update_note(path, content, append)


@mcp.tool
async def delete_note(path: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.delete_note(path)


@mcp.tool
async def search(query: str, session_id: str, content: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.search(query, content)


@mcp.tool
async def list_backlinks(path: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.list_backlinks(path)


@mcp.tool
async def get_daily(date_str: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.obsidian_session.get_daily(date_str)
