from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightOpenWeatherSession
except ImportError:
    from software.LightOpenWeather.session import LightOpenWeatherSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightOpenWeather")

session_dict: Dict[str, LightOpenWeatherSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightOpenWeatherSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.openweather_session.get_session_dict(),
    }


@mcp.tool
async def get_current_weather(session_id: str, q: str | None = None, lat: float | None = None, lon: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openweather_session.get_current_weather(q, lat, lon)


@mcp.tool
async def get_forecast(session_id: str, q: str | None = None, lat: float | None = None, lon: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openweather_session.get_forecast(q, lat, lon)


@mcp.tool
async def geocode_direct(q: str, session_id: str, limit: int = 5):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openweather_session.geocode_direct(q, limit)
