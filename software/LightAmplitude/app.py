from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAmplitudeSession
except ImportError:
    from software.LightAmplitude.session import LightAmplitudeSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAmplitude")

session_dict: Dict[str, LightAmplitudeSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAmplitudeSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.amplitude_session.get_session_dict(),
    }


@mcp.tool
async def ingest(events: List[Dict[str, Any]], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amplitude_session.ingest(events)


@mcp.tool
async def segmentation(session_id: str, event: str | None = None, start: str | None = None, end: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amplitude_session.segmentation(event, start, end)


@mcp.tool
async def user_activity(user: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amplitude_session.user_activity(user)
