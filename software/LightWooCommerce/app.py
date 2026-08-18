from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightWooCommerceSession
except ImportError:
    from software.LightWooCommerce.session import LightWooCommerceSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightWooCommerce")

session_dict: Dict[str, LightWooCommerceSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightWooCommerceSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.woocommerce_session.get_session_dict(),
    }


@mcp.tool
async def list_products(session_id: str, search: str | None = None, sku: str | None = None, status: str | None = None, page: int = 1, per_page: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.list_products(search, sku, status, page, per_page)


@mcp.tool
async def get_product(product_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.get_product(product_id)


@mcp.tool
async def list_orders(session_id: str, customer: int | None = None, status: str | None = None, page: int = 1, per_page: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.list_orders(customer, status, page, per_page)


@mcp.tool
async def get_order(order_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.get_order(order_id)


@mcp.tool
async def create_order(session_id: str, customer_id: int = 0, status: str = "pending", currency: str = "USD", payment_method: str = "bacs", payment_method_title: str = "Direct Bank Transfer", billing: Dict[str, Any] | None = None, line_items: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.create_order(customer_id, status, currency, payment_method, payment_method_title, billing, line_items)


@mcp.tool
async def list_customers(session_id: str, search: str | None = None, email: str | None = None, page: int = 1, per_page: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.woocommerce_session.list_customers(search, email, page, per_page)
