from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


STATUSES = ("todo", "in_progress", "done", "cancelled")
PRIORITIES = ("low", "medium", "high", "critical")

DEFAULT_PROJECTS = [
    {"pid": "proj_inbox",    "name": "Inbox",    "color": "#607D8B", "description": "Uncategorized tasks"},
    {"pid": "proj_personal", "name": "Personal", "color": "#4285F4", "description": "Personal to-dos"},
    {"pid": "proj_work",     "name": "Work",     "color": "#DB4437", "description": "Work items"},
]

SEED_TASKS = [
    ("Write weekly status report", "proj_work",     "todo",        "high",     1, ["report", "weekly"], "self"),
    ("Reply to design feedback",   "proj_work",     "in_progress", "medium",   0, ["review"],           "self"),
    ("Refactor auth module",       "proj_work",     "todo",        "high",     4, ["refactor", "auth"], "self"),
    ("Book dentist appointment",   "proj_personal", "todo",        "low",      7, ["health"],           "self"),
    ("Renew car insurance",        "proj_personal", "todo",        "high",     3, ["finance"],          "self"),
    ("Grocery shopping",           "proj_inbox",    "done",        "low",     -2, ["errand"],           "self"),
    ("Read paper on MCP tools",    "proj_inbox",    "todo",        "medium",   2, ["reading"],          "self"),
    ("Plan Q1 roadmap",            "proj_work",     "todo",        "critical", 6, ["planning"],         "self"),
]


@dataclass
class Task:
    tid: str
    title: str
    description: str
    status: str
    priority: str
    due_date: str
    project_id: str
    assignee: str
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Project:
    pid: str
    name: str
    color: str
    description: str = ""


class TasksSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"],
            ) if os_cfg else DummyOSConnector()
            self.projects: Dict[str, Project] = {
                p["pid"]: Project(**p) for p in DEFAULT_PROJECTS
            }
            self.tasks: Dict[str, Task] = {}
            self._today = datetime(2026, 1, 5)
            self._seed_tasks()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTasks')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_tasks(self) -> None:
        for title, pid, status, prio, day_offset, tags, assignee in SEED_TASKS:
            due = (self._today + timedelta(days=day_offset)).date().isoformat()
            t = Task(
                tid=self.uuid(),
                title=title,
                description="",
                status=status,
                priority=prio,
                due_date=due,
                project_id=pid,
                assignee=assignee,
                tags=list(tags),
                created_at=self._now(),
                updated_at=self._now(),
            )
            self.tasks[t.tid] = t

    def get_session_dict(self) -> Dict:
        return {
            "projects": {pid: asdict(p) for pid, p in self.projects.items()},
            "tasks": {tid: asdict(t) for tid, t in self.tasks.items()},
        }

    def _task_summary(self, t: Task) -> Dict:
        return {
            "tid": t.tid,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date,
            "project_id": t.project_id,
            "assignee": t.assignee,
            "tags": list(t.tags),
        }

    def list_projects(self) -> Dict:
        return {"status": "ok", "output": [asdict(p) for p in self.projects.values()]}

    def create_project(self, name: str, color: str = "#888888", description: str = "") -> Dict:
        pid = "proj_" + self.uuid()[:8]
        p = Project(pid=pid, name=name, color=color, description=description)
        self.projects[pid] = p
        return {"status": "ok", "output": asdict(p)}

    def delete_project(self, pid: str, reassign_to: str = "proj_inbox") -> Dict:
        if pid not in self.projects:
            return {"status": "failed", "output": f"project {pid} not found"}
        if pid == reassign_to:
            return {"status": "failed", "output": "reassign_to must differ from pid"}
        if reassign_to not in self.projects:
            return {"status": "failed", "output": f"reassign_to project {reassign_to} not found"}
        moved = 0
        for t in self.tasks.values():
            if t.project_id == pid:
                t.project_id = reassign_to
                t.updated_at = self._now()
                moved += 1
        del self.projects[pid]
        return {"status": "ok", "output": {"pid": pid, "moved": moved, "reassigned_to": reassign_to}}

    def list_tasks(self, project_id: Optional[str] = None,
                   status: Optional[str] = None,
                   priority: Optional[str] = None,
                   tag: Optional[str] = None,
                   assignee: Optional[str] = None) -> Dict:
        items = list(self.tasks.values())
        if project_id:
            items = [t for t in items if t.project_id == project_id]
        if status:
            items = [t for t in items if t.status == status]
        if priority:
            items = [t for t in items if t.priority == priority]
        if tag:
            items = [t for t in items if tag in t.tags]
        if assignee:
            items = [t for t in items if t.assignee == assignee]
        items.sort(key=lambda t: (t.status != "todo", t.due_date))
        return {"status": "ok", "output": [self._task_summary(t) for t in items]}

    def get_task(self, tid: str) -> Dict:
        t = self.tasks.get(tid)
        if not t:
            return {"status": "failed", "output": f"task {tid} not found"}
        return {"status": "ok", "output": asdict(t)}

    def create_task(self, title: str,
                    project_id: str = "proj_inbox",
                    priority: str = "medium",
                    due_date: str = "",
                    description: str = "",
                    tags: Optional[List[str]] = None,
                    assignee: str = "self") -> Dict:
        if project_id not in self.projects:
            return {"status": "failed", "output": f"project {project_id} not found"}
        if priority not in PRIORITIES:
            return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
        t = Task(
            tid=self.uuid(),
            title=title,
            description=description,
            status="todo",
            priority=priority,
            due_date=due_date,
            project_id=project_id,
            assignee=assignee,
            tags=list(tags) if tags else [],
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.tasks[t.tid] = t
        return {"status": "ok", "output": self._task_summary(t)}

    def update_task(self, tid: str,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    status: Optional[str] = None,
                    priority: Optional[str] = None,
                    due_date: Optional[str] = None,
                    project_id: Optional[str] = None,
                    assignee: Optional[str] = None,
                    tags: Optional[List[str]] = None) -> Dict:
        t = self.tasks.get(tid)
        if not t:
            return {"status": "failed", "output": f"task {tid} not found"}
        if status is not None and status not in STATUSES:
            return {"status": "failed", "output": f"status must be one of {STATUSES}"}
        if priority is not None and priority not in PRIORITIES:
            return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
        if project_id is not None and project_id not in self.projects:
            return {"status": "failed", "output": f"project {project_id} not found"}
        for k, v in {
            "title": title, "description": description, "status": status,
            "priority": priority, "due_date": due_date, "project_id": project_id,
            "assignee": assignee,
        }.items():
            if v is not None:
                setattr(t, k, v)
        if tags is not None:
            t.tags = list(tags)
        t.updated_at = self._now()
        return {"status": "ok", "output": self._task_summary(t)}

    def delete_task(self, tid: str) -> Dict:
        t = self.tasks.pop(tid, None)
        if not t:
            return {"status": "failed", "output": f"task {tid} not found"}
        return {"status": "ok", "output": {"tid": tid, "deleted": True}}

    def complete_task(self, tid: str) -> Dict:
        return self.update_task(tid, status="done")

    def reopen_task(self, tid: str) -> Dict:
        return self.update_task(tid, status="todo")

    def move_task(self, tid: str, project_id: str) -> Dict:
        return self.update_task(tid, project_id=project_id)

    def add_tag(self, tid: str, tag: str) -> Dict:
        t = self.tasks.get(tid)
        if not t:
            return {"status": "failed", "output": f"task {tid} not found"}
        if tag not in t.tags:
            t.tags.append(tag)
            t.updated_at = self._now()
        return {"status": "ok", "output": self._task_summary(t)}

    def remove_tag(self, tid: str, tag: str) -> Dict:
        t = self.tasks.get(tid)
        if not t:
            return {"status": "failed", "output": f"task {tid} not found"}
        if tag in t.tags:
            t.tags.remove(tag)
            t.updated_at = self._now()
        return {"status": "ok", "output": self._task_summary(t)}

    def search_tasks(self, query: str) -> Dict:
        q = query.lower()
        items = [t for t in self.tasks.values()
                 if q in t.title.lower() or q in t.description.lower()
                 or any(q in tag.lower() for tag in t.tags)]
        items.sort(key=lambda t: t.due_date)
        return {"status": "ok", "output": [self._task_summary(t) for t in items]}

    def list_upcoming(self, days: int = 7, today: Optional[str] = None) -> Dict:
        anchor = datetime.fromisoformat(today).date() if today else self._today.date()
        horizon = anchor + timedelta(days=days)
        items = []
        for t in self.tasks.values():
            if t.status in {"done", "cancelled"} or not t.due_date:
                continue
            try:
                d = datetime.fromisoformat(t.due_date).date()
            except ValueError:
                continue
            if anchor <= d <= horizon:
                items.append(t)
        items.sort(key=lambda t: t.due_date)
        return {"status": "ok", "output": [self._task_summary(t) for t in items]}

    def list_overdue(self, today: Optional[str] = None) -> Dict:
        anchor = datetime.fromisoformat(today).date() if today else self._today.date()
        items = []
        for t in self.tasks.values():
            if t.status in {"done", "cancelled"} or not t.due_date:
                continue
            try:
                d = datetime.fromisoformat(t.due_date).date()
            except ValueError:
                continue
            if d < anchor:
                items.append(t)
        items.sort(key=lambda t: t.due_date)
        return {"status": "ok", "output": [self._task_summary(t) for t in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in STATUSES}
        by_priority: Dict[str, int] = {p: 0 for p in PRIORITIES}
        by_project: Dict[str, int] = {pid: 0 for pid in self.projects}
        for t in self.tasks.values():
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            by_project[t.project_id] = by_project.get(t.project_id, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total": len(self.tasks),
                "by_status": by_status,
                "by_priority": by_priority,
                "by_project": by_project,
            },
        }
