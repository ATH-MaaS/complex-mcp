from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightVimeoSession
except ImportError:
    from software.LightVimeo.session import LightVimeoSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightVimeo")

session_dict: Dict[str, LightVimeoSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightVimeoSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.vimeo_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.vimeo_session.get_me()


@mcp.tool
async def get_my_videos(session_id: str, page: int = 1, per_page: int = 25):
	session, err = get_session(session_id)
	if err:
		return err
	return session.vimeo_session.get_my_videos(page, per_page)


@mcp.tool
async def get_video(video_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.vimeo_session.get_video(video_id)


@mcp.tool
async def get_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.vimeo_session.get_user(user_id)


@mcp.tool
async def get_user_videos(user_id: str, session_id: str, page: int = 1, per_page: int = 25):
	session, err = get_session(session_id)
	if err:
		return err
	return session.vimeo_session.get_user_videos(user_id, page, per_page)
