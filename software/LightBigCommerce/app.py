from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightBigCommerceSession
except ImportError:
    from software.LightBigCommerce.session import LightBigCommerceSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightBigCommerce")

session_dict: Dict[str, LightBigCommerceSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightBigCommerceSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.bigcommerce_session.get_session_dict(),
    }


@mcp.tool
async def list_products(session_id: str, name: str | None = None, sku: str | None = None, is_visible: bool | None = None, page: int = 1, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.list_products(name, sku, is_visible, page, limit)


@mcp.tool
async def get_product(product_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.get_product(product_id)


@mcp.tool
async def list_orders(session_id: str, customer_id: int | None = None, status_id: int | None = None, page: int = 1, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.list_orders(customer_id, status_id, page, limit)


@mcp.tool
async def get_order(order_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.get_order(order_id)


@mcp.tool
async def create_order(session_id: str, customer_id: int = 0, status_id: int = 1, payment_method: str = "manual", currency_code: str = "USD", billing_address: Dict[str, Any] | None = None, products: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.create_order(customer_id, status_id, payment_method, currency_code, billing_address, products)


@mcp.tool
async def list_customers(session_id: str, email: str | None = None, company: str | None = None, page: int = 1, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bigcommerce_session.list_customers(email, company, page, limit)
