from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightWeatherSession
except ImportError:
    from software.LightWeather.session import LightWeatherSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightWeather")

session_dict: Dict[str, LightWeatherSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightWeatherSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.weather_session.get_session_dict(),
    }


@mcp.tool
async def list_cities(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.list_cities()


@mcp.tool
async def get_current_weather(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_current_weather(location)


@mcp.tool
async def get_forecast(location: str, days: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_forecast(location, days)


@mcp.tool
async def get_hourly_forecast(location: str, hours: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_hourly_forecast(location, hours)


@mcp.tool
async def list_stations(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.list_stations()


@mcp.tool
async def get_station_info(station_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_station_info(station_id)


@mcp.tool
async def get_station_observation(station_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_station_observation(station_id)


@mcp.tool
async def get_historical_weather(location: str, start: str, end: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_historical_weather(location, start, end)


@mcp.tool
async def get_weather_alerts(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_weather_alerts(location)


@mcp.tool
async def create_alert(location: str, condition: str, threshold: float, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.create_alert(location, condition, threshold)


@mcp.tool
async def delete_alert(alert_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.delete_alert(alert_id)


@mcp.tool
async def list_alerts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.list_alerts()


@mcp.tool
async def get_uv_index(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_uv_index(location)


@mcp.tool
async def get_air_quality(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_air_quality(location)


@mcp.tool
async def get_sun_times(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_sun_times(location)


@mcp.tool
async def convert_temperature(value: float, from_unit: str, to_unit: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.convert_temperature(value, from_unit, to_unit)


@mcp.tool
async def estimate_travel_weather(route: List[str], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.estimate_travel_weather(route)


@mcp.tool
async def compare_climate(location1: str, location2: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.compare_climate(location1, location2)


@mcp.tool
async def get_precip_probability(location: str, next_hours: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_precip_probability(location, next_hours)


@mcp.tool
async def get_wind_forecast(location: str, hours: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_wind_forecast(location, hours)


@mcp.tool
async def get_climate_summary(location: str, year: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_climate_summary(location, year)


@mcp.tool
async def set_primary_location(location: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.set_primary_location(location)


@mcp.tool
async def get_primary_location(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.weather_session.get_primary_location()

