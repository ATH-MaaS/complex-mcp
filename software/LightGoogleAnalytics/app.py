from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGoogleAnalyticsSession
except ImportError:
    from software.LightGoogleAnalytics.session import LightGoogleAnalyticsSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("google-analytics")

session_dict: Dict[str, LightGoogleAnalyticsSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGoogleAnalyticsSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.google_analytics_session.get_session_dict(),
    }


@mcp.tool
async def run_report(property_id: str, session_id: str, dimensions: List[Any] | None = None, metrics: List[Any] | None = None, date_ranges: List[Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_analytics_session.run_report(property_id, dimensions, metrics, date_ranges)


@mcp.tool
async def run_realtime_report(property_id: str, session_id: str, dimensions: List[Any] | None = None, metrics: List[Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_analytics_session.run_realtime_report(property_id, dimensions, metrics)


@mcp.tool
async def batch_run_reports(property_id: str, session_id: str, requests: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_analytics_session.batch_run_reports(property_id, requests)


@mcp.tool
async def get_metadata(property_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_analytics_session.get_metadata(property_id)


@mcp.tool
async def get_property(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_analytics_session.get_property()
