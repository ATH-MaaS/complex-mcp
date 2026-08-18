from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAirtableSession
except ImportError:
    from software.LightAirtable.session import LightAirtableSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAirtable")

session_dict: Dict[str, LightAirtableSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAirtableSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.airtable_session.get_session_dict(),
    }


@mcp.tool
async def list_bases(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.list_bases()


@mcp.tool
async def list_tables(base_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.list_tables(base_id)


@mcp.tool
async def list_records(base_id: str, table_id_or_name: str, session_id: str, page_size: int = 100, offset: str | None = None, filter_by_formula: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.list_records(base_id, table_id_or_name, page_size, offset, filter_by_formula)


@mcp.tool
async def get_record(base_id: str, table_id_or_name: str, record_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.get_record(base_id, table_id_or_name, record_id)


@mcp.tool
async def create_records(base_id: str, table_id_or_name: str, records: List[Dict[str, Any]], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.create_records(base_id, table_id_or_name, records)


@mcp.tool
async def update_record(base_id: str, table_id_or_name: str, record_id: str, fields: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.update_record(base_id, table_id_or_name, record_id, fields)


@mcp.tool
async def delete_record(base_id: str, table_id_or_name: str, record_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.airtable_session.delete_record(base_id, table_id_or_name, record_id)
