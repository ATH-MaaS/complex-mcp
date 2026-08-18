from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightDropboxSession
except ImportError:
    from software.LightDropbox.session import LightDropboxSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightDropbox")

session_dict: Dict[str, LightDropboxSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightDropboxSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.dropbox_session.get_session_dict(),
    }


@mcp.tool
async def get_current_account(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.get_current_account()


@mcp.tool
async def list_folder(session_id: str, path: str = "", recursive: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.list_folder(path, recursive)


@mcp.tool
async def get_metadata(session_id: str, path: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.get_metadata(path)


@mcp.tool
async def download_file(session_id: str, path: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.download_file(path)


@mcp.tool
async def search_v2(session_id: str, query: str | None = None, path: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.search_v2(query, path)


@mcp.tool
async def list_shared_links(session_id: str, path: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.dropbox_session.list_shared_links(path)
