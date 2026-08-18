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


def _strict_int(v) -> int:
    return int(v)


class SentrySession:
    """Deterministic sandbox for the Sentry mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    _VALID_STATUSES = {"resolved", "ignored", "unresolved"}

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "sentry.yaml") as f:
                info = yaml.safe_load(f)

            self.organizations: List[Dict[str, Any]] = [
                {**o, "id": _strict_int(o["id"])} for o in info.get("organizations", [])
            ]
            self.projects: List[Dict[str, Any]] = [
                {**p, "id": _strict_int(p["id"])} for p in info.get("projects", [])
            ]
            self.issues: List[Dict[str, Any]] = [
                {
                    **i,
                    "id": _strict_int(i["id"]),
                    "count": _strict_int(i["count"]),
                    "user_count": _strict_int(i["user_count"]),
                }
                for i in info.get("issues", [])
            ]
            self.events: List[Dict[str, Any]] = [
                {
                    **e,
                    "id": _strict_int(e["id"]),
                    "issue_id": _strict_int(e["issue_id"]),
                }
                for e in info.get("events", [])
            ]
            self.releases: List[Dict[str, Any]] = [
                {
                    **r,
                    "new_groups": _strict_int(r["new_groups"]),
                    "date_released": (r.get("date_released") or None),
                }
                for r in info.get("releases", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSentry')
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
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=32))

    def _org_exists(self, org_slug):
        return any(o["slug"] == org_slug for o in self.organizations)

    def _serialize_issue(self, i):
        return {
            "id": str(i["id"]),
            "shortId": i["short_id"],
            "title": i["title"],
            "culprit": i["culprit"],
            "level": i["level"],
            "status": i["status"],
            "count": i["count"],
            "userCount": i["user_count"],
            "project": {"slug": i["project_slug"]},
            "firstSeen": i["first_seen"],
            "lastSeen": i["last_seen"],
        }

    def _serialize_event(self, e):
        return {
            "id": str(e["id"]),
            "eventID": e["event_id"],
            "message": e["message"],
            "platform": e["platform"],
            "environment": e["environment"],
            "release": e["release"],
            "user": {"email": e["user_email"]},
            "dateCreated": e["date_created"],
        }

    def _serialize_release(self, r):
        return {
            "version": r["version"],
            "ref": r["ref"],
            "status": r["status"],
            "newGroups": r["new_groups"],
            "projects": [{"slug": r["project_slug"]}],
            "dateCreated": r["date_created"],
            "dateReleased": r["date_released"],
        }

    # --- API methods -------------------------------------------------------
    def list_org_projects(self, org_slug: str) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        return {"status": "ok", "output": [
            {
                "id": str(p["id"]),
                "slug": p["slug"],
                "name": p["name"],
                "platform": p["platform"],
                "status": p["status"],
                "dateCreated": p["date_created"],
            }
            for p in self.projects if p["org_slug"] == org_slug
        ]}

    def list_project_issues(self, org_slug: str, project_slug: str,
                            status: str | None = None, level: str | None = None) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        if not any(p["org_slug"] == org_slug and p["slug"] == project_slug for p in self.projects):
            return {"status": "failed", "output": f"Project {project_slug} not found"}
        results = [i for i in self.issues
                   if i["org_slug"] == org_slug and i["project_slug"] == project_slug]
        if status:
            results = [i for i in results if i["status"] == status]
        if level:
            results = [i for i in results if i["level"] == level]
        results.sort(key=lambda i: i["last_seen"], reverse=True)
        return {"status": "ok", "output": [self._serialize_issue(i) for i in results]}

    def get_issue(self, org_slug: str, issue_id: str) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        for i in self.issues:
            if i["org_slug"] == org_slug and str(i["id"]) == str(issue_id):
                return {"status": "ok", "output": self._serialize_issue(i)}
        return {"status": "failed", "output": f"Issue {issue_id} not found"}

    def update_issue(self, org_slug: str, issue_id: str, status: str) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        if status not in self._VALID_STATUSES:
            return {"status": "failed", "output": f"Invalid status {status}"}
        for i in self.issues:
            if i["org_slug"] == org_slug and str(i["id"]) == str(issue_id):
                i["status"] = status
                i["last_seen"] = self._now()
                return {"status": "ok", "output": self._serialize_issue(i)}
        return {"status": "failed", "output": f"Issue {issue_id} not found"}

    def list_issue_events(self, org_slug: str, issue_id: str) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        if not any(i["org_slug"] == org_slug and str(i["id"]) == str(issue_id) for i in self.issues):
            return {"status": "failed", "output": f"Issue {issue_id} not found"}
        events = [e for e in self.events if str(e["issue_id"]) == str(issue_id)]
        events.sort(key=lambda e: e["date_created"], reverse=True)
        return {"status": "ok", "output": [self._serialize_event(e) for e in events]}

    def list_releases(self, org_slug: str, project: str | None = None) -> Dict[str, Any]:
        if not self._org_exists(org_slug):
            return {"status": "failed", "output": f"Organization {org_slug} not found"}
        results = [r for r in self.releases if r["org_slug"] == org_slug]
        if project:
            results = [r for r in results if r["project_slug"] == project]
        results.sort(key=lambda r: r["date_created"], reverse=True)
        return {"status": "ok", "output": [self._serialize_release(r) for r in results]}


if __name__ == "__main__":
    s = SentrySession(seed=12)
    print(s.list_org_projects("orbit-labs"))
    print(s.list_project_issues("orbit-labs", "auth-service"))
    print(s.update_issue("orbit-labs", "40001", "resolved"))
