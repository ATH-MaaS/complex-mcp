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
    return int(v)


class GithubSession:
    """Deterministic sandbox for the GitHub REST API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "github.yaml") as f:
                info = yaml.safe_load(f)

            self.repos: List[Dict[str, Any]] = [
                {
                    **r,
                    "id": _to_int(r["id"]),
                    "private": _to_bool(r.get("private", False)),
                    "stars": _to_int(r["stars"]),
                    "forks": _to_int(r["forks"]),
                    "open_issues": _to_int(r["open_issues"]),
                }
                for r in info.get("repos", [])
            ]
            self.issues: List[Dict[str, Any]] = [
                {
                    **i,
                    "id": _to_int(i["id"]),
                    "number": _to_int(i["number"]),
                    "is_pull_request": _to_bool(i.get("is_pull_request", False)),
                    "labels": [l for l in str(i.get("labels", "")).split(";") if l],
                    "closed_at": (i.get("closed_at") or None),
                    "milestone": (i.get("milestone") or None),
                }
                for i in info.get("issues", [])
            ]
            self.pulls: List[Dict[str, Any]] = [
                {
                    **p,
                    "number": _to_int(p["number"]),
                    "merged": _to_bool(p.get("merged", False)),
                    "mergeable": _to_bool(p.get("mergeable", False)),
                    "draft": _to_bool(p.get("draft", False)),
                    "additions": _to_int(p["additions"]),
                    "deletions": _to_int(p["deletions"]),
                    "changed_files": _to_int(p["changed_files"]),
                }
                for p in info.get("pulls", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    **c,
                    "id": _to_int(c["id"]),
                    "issue_number": _to_int(c["issue_number"]),
                }
                for c in info.get("comments", [])
            ]
            self.user: Dict[str, Any] = dict(info.get("user", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGithub')
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
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _serialize_repo(self, r):
        return {
            "id": r["id"],
            "name": r["name"],
            "full_name": r["full_name"],
            "owner": {"login": r["owner"]},
            "private": r["private"],
            "description": r["description"],
            "default_branch": r["default_branch"],
            "language": r["language"],
            "stargazers_count": r["stars"],
            "forks_count": r["forks"],
            "open_issues_count": r["open_issues"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def _serialize_issue(self, i):
        return {
            "id": i["id"],
            "number": i["number"],
            "title": i["title"],
            "body": i["body"],
            "state": i["state"],
            "user": {"login": i["user"]},
            "assignee": {"login": i["assignee"]} if i["assignee"] else None,
            "labels": [{"name": l} for l in i["labels"]],
            "milestone": {"title": i["milestone"]} if i["milestone"] else None,
            "created_at": i["created_at"],
            "updated_at": i["updated_at"],
            "closed_at": i["closed_at"],
            "pull_request": {"url": f"/repos/{i['repo']}/pulls/{i['number']}"} if i["is_pull_request"] else None,
        }

    # --- API methods -------------------------------------------------------
    def get_user(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.user}

    def list_repos(self, owner: str | None = None) -> Dict[str, Any]:
        results = list(self.repos)
        if owner:
            results = [r for r in results if r["owner"] == owner]
        return {"status": "ok", "output": [self._serialize_repo(r) for r in results]}

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        for r in self.repos:
            if r["owner"] == owner and r["name"] == repo:
                return {"status": "ok", "output": self._serialize_repo(r)}
        return {"status": "failed", "output": f"Repo {owner}/{repo} not found"}

    def list_issues(self, owner: str, repo: str, state: str = "open", labels: str | None = None,
                    assignee: str | None = None, per_page: int = 30) -> Dict[str, Any]:
        if not any(r["owner"] == owner and r["name"] == repo for r in self.repos):
            return {"status": "failed", "output": f"Repo {owner}/{repo} not found"}
        results = [i for i in self.issues if i["repo"] == repo]
        if state and state != "all":
            results = [i for i in results if i["state"] == state]
        if labels:
            wanted = {l.strip().lower() for l in labels.split(",")}
            results = [i for i in results if {l.lower() for l in i["labels"]} & wanted]
        if assignee:
            results = [i for i in results if i["assignee"] == assignee]
        results.sort(key=lambda i: i["updated_at"], reverse=True)
        return {"status": "ok", "output": [self._serialize_issue(i) for i in results[:per_page]]}

    def get_issue(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        for i in self.issues:
            if i["repo"] == repo and i["number"] == number:
                return {"status": "ok", "output": self._serialize_issue(i)}
        return {"status": "failed", "output": f"Issue {repo}#{number} not found"}

    def create_issue(self, owner: str, repo: str, title: str, body: str = "",
                     assignee: str | None = None, labels: List[str] | None = None) -> Dict[str, Any]:
        if not any(r["owner"] == owner and r["name"] == repo for r in self.repos):
            return {"status": "failed", "output": f"Repo {owner}/{repo} not found"}
        next_number = max((i["number"] for i in self.issues if i["repo"] == repo), default=0) + 1
        issue = {
            "id": max(i["id"] for i in self.issues) + 1 if self.issues else 1,
            "number": next_number,
            "repo": repo,
            "title": title,
            "body": body or "",
            "state": "open",
            "user": self.user["login"],
            "assignee": assignee or "",
            "labels": labels or [],
            "milestone": None,
            "created_at": self._now(),
            "updated_at": self._now(),
            "closed_at": None,
            "is_pull_request": False,
        }
        self.issues.append(issue)
        for j, r in enumerate(self.repos):
            if r["owner"] == owner and r["name"] == repo:
                self.repos[j]["open_issues"] += 1
        return {"status": "ok", "output": self._serialize_issue(issue)}

    def update_issue(self, owner: str, repo: str, number: int, title: str | None = None,
                     body: str | None = None, state: str | None = None,
                     assignee: str | None = None, labels: List[str] | None = None) -> Dict[str, Any]:
        for i, issue in enumerate(self.issues):
            if issue["repo"] == repo and issue["number"] == number:
                if title is not None:
                    self.issues[i]["title"] = title
                if body is not None:
                    self.issues[i]["body"] = body
                if assignee is not None:
                    self.issues[i]["assignee"] = assignee
                if labels is not None:
                    self.issues[i]["labels"] = labels
                if state and state != self.issues[i]["state"]:
                    self.issues[i]["state"] = state
                    if state == "closed":
                        self.issues[i]["closed_at"] = self._now()
                        for j, r in enumerate(self.repos):
                            if r["name"] == repo:
                                self.repos[j]["open_issues"] = max(0, self.repos[j]["open_issues"] - 1)
                    else:
                        self.issues[i]["closed_at"] = None
                self.issues[i]["updated_at"] = self._now()
                return {"status": "ok", "output": self._serialize_issue(self.issues[i])}
        return {"status": "failed", "output": f"Issue {repo}#{number} not found"}

    def list_pulls(self, owner: str, repo: str, state: str = "open") -> Dict[str, Any]:
        if not any(r["owner"] == owner and r["name"] == repo for r in self.repos):
            return {"status": "failed", "output": f"Repo {owner}/{repo} not found"}
        pulls = [p for p in self.pulls if p["repo"] == repo]
        issues_by_number = {i["number"]: i for i in self.issues if i["repo"] == repo}
        out = []
        for p in pulls:
            issue = issues_by_number.get(p["number"])
            if not issue:
                continue
            if state != "all" and issue["state"] != state:
                continue
            out.append({**self._serialize_issue(issue), **p, "issue_state": issue["state"]})
        return {"status": "ok", "output": out}

    def get_pull(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        pull = next((p for p in self.pulls if p["repo"] == repo and p["number"] == number), None)
        issue = next((i for i in self.issues if i["repo"] == repo and i["number"] == number), None)
        if not pull or not issue:
            return {"status": "failed", "output": f"Pull {repo}#{number} not found"}
        return {"status": "ok", "output": {**self._serialize_issue(issue), **pull}}

    def merge_pull(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        for i, p in enumerate(self.pulls):
            if p["repo"] == repo and p["number"] == number:
                if not p["mergeable"]:
                    return {"status": "failed", "output": "PR is not mergeable"}
                if p["draft"]:
                    return {"status": "failed", "output": "PR is a draft"}
                self.pulls[i]["merged"] = True
                self.update_issue(owner, repo, number, state="closed")
                return {"status": "ok", "output": {"merged": True, "sha": "deadbeefcafe123"}}
        return {"status": "failed", "output": f"Pull {repo}#{number} not found"}

    def list_comments(self, owner: str, repo: str, number: int) -> Dict[str, Any]:
        if not any(i["repo"] == repo and i["number"] == number for i in self.issues):
            return {"status": "failed", "output": f"Issue {repo}#{number} not found"}
        return {"status": "ok", "output": [c for c in self.comments if c["repo"] == repo and c["issue_number"] == number]}

    def create_comment(self, owner: str, repo: str, number: int, body: str) -> Dict[str, Any]:
        if not any(i["repo"] == repo and i["number"] == number for i in self.issues):
            return {"status": "failed", "output": f"Issue {repo}#{number} not found"}
        comment = {
            "id": max(c["id"] for c in self.comments) + 1 if self.comments else 1,
            "issue_number": number,
            "repo": repo,
            "user": self.user["login"],
            "body": body,
            "created_at": self._now(),
        }
        self.comments.append(comment)
        return {"status": "ok", "output": comment}


if __name__ == "__main__":
    s = GithubSession(seed=12)
    print(s.get_user())
    print(s.list_repos())
