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


ISSUE_STATUSES = ("open", "in_progress", "in_review", "resolved", "closed")
PRIORITIES = ("low", "medium", "high", "critical")
ISSUE_TYPES = ("bug", "feature", "task")
SPRINT_STATUSES = ("upcoming", "active", "completed")

SEED_SPRINTS = [
    ("Sprint 24",  -7, 7,  "Ship LightIssues MVP and stabilize LightCRM.", "active"),
    ("Sprint 25",   8, 21, "Roll out sprint burndown and cross-app search.", "upcoming"),
]

SEED_ISSUES = [
    ("Login crash on stale token",   "Login fails intermittently when token is stale.", "in_progress", "high",     "bug",     "alice", "self",   0, ["auth"]),
    ("Add sprint burndown chart",    "Chart tracking remaining work per day.",          "open",        "medium",   "feature", "bob",   "self",   1, ["reporting"]),
    ("Refactor issue store",         "Extract issue store into its own module.",        "in_review",   "low",      "task",    "self",  "alice",  0, ["refactor"]),
    ("Fix pagination off-by-one",    "Last page returns one duplicate row.",            "resolved",    "medium",   "bug",     "self",  "bob",    0, ["pagination"]),
    ("Cross-app search API",         "Search across all Light apps.",                   "open",        "critical", "feature", None,    "self",   1, ["search"]),
    ("Backlog: onboarding polish",   "Improve first-run experience.",                   "open",        "low",      "task",    None,    "self",   None, ["polish"]),
]

SEED_COMMENTS = [
    (0, "self",  "Reproduced locally, looks like clock skew."),
    (0, "alice", "Adding a retry with fresh token."),
    (3, "bob",   "Verified fix on staging."),
]


@dataclass
class Sprint:
    sid: str
    name: str
    start_date: str
    end_date: str
    goal: str = ""
    status: str = "upcoming"


@dataclass
class Issue:
    iid: str
    title: str
    description: str
    status: str
    priority: str
    issue_type: str
    assignee: Optional[str]
    reporter: str
    sprint_id: Optional[str]
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str = ""


@dataclass
class Comment:
    cid: str
    issue_id: str
    author: str
    text: str
    created_at: str = ""


