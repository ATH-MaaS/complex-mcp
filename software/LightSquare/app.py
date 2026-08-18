from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightSquareSession
except ImportError:
    from software.LightSquare.session import LightSquareSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightSquare")

session_dict: Dict[str, LightSquareSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightSquareSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.square_session.get_session_dict(),
    }


@mcp.tool
async def get_merchant(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.get_merchant()


@mcp.tool
async def list_payments(session_id: str, location_id: str | None = None, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.list_payments(location_id, limit)


@mcp.tool
async def get_payment(payment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.get_payment(payment_id)


@mcp.tool
async def create_payment(amount: int, session_id: str, currency: str = "USD", source_id: str = "cnon:card-nonce-ok", customer_id: str | None = None, order_id: str | None = None, location_id: str = "LOC_MAIN"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.create_payment(amount, currency, source_id, customer_id, order_id, location_id)


@mcp.tool
async def create_refund(payment_id: str, session_id: str, amount: int | None = None, currency: str = "USD", reason: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.create_refund(payment_id, amount, currency, reason)


@mcp.tool
async def list_customers(session_id: str, limit: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.list_customers(limit)


@mcp.tool
async def get_customer(customer_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.get_customer(customer_id)


@mcp.tool
async def create_customer(session_id: str, given_name: str | None = None, family_name: str | None = None, email_address: str | None = None, phone_number: str | None = None, company_name: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.create_customer(given_name, family_name, email_address, phone_number, company_name)


@mcp.tool
async def list_catalog(session_id: str, types: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.list_catalog(types)


@mcp.tool
async def create_order(session_id: str, customer_id: str | None = None, location_id: str = "LOC_MAIN", line_items: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.create_order(customer_id, location_id, line_items)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.get_order(order_id)


@mcp.tool
async def get_inventory(catalog_object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.square_session.get_inventory(catalog_object_id)
