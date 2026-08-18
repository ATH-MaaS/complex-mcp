import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _opt_str(v):
    s = str(v).strip() if v is not None else ""
    return s or None


def _opt_int(v):
    if v is None or str(v).strip() == "":
        return None
    return int(v)


def _opt_float(v, default=0.0):
    if v is None or str(v).strip() == "":
        return default
    return float(v)


def _csv_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(t).strip() for t in v if str(t).strip()]
    s = str(v).strip()
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


class LinearSession:
    """Deterministic sandbox for the Linear mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "linear.yaml") as f:
                info = yaml.safe_load(f)

            self.workspace: Dict[str, Any] = info.get("workspace", {})

            self.teams: List[Dict[str, Any]] = [
                {
                    **t,
                    "id": str(t.get("id", "")),
                    "name": str(t.get("name", "")),
                    "key": str(t.get("key", "")),
                    "description": str(t.get("description", "")),
                    "color": str(t.get("color", "")),
                    "createdAt": str(t.get("createdAt", "")),
                    "updatedAt": str(t.get("updatedAt", "")),
                }
                for t in info.get("teams", [])
            ]

            self.users: List[Dict[str, Any]] = [
                {
                    **u,
                    "id": str(u.get("id", "")),
                    "name": str(u.get("name", "")),
                    "displayName": str(u.get("displayName", "")),
                    "email": str(u.get("email", "")),
                    "avatarUrl": str(u.get("avatarUrl", "")),
                    "active": _to_bool(u.get("active", False)),
                    "admin": _to_bool(u.get("admin", False)),
                    "teamId": str(u.get("teamId", "")),
                    "createdAt": str(u.get("createdAt", "")),
                    "updatedAt": str(u.get("updatedAt", "")),
                }
                for u in info.get("users", [])
            ]

            self.workflow_states: List[Dict[str, Any]] = [
                {
                    **s,
                    "id": str(s.get("id", "")),
                    "name": str(s.get("name", "")),
                    "type": str(s.get("type", "")),
                    "color": str(s.get("color", "")),
                    "position": int(s.get("position", 0)),
                    "teamId": str(s.get("teamId", "")),
                    "description": str(s.get("description", "")),
                }
                for s in info.get("workflow_states", [])
            ]

            self.labels: List[Dict[str, Any]] = [
                {
                    **l,
                    "id": str(l.get("id", "")),
                    "name": str(l.get("name", "")),
                    "color": str(l.get("color", "")),
                    "description": str(l.get("description", "")),
                    "teamId": _opt_str(l.get("teamId", "")),
                    "createdAt": str(l.get("createdAt", "")),
                    "updatedAt": str(l.get("updatedAt", "")),
                }
                for l in info.get("labels", [])
            ]

            self.projects: List[Dict[str, Any]] = [
                {
                    **p,
                    "id": str(p.get("id", "")),
                    "name": str(p.get("name", "")),
                    "description": str(p.get("description", "")),
                    "state": str(p.get("state", "")),
                    "leadId": _opt_str(p.get("leadId", "")),
                    "teamIds": _csv_list(p.get("teamIds")),
                    "startDate": _opt_str(p.get("startDate", "")),
                    "targetDate": _opt_str(p.get("targetDate", "")),
                    "createdAt": str(p.get("createdAt", "")),
                    "updatedAt": str(p.get("updatedAt", "")),
                }
                for p in info.get("projects", [])
            ]

            self.cycles: List[Dict[str, Any]] = [
                {
                    **c,
                    "id": str(c.get("id", "")),
                    "name": str(c.get("name", "")),
                    "number": int(c.get("number", 0)),
                    "teamId": str(c.get("teamId", "")),
                    "startsAt": str(c.get("startsAt", "")),
                    "endsAt": str(c.get("endsAt", "")),
                    "completedAt": _opt_str(c.get("completedAt", "")),
                    "createdAt": str(c.get("createdAt", "")),
                    "updatedAt": str(c.get("updatedAt", "")),
                }
                for c in info.get("cycles", [])
            ]

            self.issues: List[Dict[str, Any]] = [
                {
                    **i,
                    "id": str(i.get("id", "")),
                    "identifier": str(i.get("identifier", "")),
                    "number": int(i.get("number", 0)),
                    "title": str(i.get("title", "")),
                    "description": str(i.get("description", "")),
                    "priority": int(i.get("priority", 0)),
                    "estimate": _opt_int(i.get("estimate")),
                    "stateId": str(i.get("stateId", "")),
                    "assigneeId": _opt_str(i.get("assigneeId", "")),
                    "teamId": str(i.get("teamId", "")),
                    "projectId": _opt_str(i.get("projectId", "")),
                    "cycleId": _opt_str(i.get("cycleId", "")),
                    "labelIds": _csv_list(i.get("labelIds")),
                    "dueDate": _opt_str(i.get("dueDate", "")),
                    "sortOrder": _opt_float(i.get("sortOrder", 0.0)),
                    "branchName": _opt_str(i.get("branchName", "")),
                    "createdAt": str(i.get("createdAt", "")),
                    "updatedAt": str(i.get("updatedAt", "")),
                    "startedAt": _opt_str(i.get("startedAt", "")),
                    "completedAt": _opt_str(i.get("completedAt", "")),
                    "canceledAt": _opt_str(i.get("canceledAt", "")),
                }
                for i in info.get("issues", [])
            ]

            self.comments: List[Dict[str, Any]] = [
                {
                    **c,
                    "id": str(c.get("id", "")),
                    "body": str(c.get("body", "")),
                    "issueId": str(c.get("issueId", "")),
                    "userId": str(c.get("userId", "")),
                    "createdAt": str(c.get("createdAt", "")),
                    "updatedAt": str(c.get("updatedAt", "")),
                }
                for c in info.get("comments", [])
            ]

            self._next_issue_number = max((i["number"] for i in self.issues), default=0) + 1
            self._next_comment_id = len(self.comments) + 1
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightLinear')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"issues": self.issues, "comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    # --- Teams -------------------------------------------------------------
    def list_teams(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.teams)
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "teams", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_team(self, team_id: str) -> Dict[str, Any]:
        for t in self.teams:
            if t["id"] == team_id:
                return {"status": "ok", "output": {"type": "team", "team": t}}
        return {"status": "failed", "output": f"Team {team_id} not found"}

    def get_team_members(self, team_id: str) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        members = [u for u in self.users if u["teamId"] == team_id]
        return {"status": "ok", "output": {"type": "users", "count": len(members), "results": members}}

    def get_team_issues(self, team_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        issues = [i for i in self.issues if i["teamId"] == team_id]
        total = len(issues)
        page = issues[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_team_projects(self, team_id: str) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        projects = [p for p in self.projects if team_id in p["teamIds"]]
        return {"status": "ok", "output": {"type": "projects", "count": len(projects), "results": projects}}

    def get_team_cycles(self, team_id: str) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        cycles = [c for c in self.cycles if c["teamId"] == team_id]
        return {"status": "ok", "output": {"type": "cycles", "count": len(cycles), "results": cycles}}

    def get_team_workflow_states(self, team_id: str) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        states = [s for s in self.workflow_states if s["teamId"] == team_id]
        states = sorted(states, key=lambda x: x["position"])
        return {"status": "ok", "output": {"type": "workflow_states", "count": len(states), "results": states}}

    def get_team_labels(self, team_id: str) -> Dict[str, Any]:
        team = next((t for t in self.teams if t["id"] == team_id), None)
        if not team:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        labels = [l for l in self.labels if l["teamId"] == team_id or l["teamId"] is None]
        return {"status": "ok", "output": {"type": "labels", "count": len(labels), "results": labels}}

    # --- Users -------------------------------------------------------------
    def list_users(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.users)
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "users", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == user_id:
                return {"status": "ok", "output": {"type": "user", "user": u}}
        return {"status": "failed", "output": f"User {user_id} not found"}

    def get_user_assigned_issues(self, user_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        user = next((u for u in self.users if u["id"] == user_id), None)
        if not user:
            return {"status": "failed", "output": f"User {user_id} not found"}
        issues = [i for i in self.issues if i["assigneeId"] == user_id]
        total = len(issues)
        page = issues[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    # --- Workflow States ---------------------------------------------------
    def list_workflow_states(self, team_id: str | None = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.workflow_states)
        if team_id:
            results = [s for s in results if s["teamId"] == team_id]
        results = sorted(results, key=lambda x: (x["teamId"], x["position"]))
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "workflow_states", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_workflow_state(self, state_id: str) -> Dict[str, Any]:
        for s in self.workflow_states:
            if s["id"] == state_id:
                return {"status": "ok", "output": {"type": "workflow_state", "workflowState": s}}
        return {"status": "failed", "output": f"Workflow state {state_id} not found"}

    # --- Labels ------------------------------------------------------------
    def list_labels(self, team_id: str | None = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.labels)
        if team_id:
            results = [l for l in results if l["teamId"] == team_id or l["teamId"] is None]
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "labels", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_label(self, label_id: str) -> Dict[str, Any]:
        for l in self.labels:
            if l["id"] == label_id:
                return {"status": "ok", "output": {"type": "label", "label": l}}
        return {"status": "failed", "output": f"Label {label_id} not found"}

    def create_label(self, name: str, color: str, description: str | None = None,
                     teamId: str | None = None) -> Dict[str, Any]:
        if name is None:
            return {"status": "failed", "output": "Missing required field: name"}
        if color is None:
            return {"status": "failed", "output": "Missing required field: color"}
        now = self._now()
        label = {
            "id": self._generate_id("label"),
            "name": name,
            "color": color,
            "description": description if description is not None else "",
            "teamId": teamId,
            "createdAt": now,
            "updatedAt": now,
        }
        self.labels.append(label)
        return {"status": "ok", "output": {"type": "label", "label": label}}

    # --- Projects ----------------------------------------------------------
    def list_projects(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.projects)
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "projects", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_project(self, project_id: str) -> Dict[str, Any]:
        for p in self.projects:
            if p["id"] == project_id:
                return {"status": "ok", "output": {"type": "project", "project": p}}
        return {"status": "failed", "output": f"Project {project_id} not found"}

    def create_project(self, name: str, description: str | None = None, state: str | None = None,
                       leadId: str | None = None, teamIds: List[str] | None = None,
                       startDate: str | None = None, targetDate: str | None = None) -> Dict[str, Any]:
        if name is None:
            return {"status": "failed", "output": "Missing required field: name"}
        now = self._now()
        project = {
            "id": self._generate_id("proj"),
            "name": name,
            "description": description if description is not None else "",
            "state": state if state is not None else "planned",
            "leadId": leadId,
            "teamIds": teamIds if teamIds is not None else [],
            "startDate": startDate,
            "targetDate": targetDate,
            "createdAt": now,
            "updatedAt": now,
        }
        self.projects.append(project)
        return {"status": "ok", "output": {"type": "project", "project": project}}

    def update_project(self, project_id: str, name: str | None = None, description: str | None = None,
                       state: str | None = None, leadId: str | None = None, teamIds: List[str] | None = None,
                       startDate: str | None = None, targetDate: str | None = None) -> Dict[str, Any]:
        data = {k: v for k, v in {
            "name": name, "description": description, "state": state, "leadId": leadId,
            "teamIds": teamIds, "startDate": startDate, "targetDate": targetDate,
        }.items() if v is not None}
        for i, project in enumerate(self.projects):
            if project["id"] == project_id:
                updatable = {"name", "description", "state", "leadId", "teamIds",
                             "startDate", "targetDate"}
                for k, v in data.items():
                    if k in updatable:
                        self.projects[i][k] = v
                self.projects[i]["updatedAt"] = self._now()
                return {"status": "ok", "output": {"type": "project", "project": self.projects[i]}}
        return {"status": "failed", "output": f"Project {project_id} not found"}

    def get_project_issues(self, project_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        issues = [i for i in self.issues if i["projectId"] == project_id]
        total = len(issues)
        page = issues[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    # --- Cycles ------------------------------------------------------------
    def list_cycles(self, team_id: str | None = None, status: str | None = None,
                    limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.cycles)
        if team_id:
            results = [c for c in results if c["teamId"] == team_id]
        if status:
            now_str = self._now()
            if status == "current":
                results = [c for c in results if c["startsAt"] <= now_str[:10] and c["endsAt"] >= now_str[:10] and not c["completedAt"]]
            elif status == "past":
                results = [c for c in results if c["completedAt"] is not None]
            elif status == "upcoming":
                results = [c for c in results if c["startsAt"] > now_str[:10]]
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "cycles", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_cycle(self, cycle_id: str) -> Dict[str, Any]:
        for c in self.cycles:
            if c["id"] == cycle_id:
                return {"status": "ok", "output": {"type": "cycle", "cycle": c}}
        return {"status": "failed", "output": f"Cycle {cycle_id} not found"}

    def create_cycle(self, name: str, teamId: str, startsAt: str, endsAt: str) -> Dict[str, Any]:
        if name is None:
            return {"status": "failed", "output": "Missing required field: name"}
        if teamId is None:
            return {"status": "failed", "output": "Missing required field: teamId"}
        if startsAt is None:
            return {"status": "failed", "output": "Missing required field: startsAt"}
        if endsAt is None:
            return {"status": "failed", "output": "Missing required field: endsAt"}
        now = self._now()
        team_cycles = [c for c in self.cycles if c["teamId"] == teamId]
        next_num = max((c["number"] for c in team_cycles), default=0) + 1
        cycle = {
            "id": self._generate_id("cycle"),
            "name": name,
            "number": next_num,
            "teamId": teamId,
            "startsAt": startsAt,
            "endsAt": endsAt,
            "completedAt": None,
            "createdAt": now,
            "updatedAt": now,
        }
        self.cycles.append(cycle)
        return {"status": "ok", "output": {"type": "cycle", "cycle": cycle}}

    def get_cycle_issues(self, cycle_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        cycle = next((c for c in self.cycles if c["id"] == cycle_id), None)
        if not cycle:
            return {"status": "failed", "output": f"Cycle {cycle_id} not found"}
        issues = [i for i in self.issues if i["cycleId"] == cycle_id]
        total = len(issues)
        page = issues[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    # --- Issues ------------------------------------------------------------
    def list_issues(self, state_id: str | None = None, assignee_id: str | None = None,
                    project_id: str | None = None, cycle_id: str | None = None,
                    team_id: str | None = None, priority: int | None = None,
                    label_id: str | None = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        results = list(self.issues)
        if state_id:
            results = [i for i in results if i["stateId"] == state_id]
        if assignee_id:
            results = [i for i in results if i["assigneeId"] == assignee_id]
        if project_id:
            results = [i for i in results if i["projectId"] == project_id]
        if cycle_id:
            results = [i for i in results if i["cycleId"] == cycle_id]
        if team_id:
            results = [i for i in results if i["teamId"] == team_id]
        if priority is not None:
            results = [i for i in results if i["priority"] == priority]
        if label_id:
            results = [i for i in results if label_id in i["labelIds"]]
        results = sorted(results, key=lambda x: x["sortOrder"])
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def search_issues(self, query: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        q = query.lower()
        results = [
            i for i in self.issues
            if q in i["title"].lower() or q in i["description"].lower() or q in i["identifier"].lower()
        ]
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "issues", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_issue(self, issue_id: str) -> Dict[str, Any]:
        for i in self.issues:
            if i["id"] == issue_id:
                return {"status": "ok", "output": {"type": "issue", "issue": i}}
        return {"status": "failed", "output": f"Issue {issue_id} not found"}

    def create_issue(self, title: str, teamId: str, description: str | None = None,
                     priority: int | None = None, estimate: int | None = None,
                     stateId: str | None = None, assigneeId: str | None = None,
                     projectId: str | None = None, cycleId: str | None = None,
                     labelIds: List[str] | None = None, dueDate: str | None = None) -> Dict[str, Any]:
        if title is None:
            return {"status": "failed", "output": "Missing required field: title"}
        if teamId is None:
            return {"status": "failed", "output": "Missing required field: teamId"}
        now = self._now()
        number = self._next_issue_number
        identifier = f"MER-{number}"

        branch_name = None
        if assigneeId:
            assignee = next((u for u in self.users if u["id"] == assigneeId), None)
            if assignee:
                slug = title.lower().replace(" ", "-")[:40]
                branch_name = f"{assignee['name']}/{identifier.lower()}-{slug}"

        state_id = stateId
        if not state_id:
            team_states = [s for s in self.workflow_states if s["teamId"] == teamId and s["type"] == "backlog"]
            if team_states:
                state_id = team_states[0]["id"]

        issue = {
            "id": self._generate_id("issue"),
            "identifier": identifier,
            "number": number,
            "title": title,
            "description": description if description is not None else "",
            "priority": priority if priority is not None else 0,
            "estimate": estimate,
            "stateId": state_id,
            "assigneeId": assigneeId,
            "teamId": teamId,
            "projectId": projectId,
            "cycleId": cycleId,
            "labelIds": labelIds if labelIds is not None else [],
            "dueDate": dueDate,
            "sortOrder": float(number),
            "branchName": branch_name,
            "createdAt": now,
            "updatedAt": now,
            "startedAt": None,
            "completedAt": None,
            "canceledAt": None,
        }
        self.issues.append(issue)
        self._next_issue_number += 1
        return {"status": "ok", "output": {"type": "issue", "issue": issue}}

    def update_issue(self, issue_id: str, title: str | None = None, description: str | None = None,
                     priority: int | None = None, estimate: int | None = None, stateId: str | None = None,
                     assigneeId: str | None = None, projectId: str | None = None, cycleId: str | None = None,
                     labelIds: List[str] | None = None, dueDate: str | None = None,
                     sortOrder: float | None = None) -> Dict[str, Any]:
        data = {k: v for k, v in {
            "title": title, "description": description, "priority": priority, "estimate": estimate,
            "stateId": stateId, "assigneeId": assigneeId, "projectId": projectId, "cycleId": cycleId,
            "labelIds": labelIds, "dueDate": dueDate, "sortOrder": sortOrder,
        }.items() if v is not None}
        for i, issue in enumerate(self.issues):
            if issue["id"] == issue_id:
                updatable = {"title", "description", "priority", "estimate", "stateId",
                             "assigneeId", "projectId", "cycleId", "labelIds", "dueDate",
                             "sortOrder"}
                for k, v in data.items():
                    if k in updatable:
                        if k == "priority" and v is not None:
                            self.issues[i][k] = int(v)
                        elif k == "estimate" and v is not None:
                            self.issues[i][k] = int(v)
                        elif k == "sortOrder" and v is not None:
                            self.issues[i][k] = float(v)
                        else:
                            self.issues[i][k] = v

                if "stateId" in data:
                    new_state = next((s for s in self.workflow_states if s["id"] == data["stateId"]), None)
                    if new_state:
                        now = self._now()
                        if new_state["type"] == "started" and not self.issues[i]["startedAt"]:
                            self.issues[i]["startedAt"] = now
                        elif new_state["type"] == "completed":
                            self.issues[i]["completedAt"] = now
                            if not self.issues[i]["startedAt"]:
                                self.issues[i]["startedAt"] = now
                        elif new_state["type"] == "cancelled":
                            self.issues[i]["canceledAt"] = now

                self.issues[i]["updatedAt"] = self._now()

                if "assigneeId" in data and data["assigneeId"]:
                    assignee = next((u for u in self.users if u["id"] == data["assigneeId"]), None)
                    if assignee:
                        slug = self.issues[i]["title"].lower().replace(" ", "-")[:40]
                        self.issues[i]["branchName"] = f"{assignee['name']}/{self.issues[i]['identifier'].lower()}-{slug}"

                return {"status": "ok", "output": {"type": "issue", "issue": self.issues[i]}}
        return {"status": "failed", "output": f"Issue {issue_id} not found"}

    def delete_issue(self, issue_id: str) -> Dict[str, Any]:
        for i, issue in enumerate(self.issues):
            if issue["id"] == issue_id:
                self.issues.pop(i)
                return {"status": "ok", "output": {"type": "issue", "deleted": True, "issueId": issue_id}}
        return {"status": "failed", "output": f"Issue {issue_id} not found"}

    # --- Comments ----------------------------------------------------------
    def list_comments(self, issue_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        issue = next((i for i in self.issues if i["id"] == issue_id), None)
        if not issue:
            return {"status": "failed", "output": f"Issue {issue_id} not found"}
        results = [c for c in self.comments if c["issueId"] == issue_id]
        results = sorted(results, key=lambda x: x["createdAt"])
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "comments", "count": len(page), "total": total,
            "offset": offset, "limit": limit, "results": page,
        }}

    def get_comment(self, comment_id: str) -> Dict[str, Any]:
        for c in self.comments:
            if c["id"] == comment_id:
                return {"status": "ok", "output": {"type": "comment", "comment": c}}
        return {"status": "failed", "output": f"Comment {comment_id} not found"}

    def create_comment(self, body: str, issueId: str, userId: str | None = None) -> Dict[str, Any]:
        if body is None:
            return {"status": "failed", "output": "Missing required field: body"}
        if issueId is None:
            return {"status": "failed", "output": "Missing required field: issueId"}
        issue = next((i for i in self.issues if i["id"] == issueId), None)
        if not issue:
            return {"status": "failed", "output": f"Issue {issueId} not found"}
        now = self._now()
        comment = {
            "id": f"comment-{self._next_comment_id:02d}",
            "body": body,
            "issueId": issueId,
            "userId": userId if userId is not None else "user-01",
            "createdAt": now,
            "updatedAt": now,
        }
        self.comments.append(comment)
        self._next_comment_id += 1
        return {"status": "ok", "output": {"type": "comment", "comment": comment}}

    def update_comment(self, comment_id: str, body: str) -> Dict[str, Any]:
        for i, comment in enumerate(self.comments):
            if comment["id"] == comment_id:
                if body is not None:
                    self.comments[i]["body"] = body
                self.comments[i]["updatedAt"] = self._now()
                return {"status": "ok", "output": {"type": "comment", "comment": self.comments[i]}}
        return {"status": "failed", "output": f"Comment {comment_id} not found"}

    def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        for i, comment in enumerate(self.comments):
            if comment["id"] == comment_id:
                self.comments.pop(i)
                return {"status": "ok", "output": {"type": "comment", "deleted": True, "commentId": comment_id}}
        return {"status": "failed", "output": f"Comment {comment_id} not found"}


if __name__ == "__main__":
    s = LinearSession(seed=12)
    print(s.list_teams())
    print(s.list_issues())
