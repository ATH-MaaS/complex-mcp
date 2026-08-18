from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightZillowSession
except ImportError:
    from software.LightZillow.session import LightZillowSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightZillow")

session_dict: Dict[str, LightZillowSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightZillowSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.zillow_session.get_session_dict(),
    }


@mcp.tool
async def search_properties(session_id: str, city: str | None = None, state: str | None = None, zipcode: str | None = None, min_price: int | None = None, max_price: int | None = None, min_beds: int | None = None, min_baths: float | None = None, home_type: str | None = None, status: str = "FOR_SALE", limit: int = 25, offset: int = 0, sort_by: str = "list_price", sort_order: str = "asc"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.search_properties(city, state, zipcode, min_price, max_price, min_beds, min_baths, home_type, status, limit, offset, sort_by, sort_order)


@mcp.tool
async def get_property(zpid: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.get_property(zpid)


@mcp.tool
async def get_zestimate(zpid: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.get_zestimate(zpid)


@mcp.tool
async def get_price_history(zpid: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.get_price_history(zpid)


@mcp.tool
async def list_agents(session_id: str, city: str | None = None, state: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.list_agents(city, state)


@mcp.tool
async def get_agent(agent_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.get_agent(agent_id)


@mcp.tool
async def list_saved_searches(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.list_saved_searches(user_id)


@mcp.tool
async def create_saved_search(user_id: str, name: str, session_id: str, city: str | None = None, state: str | None = None, min_price: int = 0, max_price: int = 10000000, min_beds: int = 0, min_baths: float = 0.0, home_type: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.create_saved_search(user_id, name, city, state, min_price, max_price, min_beds, min_baths, home_type)


@mcp.tool
async def delete_saved_search(search_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.zillow_session.delete_saved_search(search_id)
