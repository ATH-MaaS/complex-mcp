from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMicrosoftTeamsSession
except ImportError:
    from software.LightMicrosoftTeams.session import LightMicrosoftTeamsSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("microsoft-teams")

session_dict: Dict[str, LightMicrosoftTeamsSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMicrosoftTeamsSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.microsoft_teams_session.get_session_dict(),
    }


@mcp.tool
async def list_joined_teams(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.microsoft_teams_session.list_joined_teams()


@mcp.tool
async def get_team(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.microsoft_teams_session.get_team(team_id)


@mcp.tool
async def list_channels(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.microsoft_teams_session.list_channels(team_id)


@mcp.tool
async def list_messages(team_id: str, channel_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.microsoft_teams_session.list_messages(team_id, channel_id)


@mcp.tool
async def send_message(team_id: str, channel_id: str, content: str, session_id: str, content_type: str = "html", importance: str = "normal"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.microsoft_teams_session.send_message(team_id, channel_id, content, content_type, importance)
