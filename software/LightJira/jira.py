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


_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}


def _strict_int(v) -> int:
    return int(str(v).strip())


def _strict_bool(v) -> bool:
    token = str(v).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return False


def _opt_int(v, default=None):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_str(v, default=""):
    if v is None:
        return default
    return str(v)


# Workflow: status name -> {transition_id: target_status}
_WORKFLOW = {
    "To Do": {"11": "In Progress"},
    "In Progress": {"21": "Done", "31": "To Do"},
    "Done": {"41": "In Progress"},
}

_STATUS_CATEGORY = {
    "To Do": {"id": 2, "key": "new", "name": "To Do"},
    "In Progress": {"id": 4, "key": "indeterminate", "name": "In Progress"},
    "Done": {"id": 3, "key": "done", "name": "Done"},
}


class JiraSession:
    """Deterministic sandbox for the Jira mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "jira.yaml") as f:
                info = yaml.safe_load(f)

            self.projects: List[Dict[str, Any]] = [
                {**p, "id": p["id"]} for p in info.get("projects", [])
            ]
            self.users: List[Dict[str, Any]] = [
                {**u, "active": _strict_bool(u.get("active"))} for u in info.get("users", [])
            ]
            self.boards: List[Dict[str, Any]] = [
                {**b, "id": _strict_int(b["id"])} for b in info.get("boards", [])
            ]
            self.sprints: List[Dict[str, Any]] = [
                {
                    **s,
                    "id": _strict_int(s["id"]),
                    "board_id": _strict_int(s["board_id"]),
                    "start_date": _opt_str(s.get("start_date"), default="") or None,
                    "end_date": _opt_str(s.get("end_date"), default="") or None,
                }
                for s in info.get("sprints", [])
            ]
            self.issues: List[Dict[str, Any]] = [
                {
                    **i,
                    "id": i["id"],
                    "sprint_id": _opt_int(i.get("sprint_id"), default=0),
                    "story_points": _opt_int(i.get("story_points"), default=0),
                    "assignee": _opt_str(i.get("assignee"), default="") or None,
                }
                for i in info.get("issues", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightJira')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"issues": self.issues}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _user_obj(self, account_id):
        u = next((x for x in self.users if x["account_id"] == account_id), None)
        if not u:
            return None
        return {
            "accountId": u["account_id"],
            "displayName": u["display_name"],
            "emailAddress": u["email"],
            "active": u["active"],
        }

    def _serialize_issue(self, i):
        status_cat = _STATUS_CATEGORY.get(i["status"], _STATUS_CATEGORY["To Do"])
        return {
            "id": i["id"],
            "key": i["key"],
            "fields": {
                "summary": i["summary"],
                "description": i["description"],
                "issuetype": {"name": i["issue_type"]},
                "project": {"key": i["project_key"]},
                "status": {"name": i["status"], "statusCategory": status_cat},
                "priority": {"name": i["priority"]},
                "assignee": self._user_obj(i["assignee"]) if i["assignee"] else None,
                "reporter": self._user_obj(i["reporter"]),
                "customfield_10016": i["story_points"],
                "created": i["created"],
                "updated": i["updated"],
            },
        }

    def _serialize_project(self, p):
        return {
            "id": p["id"],
            "key": p["key"],
            "name": p["name"],
            "projectTypeKey": p["project_type_key"],
            "lead": self._user_obj(p["lead"]),
            "description": p["description"],
        }

    def _next_issue_key(self, project_key):
        nums = []
        for i in self.issues:
            if i["project_key"] == project_key and "-" in i["key"]:
                try:
                    nums.append(int(i["key"].split("-")[1]))
                except ValueError:
                    pass
        return f"{project_key}-{max(nums, default=100) + 1}"

    # --- API methods -------------------------------------------------------
    def list_projects(self) -> Dict[str, Any]:
        return {"status": "ok", "output": [self._serialize_project(p) for p in self.projects]}

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        for i in self.issues:
            if i["key"] == issue_key:
                return {"status": "ok", "output": self._serialize_issue(i)}
        return {"status": "failed", "output": f"Issue {issue_key} does not exist"}

    def create_issue(self, project_key: str, summary: str, issue_type: str = "Task",
                     description: str = "", priority: str = "Medium",
                     assignee: str | None = None, reporter: str = "user-amelia") -> Dict[str, Any]:
        proj = next((p for p in self.projects if p["key"] == project_key), None)
        if not proj:
            return {"status": "failed", "output": f"Project {project_key} not found"}
        if assignee and not any(u["account_id"] == assignee for u in self.users):
            return {"status": "failed", "output": "Invalid assignee"}
        key = self._next_issue_key(project_key)
        new_id = str(max(int(i["id"]) for i in self.issues) + 1)
        issue = {
            "id": new_id,
            "key": key,
            "project_key": project_key,
            "issue_type": issue_type,
            "summary": summary,
            "description": description or "",
            "status": "To Do",
            "priority": priority,
            "assignee": assignee,
            "reporter": reporter,
            "sprint_id": None,
            "story_points": None,
            "created": self._now(),
            "updated": self._now(),
        }
        self.issues.append(issue)
        return {"status": "ok", "output": {"id": new_id, "key": key, "self": f"/rest/api/3/issue/{new_id}"}}

    def update_issue(self, issue_key: str, summary: str | None = None, description: str | None = None,
                     priority: str | None = None, assignee: str | None = None) -> Dict[str, Any]:
        for idx, issue in enumerate(self.issues):
            if issue["key"] == issue_key:
                if summary is not None:
                    self.issues[idx]["summary"] = summary
                if description is not None:
                    self.issues[idx]["description"] = description
                if priority is not None:
                    self.issues[idx]["priority"] = priority
                if assignee is not None:
                    self.issues[idx]["assignee"] = assignee or None
                self.issues[idx]["updated"] = self._now()
                return {"status": "ok", "output": {"key": issue_key, "updated": True}}
        return {"status": "failed", "output": f"Issue {issue_key} does not exist"}

    def get_transitions(self, issue_key: str) -> Dict[str, Any]:
        issue = next((i for i in self.issues if i["key"] == issue_key), None)
        if not issue:
            return {"status": "failed", "output": f"Issue {issue_key} does not exist"}
        transitions = []
        for tid, target in _WORKFLOW.get(issue["status"], {}).items():
            transitions.append({"id": tid, "name": f"To {target}", "to": {"name": target}})
        return {"status": "ok", "output": {"transitions": transitions}}

    def transition_issue(self, issue_key: str, transition_id: str) -> Dict[str, Any]:
        for idx, issue in enumerate(self.issues):
            if issue["key"] == issue_key:
                allowed = _WORKFLOW.get(issue["status"], {})
                if transition_id not in allowed:
                    return {"status": "failed", "output": f"Transition {transition_id} not valid from {issue['status']}"}
                self.issues[idx]["status"] = allowed[transition_id]
                self.issues[idx]["updated"] = self._now()
                return {"status": "ok", "output": {"key": issue_key, "status": allowed[transition_id], "transitioned": True}}
        return {"status": "failed", "output": f"Issue {issue_key} does not exist"}

    def search(self, jql: str | None = None, max_results: int = 50) -> Dict[str, Any]:
        results = list(self.issues)
        project = None
        status = None
        if jql:
            for clause in jql.split("AND"):
                clause = clause.strip()
                if "=" not in clause:
                    continue
                field, _, value = clause.partition("=")
                field = field.strip().lower()
                value = value.strip().strip('"').strip("'")
                if field == "project":
                    project = value
                elif field == "status":
                    status = value
        if project:
            results = [i for i in results if i["project_key"] == project]
        if status:
            results = [i for i in results if i["status"].lower() == status.lower()]
        results = results[:max_results]
        return {"status": "ok", "output": {
            "expand": "schema,names",
            "startAt": 0,
            "maxResults": max_results,
            "total": len(results),
            "issues": [self._serialize_issue(i) for i in results],
        }}

    def list_boards(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "maxResults": 50,
            "startAt": 0,
            "total": len(self.boards),
            "values": [
                {"id": b["id"], "name": b["name"], "type": b["type"],
                 "location": {"projectKey": b["project_key"]}}
                for b in self.boards
            ],
        }}

    def list_sprints(self, board_id: int, state: str | None = None) -> Dict[str, Any]:
        if not any(b["id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        sprints = [s for s in self.sprints if s["board_id"] == board_id]
        if state:
            sprints = [s for s in sprints if s["state"] == state]
        return {"status": "ok", "output": {
            "maxResults": 50,
            "startAt": 0,
            "total": len(sprints),
            "values": [
                {"id": s["id"], "name": s["name"], "state": s["state"],
                 "originBoardId": s["board_id"], "startDate": s["start_date"],
                 "endDate": s["end_date"], "goal": s["goal"]}
                for s in sprints
            ],
        }}


if __name__ == "__main__":
    s = JiraSession(seed=12)
    print(s.list_projects())
    print(s.list_boards())
