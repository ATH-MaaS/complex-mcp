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


def _to_int(v) -> int:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return 0


class LinkedinSession:
    """Deterministic sandbox for the LinkedIn mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "linkedin.yaml") as f:
                info = yaml.safe_load(f)

            self.profile: Dict[str, Any] = dict(info.get("profile", {}))
            self.connections: List[Dict[str, Any]] = list(info.get("connections", []))
            self.posts: List[Dict[str, Any]] = [self._coerce_post(p) for p in info.get("posts", [])]
            self.organizations: List[Dict[str, Any]] = [
                {**o, "followerCount": _to_int(o.get("followerCount"))} for o in info.get("organizations", [])
            ]
            self.jobs: List[Dict[str, Any]] = [
                {
                    **j,
                    "applicants": _to_int(j.get("applicants")),
                    "keywords": [k for k in str(j.get("keywords", "")).split(" ") if k],
                }
                for j in info.get("jobs", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightLinkedIn')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"posts": self.posts}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=10))

    def _coerce_post(self, r: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in r.items() if k not in ("like_count", "comment_count", "share_count")}
        out["socialDetail"] = {
            "likeCount": _to_int(r.get("like_count")),
            "commentCount": _to_int(r.get("comment_count")),
            "shareCount": _to_int(r.get("share_count")),
        }
        return out

    # --- API methods -------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.profile}

    def list_connections(self, start: int = 0, count: int = 50) -> Dict[str, Any]:
        rows = self.connections
        sliced = rows[start: start + count]
        return {"status": "ok", "output": {
            "elements": sliced,
            "paging": {"start": start, "count": count, "total": len(rows)},
        }}

    def list_posts(self, author_id: str | None = None, start: int = 0, count: int = 50) -> Dict[str, Any]:
        posts = list(self.posts)
        if author_id:
            posts = [p for p in posts if p["author_id"] == author_id]
        posts.sort(key=lambda p: p["created_at"], reverse=True)
        sliced = posts[start: start + count]
        return {"status": "ok", "output": {
            "elements": sliced,
            "paging": {"start": start, "count": count, "total": len(posts)},
        }}

    def get_post(self, post_id: str) -> Dict[str, Any]:
        for p in self.posts:
            if p["id"] == post_id:
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": f"Post {post_id} not found"}

    def create_post(self, commentary: str, author_id: str | None = None,
                    visibility: str = "PUBLIC") -> Dict[str, Any]:
        author_id = author_id or self.profile["id"]
        post = {
            "id": self.uuid(),
            "author_id": author_id,
            "commentary": commentary,
            "visibility": visibility,
            "created_at": self._now(),
            "socialDetail": {"likeCount": 0, "commentCount": 0, "shareCount": 0},
        }
        self.posts.append(post)
        return {"status": "ok", "output": post}

    def get_organization(self, org_id: str) -> Dict[str, Any]:
        for o in self.organizations:
            if o["id"] == org_id:
                return {"status": "ok", "output": o}
        return {"status": "failed", "output": f"Organization {org_id} not found"}

    def search_jobs(self, keywords: str | None = None, location: str | None = None,
                    start: int = 0, count: int = 50) -> Dict[str, Any]:
        jobs = list(self.jobs)
        if keywords:
            q = keywords.lower()
            jobs = [j for j in jobs
                    if q in j["title"].lower()
                    or q in j["description"].lower()
                    or any(q in k.lower() for k in j["keywords"])]
        if location:
            loc = location.lower()
            jobs = [j for j in jobs if loc in j["location"].lower()]
        jobs.sort(key=lambda j: j["postedAt"], reverse=True)
        sliced = jobs[start: start + count]
        return {"status": "ok", "output": {
            "elements": sliced,
            "paging": {"start": start, "count": count, "total": len(jobs)},
        }}

    def get_job(self, job_id: str) -> Dict[str, Any]:
        for j in self.jobs:
            if j["id"] == job_id:
                return {"status": "ok", "output": j}
        return {"status": "failed", "output": f"Job {job_id} not found"}


if __name__ == "__main__":
    s = LinkedinSession(seed=12)
    print(s.get_me())
    print(s.list_posts())
