from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMixpanelSession
except ImportError:
    from software.LightMixpanel.session import LightMixpanelSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightMixpanel")

session_dict: Dict[str, LightMixpanelSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMixpanelSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.mixpanel_session.get_session_dict(),
    }


@mcp.tool
async def track(event: str, session_id: str, distinct_id: str | None = None, time: str | None = None, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.track(event, distinct_id, time, properties)


@mcp.tool
async def events_counts(session_id: str, event: str | None = None, from_date: str | None = None, to_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.events_counts(event, from_date, to_date)


@mcp.tool
async def funnels_list(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.funnels_list()


@mcp.tool
async def funnel(funnel_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.funnel(funnel_id)


@mcp.tool
async def segmentation(event: str, session_id: str, from_date: str | None = None, to_date: str | None = None, on: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.segmentation(event, from_date, to_date, on)


@mcp.tool
async def engage(session_id: str, distinct_id: str | None = None, where: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mixpanel_session.engage(distinct_id, where, page_size)
