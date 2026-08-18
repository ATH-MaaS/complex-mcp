from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightFedExSession
except ImportError:
    from software.LightFedEx.session import LightFedExSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightFedEx")

session_dict: Dict[str, LightFedExSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightFedExSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.fedex_session.get_session_dict(),
    }


@mcp.tool
async def get_rate_quote(origin_zip: str, dest_zip: str, session_id: str, weight_lb: float = 1.0, service_type: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.fedex_session.get_rate_quote(origin_zip, dest_zip, weight_lb, service_type)


@mcp.tool
async def create_shipment(origin_zip: str, dest_zip: str, session_id: str, weight_lb: float = 1.0, service_type: str = "FEDEX_GROUND"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.fedex_session.create_shipment(origin_zip, dest_zip, weight_lb, service_type)


@mcp.tool
async def track(tracking_number: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.fedex_session.track(tracking_number)
