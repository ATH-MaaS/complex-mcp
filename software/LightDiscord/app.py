from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightDiscordSession
except ImportError:
    from software.LightDiscord.session import LightDiscordSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightDiscord")

session_dict: Dict[str, LightDiscordSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightDiscordSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.discord_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.get_me()


@mcp.tool
async def list_my_guilds(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.list_my_guilds()


@mcp.tool
async def get_guild(guild_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.get_guild(guild_id)


@mcp.tool
async def list_guild_channels(guild_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.list_guild_channels(guild_id)


@mcp.tool
async def list_guild_members(guild_id: str, session_id: str, limit: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.list_guild_members(guild_id, limit)


@mcp.tool
async def list_guild_roles(guild_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.list_guild_roles(guild_id)


@mcp.tool
async def get_channel(channel_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.get_channel(channel_id)


@mcp.tool
async def list_channel_messages(channel_id: str, session_id: str, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.list_channel_messages(channel_id, limit)


@mcp.tool
async def create_message(channel_id: str, content: str, session_id: str, author_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.discord_session.create_message(channel_id, content, author_id)
