from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightCoinbaseSession
except ImportError:
    from software.LightCoinbase.session import LightCoinbaseSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightCoinbase")

session_dict: Dict[str, LightCoinbaseSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightCoinbaseSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.coinbase_session.get_session_dict(),
    }


@mcp.tool
async def get_user(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.get_user()


@mcp.tool
async def list_accounts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.list_accounts()


@mcp.tool
async def get_account(account_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.get_account(account_id)


@mcp.tool
async def get_spot_price(pair: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.get_spot_price(pair)


@mcp.tool
async def create_buy(account_id: str, amount: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.create_buy(account_id, amount)


@mcp.tool
async def create_sell(account_id: str, amount: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.create_sell(account_id, amount)


@mcp.tool
async def list_transactions(account_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.coinbase_session.list_transactions(account_id)
