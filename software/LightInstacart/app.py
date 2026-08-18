from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightInstacartSession
except ImportError:
    from software.LightInstacart.session import LightInstacartSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightInstacart")

session_dict: Dict[str, LightInstacartSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightInstacartSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.instacart_session.get_session_dict(),
    }


@mcp.tool
async def get_user(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.get_user()


@mcp.tool
async def list_retailers(session_id: str, zip_code: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.list_retailers(zip_code)


@mcp.tool
async def get_retailer(retailer_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.get_retailer(retailer_id)


@mcp.tool
async def search_products(session_id: str, retailer_id: str | None = None, query: str | None = None, category: str | None = None, in_stock_only: bool = True, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.search_products(retailer_id, query, category, in_stock_only, limit, offset)


@mcp.tool
async def get_product(product_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.get_product(product_id)


@mcp.tool
async def create_cart(user_id: str, retailer_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.create_cart(user_id, retailer_id)


@mcp.tool
async def get_cart(cart_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.get_cart(cart_id)


@mcp.tool
async def add_to_cart(cart_id: str, product_id: str, quantity: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.add_to_cart(cart_id, product_id, quantity)


@mcp.tool
async def update_cart_item(cart_id: str, product_id: str, quantity: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.update_cart_item(cart_id, product_id, quantity)


@mcp.tool
async def checkout(cart_id: str, session_id: str, tip: float = 0.0, delivery_window_start: str | None = None, delivery_window_end: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.checkout(cart_id, tip, delivery_window_start, delivery_window_end)


@mcp.tool
async def list_orders(session_id: str, user_id: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.list_orders(user_id, status)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.get_order(order_id)


@mcp.tool
async def cancel_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instacart_session.cancel_order(order_id)
