from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightSalesforceSession
except ImportError:
    from software.LightSalesforce.session import LightSalesforceSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightSalesforce")

session_dict: Dict[str, LightSalesforceSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightSalesforceSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.salesforce_session.get_session_dict(),
    }


@mcp.tool
async def list_records(sobject: str, session_id: str, limit: int = 200):
	session, err = get_session(session_id)
	if err:
		return err
	return session.salesforce_session.list_records(sobject, limit)


@mcp.tool
async def get_record(sobject: str, record_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.salesforce_session.get_record(sobject, record_id)


@mcp.tool
async def create_record(sobject: str, session_id: str, fields: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.salesforce_session.create_record(sobject, fields)


@mcp.tool
async def update_record(sobject: str, record_id: str, session_id: str, fields: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.salesforce_session.update_record(sobject, record_id, fields)


@mcp.tool
async def soql_query(q: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.salesforce_session.soql_query(q)
