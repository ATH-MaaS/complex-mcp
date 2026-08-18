from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightPlaidSession
except ImportError:
    from software.LightPlaid.session import LightPlaidSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightPlaid")

session_dict: Dict[str, LightPlaidSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightPlaidSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.plaid_session.get_session_dict(),
    }


@mcp.tool
async def get_accounts(session_id: str, account_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.plaid_session.get_accounts(account_ids)


@mcp.tool
async def get_balances(session_id: str, account_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.plaid_session.get_balances(account_ids)


@mcp.tool
async def get_transactions(session_id: str, start_date: str | None = None, end_date: str | None = None, account_ids: List[str] | None = None, count: int = 100, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.plaid_session.get_transactions(start_date, end_date, account_ids, count, offset)


@mcp.tool
async def get_institution_by_id(institution_id: str, session_id: str, country_codes: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.plaid_session.get_institution_by_id(institution_id)


@mcp.tool
async def get_identity(session_id: str, account_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.plaid_session.get_identity(account_ids)
