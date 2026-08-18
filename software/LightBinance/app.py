from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightBinanceSession
except ImportError:
    from software.LightBinance.session import LightBinanceSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightBinance")

session_dict: Dict[str, LightBinanceSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightBinanceSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.binance_session.get_session_dict(),
    }


@mcp.tool
async def get_ticker_price(session_id: str, symbol: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.binance_session.get_ticker_price(symbol)


@mcp.tool
async def get_ticker_24hr(session_id: str, symbol: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.binance_session.get_ticker_24hr(symbol)


@mcp.tool
async def get_depth(symbol: str, session_id: str, limit: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.binance_session.get_depth(symbol, limit)


@mcp.tool
async def get_klines(symbol: str, session_id: str, interval: str = "1h", limit: int = 500):
	session, err = get_session(session_id)
	if err:
		return err
	return session.binance_session.get_klines(symbol, interval, limit)


@mcp.tool
async def get_account(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.binance_session.get_account()
