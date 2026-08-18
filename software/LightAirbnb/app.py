from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAirbnbSession
except ImportError:
    from software.LightAirbnb.session import LightAirbnbSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAirbnb")

session_dict: Dict[str, LightAirbnbSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAirbnbSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.airbnb_session.get_session_dict(),
    }


@mcp.tool
async def search_listings(session_id: str, location: str | None = None, checkin: str | None = None, checkout: str | None = None, guests: int | None = None, min_price: float | None = None, max_price: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.search_listings(location, checkin, checkout, guests, min_price, max_price)


@mcp.tool
async def get_listing(listing_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.get_listing(listing_id)


@mcp.tool
async def get_availability(listing_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.get_availability(listing_id)


@mcp.tool
async def get_reviews(listing_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.get_reviews(listing_id)


@mcp.tool
async def create_reservation(listing_id: str, checkin: str, checkout: str, session_id: str, guests: int = 1, guest_name: str = "Guest"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.create_reservation(listing_id, checkin, checkout, guests, guest_name)


@mcp.tool
async def get_reservation(reservation_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.get_reservation(reservation_id)


@mcp.tool
async def cancel_reservation(reservation_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airbnb_session.cancel_reservation(reservation_id)
