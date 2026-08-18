from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTMDBSession
except ImportError:
    from software.LightTMDB.session import LightTMDBSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTMDB")

session_dict: Dict[str, LightTMDBSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTMDBSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.tmdb_session.get_session_dict(),
    }


@mcp.tool
async def search_movie(query: str, session_id: str, page: int = 1):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.search_movie(query, page)


@mcp.tool
async def movie_popular(session_id: str, page: int = 1):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.movie_popular(page)


@mcp.tool
async def get_movie(movie_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.get_movie(movie_id)


@mcp.tool
async def movie_credits(movie_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.movie_credits(movie_id)


@mcp.tool
async def get_tv(tv_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.get_tv(tv_id)


@mcp.tool
async def genre_movie_list(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.genre_movie_list()


@mcp.tool
async def trending_all_week(session_id: str, page: int = 1):
	session, err = get_session(session_id)
	if err:
		return err
	return session.tmdb_session.trending_all_week(page)
