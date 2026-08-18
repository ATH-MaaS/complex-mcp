from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAmadeusSession
except ImportError:
    from software.LightAmadeus.session import LightAmadeusSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAmadeus")

session_dict: Dict[str, LightAmadeusSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAmadeusSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.amadeus_session.get_session_dict(),
    }


@mcp.tool
async def search_flight_offers(origin: str, destination: str, session_id: str, departure_date: str | None = None, adults: int = 1, max_results: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amadeus_session.search_flight_offers(origin, destination, departure_date, adults, max_results)


@mcp.tool
async def price_flight_offer(offer: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amadeus_session.price_flight_offer(offer)


@mcp.tool
async def search_locations(session_id: str, keyword: str | None = None, sub_type: str = "AIRPORT,CITY"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amadeus_session.search_locations(keyword, sub_type)


@mcp.tool
async def get_location(location_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amadeus_session.get_location(location_id)


@mcp.tool
async def get_airlines(session_id: str, airline_codes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amadeus_session.get_airlines(airline_codes)
