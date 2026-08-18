from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightPayPalSession
except ImportError:
    from software.LightPayPal.session import LightPayPalSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightPayPal")

session_dict: Dict[str, LightPayPalSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightPayPalSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.paypal_session.get_session_dict(),
    }


@mcp.tool
async def create_order(session_id: str, amount_value: str = "0.00", currency_code: str = "USD", payee_email: str = "merchant@orbit-labs.com", description: str = "", intent: str = "CAPTURE"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.create_order(amount_value, currency_code, payee_email, description, intent)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.get_order(order_id)


@mcp.tool
async def capture_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.capture_order(order_id)


@mcp.tool
async def create_refund(capture_id: str, session_id: str, amount_value: str | None = None, currency_code: str = "USD", note_to_payer: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.create_refund(capture_id, amount_value, currency_code, note_to_payer)


@mcp.tool
async def get_refund(refund_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.get_refund(refund_id)


@mcp.tool
async def list_invoices(session_id: str, status: str | None = None, page_size: int = 20):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.list_invoices(status, page_size)


@mcp.tool
async def create_invoice(session_id: str, invoice_number: str | None = None, recipient_email: str | None = None, amount_value: str = "0.00", currency_code: str = "USD", due_date: str | None = None, note: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.create_invoice(invoice_number, recipient_email, amount_value, currency_code, due_date, note)


@mcp.tool
async def create_payout(session_id: str, amount_value: str = "0.00", currency_code: str = "USD", recipient_email: str | None = None, sender_batch_id: str | None = None, note: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.paypal_session.create_payout(amount_value, currency_code, recipient_email, sender_batch_id, note)
