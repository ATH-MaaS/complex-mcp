from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightLinearSession
except ImportError:
    from software.LightLinear.session import LightLinearSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightLinear")

session_dict: Dict[str, LightLinearSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightLinearSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.linear_session.get_session_dict(),
    }


@mcp.tool
async def list_teams(session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_teams(limit, offset)


@mcp.tool
async def get_team(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team(team_id)


@mcp.tool
async def get_team_members(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_members(team_id)


@mcp.tool
async def get_team_issues(team_id: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_issues(team_id, limit, offset)


@mcp.tool
async def get_team_projects(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_projects(team_id)


@mcp.tool
async def get_team_cycles(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_cycles(team_id)


@mcp.tool
async def get_team_workflow_states(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_workflow_states(team_id)


@mcp.tool
async def get_team_labels(team_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_team_labels(team_id)


@mcp.tool
async def list_users(session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_users(limit, offset)


@mcp.tool
async def get_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_user(user_id)


@mcp.tool
async def get_user_assigned_issues(user_id: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_user_assigned_issues(user_id, limit, offset)


@mcp.tool
async def list_workflow_states(session_id: str, team_id: str | None = None, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_workflow_states(team_id, limit, offset)


@mcp.tool
async def get_workflow_state(state_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_workflow_state(state_id)


@mcp.tool
async def list_labels(session_id: str, team_id: str | None = None, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_labels(team_id, limit, offset)


@mcp.tool
async def get_label(label_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_label(label_id)


@mcp.tool
async def create_label(name: str, color: str, session_id: str, description: str | None = None, teamId: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.create_label(name, color, description, teamId)


@mcp.tool
async def list_projects(session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_projects(limit, offset)


@mcp.tool
async def get_project(project_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_project(project_id)


@mcp.tool
async def create_project(name: str, session_id: str, description: str | None = None, state: str | None = None, leadId: str | None = None, teamIds: List[str] | None = None, startDate: str | None = None, targetDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.create_project(name, description, state, leadId, teamIds, startDate, targetDate)


@mcp.tool
async def update_project(project_id: str, session_id: str, name: str | None = None, description: str | None = None, state: str | None = None, leadId: str | None = None, teamIds: List[str] | None = None, startDate: str | None = None, targetDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.update_project(project_id, name, description, state, leadId, teamIds, startDate, targetDate)


@mcp.tool
async def get_project_issues(project_id: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_project_issues(project_id, limit, offset)


@mcp.tool
async def list_cycles(session_id: str, team_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_cycles(team_id, status, limit, offset)


@mcp.tool
async def get_cycle(cycle_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_cycle(cycle_id)


@mcp.tool
async def create_cycle(name: str, teamId: str, startsAt: str, endsAt: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.create_cycle(name, teamId, startsAt, endsAt)


@mcp.tool
async def get_cycle_issues(cycle_id: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_cycle_issues(cycle_id, limit, offset)


@mcp.tool
async def list_issues(session_id: str, state_id: str | None = None, assignee_id: str | None = None, project_id: str | None = None, cycle_id: str | None = None, team_id: str | None = None, priority: int | None = None, label_id: str | None = None, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_issues(state_id, assignee_id, project_id, cycle_id, team_id, priority, label_id, limit, offset)


@mcp.tool
async def search_issues(query: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.search_issues(query, limit, offset)


@mcp.tool
async def get_issue(issue_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_issue(issue_id)


@mcp.tool
async def create_issue(title: str, teamId: str, session_id: str, description: str | None = None, priority: int | None = None, estimate: int | None = None, stateId: str | None = None, assigneeId: str | None = None, projectId: str | None = None, cycleId: str | None = None, labelIds: List[str] | None = None, dueDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.create_issue(title, teamId, description, priority, estimate, stateId, assigneeId, projectId, cycleId, labelIds, dueDate)


@mcp.tool
async def update_issue(issue_id: str, session_id: str, title: str | None = None, description: str | None = None, priority: int | None = None, estimate: int | None = None, stateId: str | None = None, assigneeId: str | None = None, projectId: str | None = None, cycleId: str | None = None, labelIds: List[str] | None = None, dueDate: str | None = None, sortOrder: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.update_issue(issue_id, title, description, priority, estimate, stateId, assigneeId, projectId, cycleId, labelIds, dueDate, sortOrder)


@mcp.tool
async def delete_issue(issue_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.delete_issue(issue_id)


@mcp.tool
async def list_comments(issue_id: str, session_id: str, limit: int = 50, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.list_comments(issue_id, limit, offset)


@mcp.tool
async def get_comment(comment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.get_comment(comment_id)


@mcp.tool
async def create_comment(body: str, issueId: str, session_id: str, userId: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.create_comment(body, issueId, userId)


@mcp.tool
async def update_comment(comment_id: str, body: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.update_comment(comment_id, body)


@mcp.tool
async def delete_comment(comment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.linear_session.delete_comment(comment_id)
