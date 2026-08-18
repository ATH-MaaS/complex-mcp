from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAlpacaSession
except ImportError:
    from software.LightAlpaca.session import LightAlpacaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAlpaca")

session_dict: Dict[str, LightAlpacaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAlpacaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.alpaca_session.get_session_dict(),
    }


@mcp.tool
async def get_account(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.get_account()


@mcp.tool
async def list_positions(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.list_positions()


@mcp.tool
async def get_position(symbol: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.get_position(symbol)


@mcp.tool
async def list_orders(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.list_orders(status)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.get_order(order_id)


@mcp.tool
async def create_order(symbol: str, qty: float, side: str, session_id: str, type: str = "market", time_in_force: str = "day", limit_price: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.create_order(symbol, qty, side, type, time_in_force, limit_price)


@mcp.tool
async def cancel_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.cancel_order(order_id)


@mcp.tool
async def list_assets(session_id: str, status: str | None = None, asset_class: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.list_assets(status, asset_class)


@mcp.tool
async def get_latest_quote(symbol: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.alpaca_session.get_latest_quote(symbol)
