from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGitlabSession
except ImportError:
    from software.LightGitlab.session import LightGitlabSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightGitlab")

session_dict: Dict[str, LightGitlabSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGitlabSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.gitlab_session.get_session_dict(),
    }


@mcp.tool
async def get_current_user(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.get_current_user()


@mcp.tool
async def list_users(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.list_users()


@mcp.tool
async def list_projects(session_id: str, visibility: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.list_projects(visibility)


@mcp.tool
async def get_project(project_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.get_project(project_id)


@mcp.tool
async def list_issues(project_id: str, session_id: str, state: str | None = None, labels: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.list_issues(project_id, state, labels)


@mcp.tool
async def get_issue(project_id: str, issue_iid: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.get_issue(project_id, issue_iid)


@mcp.tool
async def create_issue(project_id: str, title: str, session_id: str, description: str = "", assignee: str | None = None, labels: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.create_issue(project_id, title, description, assignee, labels)


@mcp.tool
async def update_issue(project_id: str, issue_iid: int, session_id: str, title: str | None = None, description: str | None = None, state_event: str | None = None, assignee: str | None = None, labels: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.update_issue(project_id, issue_iid, title, description, state_event, assignee, labels)


@mcp.tool
async def list_merge_requests(project_id: str, session_id: str, state: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.list_merge_requests(project_id, state)


@mcp.tool
async def create_merge_request(project_id: str, title: str, source_branch: str, session_id: str, target_branch: str = "main", description: str = "", assignee: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.create_merge_request(project_id, title, source_branch, target_branch, description, assignee)


@mcp.tool
async def merge_merge_request(project_id: str, mr_iid: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.merge_merge_request(project_id, mr_iid)


@mcp.tool
async def list_pipelines(project_id: str, session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gitlab_session.list_pipelines(project_id, status)
