from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightUPSSession
except ImportError:
    from software.LightUPS.session import LightUPSSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightUPS")

session_dict: Dict[str, LightUPSSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightUPSSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.ups_session.get_session_dict(),
    }


@mcp.tool
async def get_rate(origin_zip: str, dest_zip: str, session_id: str, weight_lb: float = 1.0, service_code: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ups_session.get_rate(origin_zip, dest_zip, weight_lb, service_code)


@mcp.tool
async def create_shipment(origin_zip: str, dest_zip: str, session_id: str, weight_lb: float = 1.0, service_code: str = "03"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ups_session.create_shipment(origin_zip, dest_zip, weight_lb, service_code)


@mcp.tool
async def track(tracking_number: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ups_session.track(tracking_number)
