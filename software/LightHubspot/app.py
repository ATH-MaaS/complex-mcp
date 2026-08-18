from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightHubspotSession
except ImportError:
    from software.LightHubspot.session import LightHubspotSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightHubspot")

session_dict: Dict[str, LightHubspotSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightHubspotSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.hubspot_session.get_session_dict(),
    }


@mcp.tool
async def list_contacts(session_id: str, limit: int = 10, after: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.list_contacts(limit, after)


@mcp.tool
async def get_contact(contact_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.get_contact(contact_id)


@mcp.tool
async def create_contact(session_id: str, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.create_contact(properties)


@mcp.tool
async def update_contact(contact_id: str, session_id: str, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.update_contact(contact_id, properties)


@mcp.tool
async def list_companies(session_id: str, limit: int = 10, after: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.list_companies(limit, after)


@mcp.tool
async def get_company(company_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.get_company(company_id)


@mcp.tool
async def list_deals(session_id: str, limit: int = 10, after: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.list_deals(limit, after)


@mcp.tool
async def get_deal(deal_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.get_deal(deal_id)


@mcp.tool
async def create_deal(session_id: str, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.create_deal(properties)


@mcp.tool
async def update_deal(deal_id: str, session_id: str, properties: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.update_deal(deal_id, properties)


@mcp.tool
async def list_deal_pipelines(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.hubspot_session.list_deal_pipelines()
