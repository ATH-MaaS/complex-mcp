from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAlgoliaSession
except ImportError:
    from software.LightAlgolia.session import LightAlgoliaSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightAlgolia")

session_dict: Dict[str, LightAlgoliaSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAlgoliaSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.algolia_session.get_session_dict(),
    }


@mcp.tool
async def list_indexes(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.list_indexes()


@mcp.tool
async def get_settings(index: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.get_settings(index)


@mcp.tool
async def query_index(index: str, session_id: str, query: str | None = None, filters: str | None = None, hits_per_page: int = 20, page: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.query_index(index, query, filters, hits_per_page, page)


@mcp.tool
async def get_object(index: str, object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.get_object(index, object_id)


@mcp.tool
async def add_object(index: str, body: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.add_object(index, body)


@mcp.tool
async def update_object(index: str, object_id: str, body: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.update_object(index, object_id, body)


@mcp.tool
async def delete_object(index: str, object_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.algolia_session.delete_object(index, object_id)
