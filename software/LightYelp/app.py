from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightYelpSession
except ImportError:
    from software.LightYelp.session import LightYelpSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightYelp")

session_dict: Dict[str, LightYelpSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightYelpSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.yelp_session.get_session_dict(),
    }


@mcp.tool
async def search_businesses(session_id: str, term: str | None = None, location: str | None = None, categories: str | None = None, price: str | None = None, sort_by: str = "best_match", limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.yelp_session.search_businesses(term, location, categories, price, sort_by, limit, offset)


@mcp.tool
async def get_business(business_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.yelp_session.get_business(business_id)


@mcp.tool
async def get_business_reviews(business_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.yelp_session.get_business_reviews(business_id)


@mcp.tool
async def list_categories(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.yelp_session.list_categories()
