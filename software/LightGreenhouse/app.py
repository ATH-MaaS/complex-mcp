from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGreenhouseSession
except ImportError:
    from software.LightGreenhouse.session import LightGreenhouseSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightGreenhouse")

session_dict: Dict[str, LightGreenhouseSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGreenhouseSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.greenhouse_session.get_session_dict(),
    }


@mcp.tool
async def list_candidates(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.list_candidates()


@mcp.tool
async def get_candidate(candidate_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.get_candidate(candidate_id)


@mcp.tool
async def create_candidate(first_name: str, last_name: str, session_id: str, email: str | None = None, phone: str | None = None, company: str | None = None, title: str | None = None, source: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.create_candidate(first_name, last_name, email, phone, company, title, source)


@mcp.tool
async def list_jobs(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.list_jobs(status)


@mcp.tool
async def get_job(job_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.get_job(job_id)


@mcp.tool
async def list_applications(session_id: str, job_id: str | None = None, candidate_id: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.list_applications(job_id, candidate_id, status)


@mcp.tool
async def get_application(application_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.get_application(application_id)


@mcp.tool
async def advance_application(application_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.advance_application(application_id)


@mcp.tool
async def reject_application(application_id: str, session_id: str, reason: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.reject_application(application_id, reason)


@mcp.tool
async def list_scorecards(session_id: str, application_id: str | None = None, candidate_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.greenhouse_session.list_scorecards(application_id, candidate_id)
