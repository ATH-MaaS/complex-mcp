from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightUberSession
except ImportError:
    from software.LightUber.session import LightUberSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightUber")

session_dict: Dict[str, LightUberSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightUberSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.uber_session.get_session_dict(),
    }


@mcp.tool
async def list_products(latitude: float, longitude: float, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.list_products(latitude, longitude)


@mcp.tool
async def get_product(product_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.get_product(product_id)


@mcp.tool
async def price_estimates(start_latitude: float, start_longitude: float, end_latitude: float, end_longitude: float, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.price_estimates(start_latitude, start_longitude, end_latitude, end_longitude)


@mcp.tool
async def time_estimates(start_latitude: float, start_longitude: float, session_id: str, product_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.time_estimates(start_latitude, start_longitude, product_id)


@mcp.tool
async def create_request(product_id: str, start_latitude: float, start_longitude: float, session_id: str, end_latitude: float | None = None, end_longitude: float | None = None, rider_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.create_request(product_id, start_latitude, start_longitude, end_latitude, end_longitude, rider_id)


@mcp.tool
async def get_request(request_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.get_request(request_id)


@mcp.tool
async def cancel_request(request_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.cancel_request(request_id)


@mcp.tool
async def get_history(session_id: str, rider_id: str | None = None, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.get_history(rider_id, limit, offset)


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.uber_session.get_me()
