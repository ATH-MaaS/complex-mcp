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


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class GitlabSession:
    """Deterministic sandbox for the GitLab mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "gitlab.yaml") as f:
                info = yaml.safe_load(f)

            self.current_user: Dict[str, Any] = info.get("current_user", {})

            self.projects: List[Dict[str, Any]] = [
                {
                    **p,
                    "id": _to_int(p.get("id")),
                    "star_count": _to_int(p.get("star_count")),
                    "forks_count": _to_int(p.get("forks_count")),
                    "open_issues_count": _to_int(p.get("open_issues_count")),
                }
                for p in info.get("projects", [])
            ]
            self.issues: List[Dict[str, Any]] = [
                {
                    **i,
                    "id": _to_int(i.get("id")),
                    "iid": _to_int(i.get("iid")),
                    "project_id": _to_int(i.get("project_id")),
                    "labels": [l for l in str(i.get("labels", "") or "").split(";") if l],
                    "closed_at": (i.get("closed_at") or None),
                }
                for i in info.get("issues", [])
            ]
            self.merge_requests: List[Dict[str, Any]] = [
                {
                    **m,
                    "id": _to_int(m.get("id")),
                    "iid": _to_int(m.get("iid")),
                    "project_id": _to_int(m.get("project_id")),
                    "draft": _to_bool(m.get("draft", False)),
                    "merged_at": (m.get("merged_at") or None),
                }
                for m in info.get("merge_requests", [])
            ]
            self.pipelines: List[Dict[str, Any]] = [
                {
                    **p,
                    "id": _to_int(p.get("id")),
                    "project_id": _to_int(p.get("project_id")),
                    "duration": _to_int(p.get("duration")),
                }
                for p in info.get("pipelines", [])
            ]
            self.users: List[Dict[str, Any]] = [
                {
                    **u,
                    "id": _to_int(u.get("id")),
                    "is_admin": _to_bool(u.get("is_admin", False)),
                }
                for u in info.get("users", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGitlab')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"issues": self.issues, "merge_requests": self.merge_requests}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _find_project(self, project_id):
        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            return None
        return next((p for p in self.projects if p["id"] == pid), None)

    def _new_numeric_id(self, store):
        return max((row["id"] for row in store), default=0) + 1

    # --- Users -------------------------------------------------------------
    def get_current_user(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.current_user}

    def list_users(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.users)}

    # --- Projects ----------------------------------------------------------
    def list_projects(self, visibility: str | None = None) -> Dict[str, Any]:
        results = list(self.projects)
        if visibility:
            results = [p for p in results if p["visibility"] == visibility]
        return {"status": "ok", "output": results}

    def get_project(self, project_id: str) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        return {"status": "ok", "output": project}

    # --- Issues ------------------------------------------------------------
    def list_issues(self, project_id: str, state: str | None = None, labels: str | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        results = [i for i in self.issues if i["project_id"] == project["id"]]
        if state and state != "all":
            results = [i for i in results if i["state"] == state]
        if labels:
            wanted = {l.strip().lower() for l in labels.split(",")}
            results = [i for i in results if {l.lower() for l in i["labels"]} & wanted]
        results.sort(key=lambda i: i["updated_at"], reverse=True)
        return {"status": "ok", "output": results}

    def get_issue(self, project_id: str, issue_iid: int) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        for i in self.issues:
            if i["project_id"] == project["id"] and i["iid"] == int(issue_iid):
                return {"status": "ok", "output": i}
        return {"status": "failed", "output": f"Issue {issue_iid} not found in project {project_id}"}

    def create_issue(self, project_id: str, title: str, description: str = "",
                     assignee: str | None = None, labels: List[str] | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        next_iid = max((i["iid"] for i in self.issues if i["project_id"] == project["id"]), default=0) + 1
        issue = {
            "id": self._new_numeric_id(self.issues),
            "iid": next_iid,
            "project_id": project["id"],
            "title": title,
            "description": description or "",
            "state": "opened",
            "author": self.current_user["username"],
            "assignee": assignee or "",
            "labels": labels or [],
            "created_at": self._now(),
            "updated_at": self._now(),
            "closed_at": None,
        }
        self.issues.append(issue)
        project["open_issues_count"] += 1
        return {"status": "ok", "output": issue}

    def update_issue(self, project_id: str, issue_iid: int, title: str | None = None,
                     description: str | None = None, state_event: str | None = None,
                     assignee: str | None = None, labels: List[str] | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        for idx, i in enumerate(self.issues):
            if i["project_id"] == project["id"] and i["iid"] == int(issue_iid):
                if title is not None:
                    self.issues[idx]["title"] = title
                if description is not None:
                    self.issues[idx]["description"] = description
                if assignee is not None:
                    self.issues[idx]["assignee"] = assignee
                if labels is not None:
                    self.issues[idx]["labels"] = labels
                if state_event == "close" and i["state"] != "closed":
                    self.issues[idx]["state"] = "closed"
                    self.issues[idx]["closed_at"] = self._now()
                    project["open_issues_count"] = max(0, project["open_issues_count"] - 1)
                elif state_event == "reopen" and i["state"] != "opened":
                    self.issues[idx]["state"] = "opened"
                    self.issues[idx]["closed_at"] = None
                    project["open_issues_count"] += 1
                self.issues[idx]["updated_at"] = self._now()
                return {"status": "ok", "output": self.issues[idx]}
        return {"status": "failed", "output": f"Issue {issue_iid} not found in project {project_id}"}

    # --- Merge requests ----------------------------------------------------
    def list_merge_requests(self, project_id: str, state: str | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        results = [m for m in self.merge_requests if m["project_id"] == project["id"]]
        if state and state != "all":
            results = [m for m in results if m["state"] == state]
        results.sort(key=lambda m: m["updated_at"], reverse=True)
        return {"status": "ok", "output": results}

    def create_merge_request(self, project_id: str, title: str, source_branch: str,
                             target_branch: str = "main", description: str = "",
                             assignee: str | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        next_iid = max((m["iid"] for m in self.merge_requests if m["project_id"] == project["id"]), default=0) + 1
        mr = {
            "id": self._new_numeric_id(self.merge_requests),
            "iid": next_iid,
            "project_id": project["id"],
            "title": title,
            "description": description or "",
            "state": "opened",
            "source_branch": source_branch,
            "target_branch": target_branch,
            "author": self.current_user["username"],
            "assignee": assignee or "",
            "merge_status": "can_be_merged",
            "draft": False,
            "created_at": self._now(),
            "updated_at": self._now(),
            "merged_at": None,
        }
        self.merge_requests.append(mr)
        return {"status": "ok", "output": mr}

    def merge_merge_request(self, project_id: str, mr_iid: int) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        for idx, m in enumerate(self.merge_requests):
            if m["project_id"] == project["id"] and m["iid"] == int(mr_iid):
                if m["draft"]:
                    return {"status": "failed", "output": "Draft merge request cannot be merged"}
                if m["merge_status"] != "can_be_merged":
                    return {"status": "failed", "output": "Merge request cannot be merged"}
                if m["state"] == "merged":
                    return {"status": "failed", "output": "Merge request already merged"}
                self.merge_requests[idx]["state"] = "merged"
                self.merge_requests[idx]["merged_at"] = self._now()
                self.merge_requests[idx]["updated_at"] = self._now()
                return {"status": "ok", "output": self.merge_requests[idx]}
        return {"status": "failed", "output": f"Merge request {mr_iid} not found in project {project_id}"}

    # --- Pipelines ---------------------------------------------------------
    def list_pipelines(self, project_id: str, status: str | None = None) -> Dict[str, Any]:
        project = self._find_project(project_id)
        if not project:
            return {"status": "failed", "output": f"Project {project_id} not found"}
        results = [p for p in self.pipelines if p["project_id"] == project["id"]]
        if status:
            results = [p for p in results if p["status"] == status]
        results.sort(key=lambda p: p["created_at"], reverse=True)
        return {"status": "ok", "output": results}


if __name__ == "__main__":
    s = GitlabSession(seed=12)
    print(s.get_current_user())
    print(s.list_projects())
