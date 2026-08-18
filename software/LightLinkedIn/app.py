from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightLinkedInSession
except ImportError:
    from software.LightLinkedIn.session import LightLinkedInSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightLinkedIn")

session_dict: Dict[str, LightLinkedInSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightLinkedInSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.linkedin_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.get_me()


@mcp.tool
async def list_connections(session_id: str, start: int = 0, count: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.list_connections(start, count)


@mcp.tool
async def list_posts(session_id: str, author_id: str | None = None, start: int = 0, count: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.list_posts(author_id, start, count)


@mcp.tool
async def get_post(post_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.get_post(post_id)


@mcp.tool
async def create_post(commentary: str, session_id: str, author_id: str | None = None, visibility: str = "PUBLIC"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.create_post(commentary, author_id, visibility)


@mcp.tool
async def get_organization(org_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.get_organization(org_id)


@mcp.tool
async def search_jobs(session_id: str, keywords: str | None = None, location: str | None = None, start: int = 0, count: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.search_jobs(keywords, location, start, count)


@mcp.tool
async def get_job(job_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linkedin_session.get_job(job_id)
