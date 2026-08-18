from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightShippoSession
except ImportError:
    from software.LightShippo.session import LightShippoSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightShippo")

session_dict: Dict[str, LightShippoSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightShippoSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.shippo_session.get_session_dict(),
    }


@mcp.tool
async def create_address(name: str, session_id: str, company: str = "", street1: str = "", street2: str = "", city: str = "", state: str = "", zip: str = "", country: str = "US", phone: str = "", email: str = "", is_residential: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.create_address(name, company, street1, street2, city, state, zip, country, phone, email, is_residential)


@mcp.tool
async def get_address(object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.get_address(object_id)


@mcp.tool
async def create_shipment(address_from: str, address_to: str, session_id: str, parcels: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.create_shipment(address_from, address_to, parcels)


@mcp.tool
async def get_shipment(object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.get_shipment(object_id)


@mcp.tool
async def list_shipment_rates(object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.list_shipment_rates(object_id)


@mcp.tool
async def create_transaction(rate: str, session_id: str, label_file_type: str = "PDF", async_: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.create_transaction(rate, label_file_type, async_)


@mcp.tool
async def get_transaction(object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.get_transaction(object_id)


@mcp.tool
async def get_tracking(carrier: str, tracking_number: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.shippo_session.get_tracking(carrier, tracking_number)
