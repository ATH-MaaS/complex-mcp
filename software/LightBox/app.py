from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightBoxSession
except ImportError:
    from software.LightBox.session import LightBoxSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightBox")

session_dict: Dict[str, LightBoxSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightBoxSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.box_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.get_me()


@mcp.tool
async def get_folder(folder_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.get_folder(folder_id)


@mcp.tool
async def get_folder_items(folder_id: str, session_id: str, limit: int = 100, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.get_folder_items(folder_id, limit, offset)


@mcp.tool
async def get_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.get_file(file_id)


@mcp.tool
async def download_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.download_file(file_id)


@mcp.tool
async def search(session_id: str, query: str | None = None, type: str | None = None, limit: int = 100, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.box_session.search(query, type, limit, offset)
