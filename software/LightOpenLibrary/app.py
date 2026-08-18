from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightOpenLibrarySession
except ImportError:
    from software.LightOpenLibrary.session import LightOpenLibrarySession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightOpenLibrary")

session_dict: Dict[str, LightOpenLibrarySession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightOpenLibrarySession(os_cfg=os_cfg, seed=seed)
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
        "output": session.openlibrary_session.get_session_dict(),
    }


@mcp.tool
async def search(session_id: str, q: str | None = None, author: str | None = None, title: str | None = None, page: int = 1, limit: int = 20):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.search(q, author, title, page, limit)


@mcp.tool
async def get_work(work_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_work(work_id)


@mcp.tool
async def get_work_editions(work_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_work_editions(work_id)


@mcp.tool
async def get_author(author_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_author(author_id)


@mcp.tool
async def get_author_works(author_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_author_works(author_id)


@mcp.tool
async def get_subject(subject: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_subject(subject)


@mcp.tool
async def get_isbn(isbn: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.openlibrary_session.get_isbn(isbn)
