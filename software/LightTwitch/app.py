from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTwitchSession
except ImportError:
    from software.LightTwitch.session import LightTwitchSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTwitch")

session_dict: Dict[str, LightTwitchSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTwitchSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.twitch_session.get_session_dict(),
    }


@mcp.tool
async def get_users(session_id: str, logins: List[str] | None = None, ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_users(logins, ids)


@mcp.tool
async def get_streams(session_id: str, user_logins: List[str] | None = None, user_ids: List[str] | None = None, game_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_streams(user_logins, user_ids, game_id)


@mcp.tool
async def get_channels(broadcaster_ids: List[str], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_channels(broadcaster_ids)


@mcp.tool
async def get_channel_followers(broadcaster_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_channel_followers(broadcaster_id)


@mcp.tool
async def get_top_games(session_id: str, first: int = 20):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_top_games(first)


@mcp.tool
async def get_games(session_id: str, names: List[str] | None = None, ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_games(names, ids)


@mcp.tool
async def get_clips(session_id: str, broadcaster_id: str | None = None, game_id: str | None = None, first: int = 20):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitch_session.get_clips(broadcaster_id, game_id, first)
