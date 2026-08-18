from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightStripeSession
except ImportError:
    from software.LightStripe.session import LightStripeSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightStripe")

session_dict: Dict[str, LightStripeSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightStripeSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.stripe_session.get_session_dict(),
    }


@mcp.tool
async def list_customers(session_id: str, limit: int = 10, email: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_customers(limit, email)


@mcp.tool
async def get_customer(customer_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_customer(customer_id)


@mcp.tool
async def create_customer(session_id: str, name: str | None = None, email: str | None = None, description: str | None = None, currency: str = "usd", phone: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_customer(name, email, description, currency, phone)


@mcp.tool
async def list_products(session_id: str, limit: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_products(limit)


@mcp.tool
async def list_prices(session_id: str, limit: int = 10, product: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_prices(limit, product)


@mcp.tool
async def create_payment_intent(amount: int, session_id: str, currency: str = "usd", customer: str | None = None, description: str | None = None, confirm: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_payment_intent(amount, currency, customer, description, confirm)


@mcp.tool
async def get_payment_intent(pi_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_payment_intent(pi_id)


@mcp.tool
async def list_charges(session_id: str, limit: int = 10, customer: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_charges(limit, customer)


@mcp.tool
async def get_charge(charge_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_charge(charge_id)


@mcp.tool
async def create_charge(amount: int, session_id: str, currency: str = "usd", customer: str | None = None, description: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_charge(amount, currency, customer, description)


@mcp.tool
async def create_refund(charge: str, session_id: str, amount: int | None = None, reason: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_refund(charge, amount, reason)


@mcp.tool
async def list_invoices(session_id: str, limit: int = 10, customer: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_invoices(limit, customer, status)


@mcp.tool
async def get_invoice(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_invoice(invoice_id)


@mcp.tool
async def create_invoice(customer: str, session_id: str, amount_due: int = 0, currency: str = "usd", subscription: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_invoice(customer, amount_due, currency, subscription)


@mcp.tool
async def list_subscriptions(session_id: str, limit: int = 10, customer: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.list_subscriptions(limit, customer, status)


@mcp.tool
async def get_subscription(sub_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_subscription(sub_id)


@mcp.tool
async def create_subscription(customer: str, price: str, session_id: str, quantity: int = 1):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.create_subscription(customer, price, quantity)


@mcp.tool
async def get_balance(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.stripe_session.get_balance()
