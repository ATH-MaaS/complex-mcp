from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightContentfulSession
except ImportError:
    from software.LightContentful.session import LightContentfulSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightContentful")

session_dict: Dict[str, LightContentfulSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightContentfulSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.contentful_session.get_session_dict(),
    }


@mcp.tool
async def get_space(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.get_space()


@mcp.tool
async def list_content_types(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.list_content_types()


@mcp.tool
async def get_content_type(content_type_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.get_content_type(content_type_id)


@mcp.tool
async def list_entries(session_id: str, content_type: str | None = None, field_filters: Dict[str, Any] | None = None, limit: int = 100, skip: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.list_entries(content_type, field_filters, limit, skip)


@mcp.tool
async def get_entry(entry_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.get_entry(entry_id)


@mcp.tool
async def create_entry(content_type: str, session_id: str, fields: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.create_entry(content_type, fields)


@mcp.tool
async def update_entry(entry_id: str, session_id: str, fields: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.update_entry(entry_id, fields)


@mcp.tool
async def delete_entry(entry_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.delete_entry(entry_id)


@mcp.tool
async def list_assets(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.list_assets()


@mcp.tool
async def get_asset(asset_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.contentful_session.get_asset(asset_id)
