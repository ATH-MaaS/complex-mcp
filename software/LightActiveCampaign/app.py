from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightActiveCampaignSession
except ImportError:
    from software.LightActiveCampaign.session import LightActiveCampaignSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightActiveCampaign")

session_dict: Dict[str, LightActiveCampaignSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightActiveCampaignSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.activecampaign_session.get_session_dict(),
    }


@mcp.tool
async def list_contacts(session_id: str, email: str | None = None, status: str | None = None, limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.list_contacts(email, status, limit, offset)


@mcp.tool
async def get_contact(contact_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.get_contact(contact_id)


@mcp.tool
async def create_contact(email: str, session_id: str, first_name: str = "", last_name: str = "", phone: str = "", status: str = "1"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.create_contact(email, first_name, last_name, phone, status)


@mcp.tool
async def list_lists(session_id: str, limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.list_lists(limit, offset)


@mcp.tool
async def list_campaigns(session_id: str, limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.list_campaigns(limit, offset)


@mcp.tool
async def list_deals(session_id: str, limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.activecampaign_session.list_deals(limit, offset)
