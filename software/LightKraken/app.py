from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightKrakenSession
except ImportError:
    from software.LightKraken.session import LightKrakenSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightKraken")

session_dict: Dict[str, LightKrakenSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightKrakenSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.kraken_session.get_session_dict(),
    }


@mcp.tool
async def get_ticker(session_id: str, pair: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kraken_session.get_ticker(pair)


@mcp.tool
async def get_ohlc(pair: str, session_id: str, interval: int = 60):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kraken_session.get_ohlc(pair, interval)


@mcp.tool
async def get_asset_pairs(session_id: str, pair: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kraken_session.get_asset_pairs(pair)


@mcp.tool
async def get_assets(session_id: str, asset: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kraken_session.get_assets(asset)


@mcp.tool
async def get_balance(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kraken_session.get_balance()
