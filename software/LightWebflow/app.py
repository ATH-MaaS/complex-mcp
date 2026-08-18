from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightWebflowSession
except ImportError:
    from software.LightWebflow.session import LightWebflowSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightWebflow")

session_dict: Dict[str, LightWebflowSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightWebflowSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.webflow_session.get_session_dict(),
    }


@mcp.tool
async def list_sites(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.webflow_session.list_sites()


@mcp.tool
async def get_site(site_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.webflow_session.get_site(site_id)


@mcp.tool
async def list_collections(site_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.webflow_session.list_collections(site_id)


@mcp.tool
async def list_items(collection_id: str, session_id: str, limit: int = 100, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.webflow_session.list_items(collection_id, limit, offset)


@mcp.tool
async def create_item(collection_id: str, session_id: str, field_data: Dict[str, Any] | None = None, is_draft: bool = False, is_archived: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.webflow_session.create_item(collection_id, field_data, is_draft, is_archived)
