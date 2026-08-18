from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightDoorDashSession
except ImportError:
    from software.LightDoorDash.session import LightDoorDashSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightDoorDash")

session_dict: Dict[str, LightDoorDashSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightDoorDashSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.doordash_session.get_session_dict(),
    }


@mcp.tool
async def list_stores(session_id: str, latitude: float | None = None, longitude: float | None = None, cuisine: str | None = None, open_only: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.list_stores(latitude, longitude, cuisine, open_only)


@mcp.tool
async def get_store(store_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.get_store(store_id)


@mcp.tool
async def get_menu(store_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.get_menu(store_id)


@mcp.tool
async def create_cart(store_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.create_cart(store_id)


@mcp.tool
async def get_cart(cart_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.get_cart(cart_id)


@mcp.tool
async def add_cart_item(cart_id: str, item_id: str, session_id: str, quantity: int = 1):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.add_cart_item(cart_id, item_id, quantity)


@mcp.tool
async def checkout(cart_id: str, session_id: str, customer_name: str = "Guest", tip: float = 0.0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.checkout(cart_id, customer_name, tip)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.doordash_session.get_order(order_id)