class IssuesSession:
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
            self.sprints: Dict[str, Sprint] = {}
            self.issues: Dict[str, Issue] = {}
            self.comments: Dict[str, Comment] = {}
            self._today = datetime(2026, 1, 5)
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightIssues')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed(self) -> None:
        sprint_ids: List[str] = []
        for name, start_off, end_off, goal, status in SEED_SPRINTS:
            s = Sprint(
                sid=self.uuid(),
                name=name,
                start_date=(self._today + timedelta(days=start_off)).date().isoformat(),
                end_date=(self._today + timedelta(days=end_off)).date().isoformat(),
                goal=goal,
                status=status,
            )
            self.sprints[s.sid] = s
            sprint_ids.append(s.sid)

        issue_ids: List[str] = []
        for title, desc, status, prio, itype, assignee, reporter, sprint_idx, tags in SEED_ISSUES:
            sprint_id = sprint_ids[sprint_idx] if sprint_idx is not None else None
            resolved_at = self._now() if status in {"resolved", "closed"} else ""
            i = Issue(
                iid=self.uuid(),
                title=title,
                description=desc,
                status=status,
                priority=prio,
                issue_type=itype,
                assignee=assignee,
                reporter=reporter,
                sprint_id=sprint_id,
                tags=list(tags),
                created_at=self._now(),
                updated_at=self._now(),
                resolved_at=resolved_at,
            )
            self.issues[i.iid] = i
            issue_ids.append(i.iid)

        for issue_idx, author, text in SEED_COMMENTS:
            c = Comment(
                cid=self.uuid(),
                issue_id=issue_ids[issue_idx],
                author=author,
                text=text,
                created_at=self._now(),
            )
            self.comments[c.cid] = c

    def get_session_dict(self) -> Dict:
        return {
            "sprints": {sid: asdict(s) for sid, s in self.sprints.items()},
            "issues": {iid: asdict(i) for iid, i in self.issues.items()},
            "comments": {cid: asdict(c) for cid, c in self.comments.items()},
        }

    def _issue_summary(self, i: Issue) -> Dict:
        return {
            "iid": i.iid,
            "title": i.title,
            "status": i.status,
            "priority": i.priority,
            "issue_type": i.issue_type,
            "assignee": i.assignee,
            "reporter": i.reporter,
            "sprint_id": i.sprint_id,
            "tags": list(i.tags),
            "updated_at": i.updated_at,
        }

    def _sprint_summary(self, s: Sprint) -> Dict:
        return {
            "sid": s.sid,
            "name": s.name,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "goal": s.goal,
            "status": s.status,
        }

    def _comment_summary(self, c: Comment) -> Dict:
        return {
            "cid": c.cid,
            "issue_id": c.issue_id,
            "author": c.author,
            "text": c.text,
            "created_at": c.created_at,
        }

    def list_issues(self, status: Optional[str] = None,
                    priority: Optional[str] = None,
                    assignee: Optional[str] = None,
                    sprint_id: Optional[str] = None,
                    tag: Optional[str] = None) -> Dict:
        items = list(self.issues.values())
        if status:
            if status not in ISSUE_STATUSES:
                return {"status": "failed", "output": f"status must be one of {ISSUE_STATUSES}"}
            items = [i for i in items if i.status == status]
        if priority:
            if priority not in PRIORITIES:
                return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
            items = [i for i in items if i.priority == priority]
        if assignee:
            items = [i for i in items if i.assignee == assignee]
        if sprint_id:
            items = [i for i in items if i.sprint_id == sprint_id]
        if tag:
            items = [i for i in items if tag in i.tags]
        items.sort(key=lambda i: (i.status != "open", i.priority, i.updated_at))
        return {"status": "ok", "output": [self._issue_summary(i) for i in items]}

    def get_issue(self, iid: str) -> Dict:
        i = self.issues.get(iid)
        if not i:
            return {"status": "failed", "output": f"issue {iid} not found"}
        return {"status": "ok", "output": asdict(i)}

    def create_issue(self, title: str,
                     description: str = "",
                     priority: str = "medium",
                     issue_type: str = "task",
                     assignee: Optional[str] = None,
                     reporter: str = "self",
                     sprint_id: Optional[str] = None,
                     tags: Optional[List[str]] = None) -> Dict:
        if priority not in PRIORITIES:
            return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
        if issue_type not in ISSUE_TYPES:
            return {"status": "failed", "output": f"issue_type must be one of {ISSUE_TYPES}"}
        if sprint_id is not None and sprint_id not in self.sprints:
            return {"status": "failed", "output": f"sprint {sprint_id} not found"}
        i = Issue(
            iid=self.uuid(),
            title=title,
            description=description,
            status="open",
            priority=priority,
            issue_type=issue_type,
            assignee=assignee,
            reporter=reporter,
            sprint_id=sprint_id,
            tags=list(tags) if tags else [],
            created_at=self._now(),
            updated_at=self._now(),
            resolved_at="",
        )
        self.issues[i.iid] = i
        return {"status": "ok", "output": self._issue_summary(i)}

    def update_issue(self, iid: str,
                     title: Optional[str] = None,
                     description: Optional[str] = None,
                     status: Optional[str] = None,
                     priority: Optional[str] = None,
                     issue_type: Optional[str] = None,
                     assignee: Optional[str] = None,
                     sprint_id: Optional[str] = None,
                     tags: Optional[List[str]] = None) -> Dict:
        i = self.issues.get(iid)
        if not i:
            return {"status": "failed", "output": f"issue {iid} not found"}
        if status is not None and status not in ISSUE_STATUSES:
            return {"status": "failed", "output": f"status must be one of {ISSUE_STATUSES}"}
        if priority is not None and priority not in PRIORITIES:
            return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
        if issue_type is not None and issue_type not in ISSUE_TYPES:
            return {"status": "failed", "output": f"issue_type must be one of {ISSUE_TYPES}"}
        if sprint_id is not None and sprint_id != "" and sprint_id not in self.sprints:
            return {"status": "failed", "output": f"sprint {sprint_id} not found"}
        for k, v in {
            "title": title, "description": description, "status": status,
            "priority": priority, "issue_type": issue_type,
            "assignee": assignee, "sprint_id": sprint_id,
        }.items():
            if v is not None:
                setattr(i, k, v)
        if tags is not None:
            i.tags = list(tags)
        if status in {"resolved", "closed"}:
            i.resolved_at = self._now()
        i.updated_at = self._now()
        return {"status": "ok", "output": self._issue_summary(i)}

    def delete_issue(self, iid: str) -> Dict:
        i = self.issues.pop(iid, None)
        if not i:
            return {"status": "failed", "output": f"issue {iid} not found"}
        removed = [cid for cid, c in self.comments.items() if c.issue_id == iid]
        for cid in removed:
            del self.comments[cid]
        return {"status": "ok", "output": {"iid": iid, "deleted": True, "removed_comments": len(removed)}}

    def assign_issue(self, iid: str, assignee: str) -> Dict:
        return self.update_issue(iid, assignee=assignee)

    def change_status(self, iid: str, status: str) -> Dict:
        if status not in ISSUE_STATUSES:
            return {"status": "failed", "output": f"status must be one of {ISSUE_STATUSES}"}
        return self.update_issue(iid, status=status)

    def change_priority(self, iid: str, priority: str) -> Dict:
        if priority not in PRIORITIES:
            return {"status": "failed", "output": f"priority must be one of {PRIORITIES}"}
        return self.update_issue(iid, priority=priority)

    def add_to_sprint(self, iid: str, sid: str) -> Dict:
        if sid not in self.sprints:
            return {"status": "failed", "output": f"sprint {sid} not found"}
        return self.update_issue(iid, sprint_id=sid)

    def remove_from_sprint(self, iid: str) -> Dict:
        i = self.issues.get(iid)
        if not i:
            return {"status": "failed", "output": f"issue {iid} not found"}
        i.sprint_id = None
        i.updated_at = self._now()
        return {"status": "ok", "output": self._issue_summary(i)}

    def list_sprints(self) -> Dict:
        items = sorted(self.sprints.values(), key=lambda s: s.start_date)
        return {"status": "ok", "output": [self._sprint_summary(s) for s in items]}

    def get_sprint(self, sid: str) -> Dict:
        s = self.sprints.get(sid)
        if not s:
            return {"status": "failed", "output": f"sprint {sid} not found"}
        return {"status": "ok", "output": asdict(s)}

    def create_sprint(self, name: str, start_date: str, end_date: str,
                      goal: str = "") -> Dict:
        s = Sprint(
            sid=self.uuid(),
            name=name,
            start_date=start_date,
            end_date=end_date,
            goal=goal,
            status="upcoming",
        )
        self.sprints[s.sid] = s
        return {"status": "ok", "output": self._sprint_summary(s)}

    def start_sprint(self, sid: str) -> Dict:
        s = self.sprints.get(sid)
        if not s:
            return {"status": "failed", "output": f"sprint {sid} not found"}
        s.status = "active"
        return {"status": "ok", "output": self._sprint_summary(s)}

    def close_sprint(self, sid: str) -> Dict:
        s = self.sprints.get(sid)
        if not s:
            return {"status": "failed", "output": f"sprint {sid} not found"}
        s.status = "completed"
        return {"status": "ok", "output": self._sprint_summary(s)}

    def list_by_sprint(self, sid: str) -> Dict:
        if sid not in self.sprints:
            return {"status": "failed", "output": f"sprint {sid} not found"}
        items = [i for i in self.issues.values() if i.sprint_id == sid]
        items.sort(key=lambda i: (i.status != "open", i.priority, i.updated_at))
        return {"status": "ok", "output": [self._issue_summary(i) for i in items]}

    def add_comment(self, iid: str, author: str, text: str) -> Dict:
        if iid not in self.issues:
            return {"status": "failed", "output": f"issue {iid} not found"}
        c = Comment(
            cid=self.uuid(),
            issue_id=iid,
            author=author,
            text=text,
            created_at=self._now(),
        )
        self.comments[c.cid] = c
        return {"status": "ok", "output": self._comment_summary(c)}

    def list_comments(self, iid: str) -> Dict:
        if iid not in self.issues:
            return {"status": "failed", "output": f"issue {iid} not found"}
        items = [c for c in self.comments.values() if c.issue_id == iid]
        items.sort(key=lambda c: c.created_at)
        return {"status": "ok", "output": [self._comment_summary(c) for c in items]}

    def search_issues(self, query: str) -> Dict:
        q = query.lower()
        items = [i for i in self.issues.values()
                 if q in i.title.lower() or q in i.description.lower()
                 or any(q in tag.lower() for tag in i.tags)]
        items.sort(key=lambda i: i.updated_at, reverse=True)
        return {"status": "ok", "output": [self._issue_summary(i) for i in items]}

    def list_backlog(self) -> Dict:
        items = [i for i in self.issues.values()
                 if i.sprint_id is None and i.status not in {"resolved", "closed"}]
        items.sort(key=lambda i: (i.priority, i.updated_at))
        return {"status": "ok", "output": [self._issue_summary(i) for i in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in ISSUE_STATUSES}
        by_priority: Dict[str, int] = {p: 0 for p in PRIORITIES}
        by_type: Dict[str, int] = {t: 0 for t in ISSUE_TYPES}
        backlog = 0
        for i in self.issues.values():
            by_status[i.status] = by_status.get(i.status, 0) + 1
            by_priority[i.priority] = by_priority.get(i.priority, 0) + 1
            by_type[i.issue_type] = by_type.get(i.issue_type, 0) + 1
            if i.sprint_id is None and i.status not in {"resolved", "closed"}:
                backlog += 1
        return {
            "status": "ok",
            "output": {
                "issues": len(self.issues),
                "sprints": len(self.sprints),
                "comments": len(self.comments),
                "backlog": backlog,
                "by_status": by_status,
                "by_priority": by_priority,
                "by_type": by_type,
            },
        }
