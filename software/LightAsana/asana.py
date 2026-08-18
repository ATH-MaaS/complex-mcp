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


class AsanaSession:
    """Deterministic sandbox for the Asana mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "asana.yaml") as f:
                info = yaml.safe_load(f)

            self.workspace: Dict[str, Any] = info.get("workspace", {})
            self.users: List[Dict[str, Any]] = list(info.get("users", []))
            self.projects: List[Dict[str, Any]] = [
                {**p, "archived": _to_bool(p.get("archived", False))} for p in info.get("projects", [])
            ]
            self.sections: List[Dict[str, Any]] = list(info.get("sections", []))
            self.tasks: List[Dict[str, Any]] = [
                {
                    **t,
                    "completed": _to_bool(t.get("completed", False)),
                    "assignee_gid": (t.get("assignee_gid") or None),
                    "due_on": (t.get("due_on") or None),
                    "section_gid": (t.get("section_gid") or None),
                }
                for t in info.get("tasks", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAsana')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"tasks": self.tasks}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _user_compact(self, gid):
        if not gid:
            return None
        for u in self.users:
            if u["gid"] == gid:
                return {"gid": u["gid"], "resource_type": "user", "name": u["name"]}
        return {"gid": gid, "resource_type": "user"}

    def _project_compact(self, gid):
        if not gid:
            return None
        for p in self.projects:
            if p["gid"] == gid:
                return {"gid": p["gid"], "resource_type": "project", "name": p["name"]}
        return {"gid": gid, "resource_type": "project"}

    def _section_compact(self, gid):
        if not gid:
            return None
        for s in self.sections:
            if s["gid"] == gid:
                return {"gid": s["gid"], "resource_type": "section", "name": s["name"]}
        return {"gid": gid, "resource_type": "section"}

    def _task_view(self, t):
        return {
            "gid": t["gid"],
            "resource_type": "task",
            "name": t["name"],
            "completed": t["completed"],
            "due_on": t["due_on"],
            "notes": t["notes"],
            "created_at": t["created_at"],
            "modified_at": t["modified_at"],
            "assignee": self._user_compact(t["assignee_gid"]),
            "memberships": [{
                "project": self._project_compact(t.get("project_gid")),
                "section": self._section_compact(t.get("section_gid")),
            }],
        }

    # --- API methods -------------------------------------------------------
    def list_workspaces(self) -> Dict[str, Any]:
        ws = self.workspace
        return {"status": "ok", "output": [{
            "gid": ws["gid"], "resource_type": "workspace", "name": ws["name"],
        }]}

    def list_users(self, workspace_gid: str | None = None) -> Dict[str, Any]:
        rows = self.users
        if workspace_gid:
            rows = [u for u in rows if u["workspace_gid"] == workspace_gid]
        return {"status": "ok", "output": [{
            "gid": u["gid"], "resource_type": "user", "name": u["name"], "email": u["email"],
        } for u in rows]}

    def list_projects(self, workspace_gid: str | None = None, archived: bool | None = None) -> Dict[str, Any]:
        rows = list(self.projects)
        if workspace_gid:
            rows = [p for p in rows if p["workspace_gid"] == workspace_gid]
        if archived is not None:
            rows = [p for p in rows if p["archived"] == archived]
        return {"status": "ok", "output": [{
            "gid": p["gid"], "resource_type": "project", "name": p["name"],
            "owner": self._user_compact(p["owner_gid"]), "color": p["color"],
            "archived": p["archived"], "notes": p["notes"], "created_at": p["created_at"],
        } for p in rows]}

    def get_project(self, project_gid: str) -> Dict[str, Any]:
        for p in self.projects:
            if p["gid"] == project_gid:
                return {"status": "ok", "output": {
                    "gid": p["gid"], "resource_type": "project", "name": p["name"],
                    "owner": self._user_compact(p["owner_gid"]), "color": p["color"],
                    "archived": p["archived"], "notes": p["notes"], "created_at": p["created_at"],
                }}
        return {"status": "failed", "output": f"Project {project_gid} not found"}

    def list_project_sections(self, project_gid: str) -> Dict[str, Any]:
        if not any(p["gid"] == project_gid for p in self.projects):
            return {"status": "failed", "output": f"Project {project_gid} not found"}
        rows = [s for s in self.sections if s["project_gid"] == project_gid]
        return {"status": "ok", "output": [{
            "gid": s["gid"], "resource_type": "section", "name": s["name"],
            "project": self._project_compact(project_gid), "created_at": s["created_at"],
        } for s in rows]}

    def list_project_tasks(self, project_gid: str, completed_since: str | None = None) -> Dict[str, Any]:
        if not any(p["gid"] == project_gid for p in self.projects):
            return {"status": "failed", "output": f"Project {project_gid} not found"}
        rows = [t for t in self.tasks if t.get("project_gid") == project_gid]
        return {"status": "ok", "output": [self._task_view(t) for t in rows]}

    def list_tasks(self, project_gid: str | None = None, assignee_gid: str | None = None,
                   completed: bool | None = None) -> Dict[str, Any]:
        rows = list(self.tasks)
        if project_gid:
            rows = [t for t in rows if t.get("project_gid") == project_gid]
        if assignee_gid:
            rows = [t for t in rows if t["assignee_gid"] == assignee_gid]
        if completed is not None:
            rows = [t for t in rows if t["completed"] == completed]
        return {"status": "ok", "output": [self._task_view(t) for t in rows]}

    def get_task(self, task_gid: str) -> Dict[str, Any]:
        for t in self.tasks:
            if t["gid"] == task_gid:
                return {"status": "ok", "output": self._task_view(t)}
        return {"status": "failed", "output": f"Task {task_gid} not found"}

    def create_task(self, name: str, project_gid: str | None = None, section_gid: str | None = None,
                    assignee_gid: str | None = None, due_on: str | None = None,
                    notes: str = "", completed: bool = False) -> Dict[str, Any]:
        if project_gid and not any(p["gid"] == project_gid for p in self.projects):
            return {"status": "failed", "output": f"Project {project_gid} not found"}
        now = self._now()
        task = {
            "gid": self.uuid(),
            "name": name,
            "project_gid": project_gid or "",
            "section_gid": section_gid,
            "assignee_gid": assignee_gid,
            "completed": bool(completed),
            "due_on": due_on,
            "notes": notes or "",
            "created_at": now,
            "modified_at": now,
        }
        self.tasks.append(task)
        return {"status": "ok", "output": self._task_view(task)}

    def update_task(self, task_gid: str, name: str | None = None, completed: bool | None = None,
                    assignee_gid: str | None = None, due_on: str | None = None,
                    section_gid: str | None = None, notes: str | None = None) -> Dict[str, Any]:
        for t in self.tasks:
            if t["gid"] == task_gid:
                if name is not None:
                    t["name"] = name
                if completed is not None:
                    t["completed"] = bool(completed)
                if assignee_gid is not None:
                    t["assignee_gid"] = assignee_gid or None
                if due_on is not None:
                    t["due_on"] = due_on or None
                if section_gid is not None:
                    t["section_gid"] = section_gid or None
                if notes is not None:
                    t["notes"] = notes
                t["modified_at"] = self._now()
                return {"status": "ok", "output": self._task_view(t)}
        return {"status": "failed", "output": f"Task {task_gid} not found"}


if __name__ == "__main__":
    s = AsanaSession(seed=12)
    print(s.list_workspaces())
    print(s.list_projects())
