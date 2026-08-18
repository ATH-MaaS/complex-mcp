from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightXeroSession
except ImportError:
    from software.LightXero.session import LightXeroSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightXero")

session_dict: Dict[str, LightXeroSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightXeroSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.xero_session.get_session_dict(),
    }


@mcp.tool
async def list_invoices(session_id: str, status: str | None = None, type_: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.xero_session.list_invoices(status, type_)


@mcp.tool
async def get_invoice(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.xero_session.get_invoice(invoice_id)


@mcp.tool
async def create_invoice(contact_id: str, session_id: str, line_items: List[Dict[str, Any]] | None = None, type_: str = "ACCREC", date: str | None = None, due_date: str | None = None, status: str = "DRAFT", reference: str = "", currency_code: str = "USD"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.xero_session.create_invoice(contact_id, line_items, type_, date, due_date, status, reference, currency_code)


@mcp.tool
async def list_contacts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.xero_session.list_contacts()


@mcp.tool
async def list_accounts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.xero_session.list_accounts()
