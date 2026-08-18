from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightPostHogSession
except ImportError:
    from software.LightPostHog.session import LightPostHogSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightPostHog")

session_dict: Dict[str, LightPostHogSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightPostHogSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.posthog_session.get_session_dict(),
    }


@mcp.tool
async def capture(session_id: str, distinct_id: str | None = None, project_id: int | None = None, event: str | None = None, timestamp: str | None = None, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.posthog_session.capture(distinct_id, project_id, event, timestamp, properties)


@mcp.tool
async def decide(session_id: str, distinct_id: str | None = None, project_id: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.posthog_session.decide(distinct_id, project_id)


@mcp.tool
async def list_events(project_id: int, session_id: str, event: str | None = None, distinct_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.posthog_session.list_events(project_id, event, distinct_id)


@mcp.tool
async def list_feature_flags(project_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.posthog_session.list_feature_flags(project_id)


@mcp.tool
async def list_persons(project_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.posthog_session.list_persons(project_id)
