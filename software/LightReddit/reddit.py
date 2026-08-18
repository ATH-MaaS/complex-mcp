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


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class RedditSession:
    """Deterministic sandbox for the Reddit mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "reddit.yaml") as f:
                info = yaml.safe_load(f)

            self.subreddits: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "display_name": r["name"],
                    "title": r["title"],
                    "public_description": r["public_description"],
                    "subscribers": _to_int(r.get("subscribers")),
                    "created_utc": _to_float(r.get("created_utc")),
                    "over18": _to_bool(r.get("over18")),
                }
                for r in info.get("subreddits", [])
            ]
            self.posts: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "subreddit": r["subreddit"],
                    "title": r["title"],
                    "author": r["author"],
                    "url": (r.get("url") or None),
                    "selftext": r["selftext"],
                    "score": _to_int(r.get("score")),
                    "ups": _to_int(r.get("score")),
                    "num_comments": _to_int(r.get("num_comments")),
                    "created_utc": _to_float(r.get("created_utc")),
                    "is_self": _to_bool(r.get("is_self")),
                    "_likes": None,
                }
                for r in info.get("posts", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "post_id": r["post_id"],
                    "parent_id": r["parent_id"],
                    "author": r["author"],
                    "body": r["body"],
                    "score": _to_int(r.get("score")),
                    "ups": _to_int(r.get("score")),
                    "created_utc": _to_float(r.get("created_utc")),
                }
                for r in info.get("comments", [])
            ]
            self.users: List[Dict[str, Any]] = [
                {
                    "name": r["name"],
                    "id": r["id"],
                    "link_karma": _to_int(r.get("link_karma")),
                    "comment_karma": _to_int(r.get("comment_karma")),
                    "created_utc": _to_float(r.get("created_utc")),
                    "is_gold": _to_bool(r.get("is_gold")),
                    "is_mod": _to_bool(r.get("is_mod")),
                }
                for r in info.get("users", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightReddit')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"posts": self.posts, "comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=6))

    def _find_subreddit(self, name):
        return next((s for s in self.subreddits if s["display_name"].lower() == name.lower()), None)

    def _listing(self, children, kind="t3"):
        return {
            "kind": "Listing",
            "data": {
                "after": None,
                "before": None,
                "children": [{"kind": kind, "data": c} for c in children],
            },
        }

    def _adjust(self, thing, direction):
        prev = thing.get("_likes")
        prev_val = {True: 1, False: -1, None: 0}.get(prev, 0)
        new_val = {1: 1, -1: -1, 0: 0}.get(direction, 0)
        thing["score"] += new_val - prev_val
        thing["ups"] = thing["score"]
        thing["_likes"] = {1: True, -1: False, 0: None}.get(direction, None)

    # --- API methods -------------------------------------------------------
    def subreddit_about(self, subreddit: str) -> Dict[str, Any]:
        s = self._find_subreddit(subreddit)
        if not s:
            return {"status": "failed", "output": f"subreddit {subreddit} not found"}
        return {"status": "ok", "output": {"kind": "t5", "data": s}}

    def subreddit_hot(self, subreddit: str, limit: int = 25) -> Dict[str, Any]:
        return self._subreddit_listing(subreddit, sort="hot", limit=limit)

    def subreddit_new(self, subreddit: str, limit: int = 25) -> Dict[str, Any]:
        return self._subreddit_listing(subreddit, sort="new", limit=limit)

    def _subreddit_listing(self, name, sort="hot", limit=25) -> Dict[str, Any]:
        s = self._find_subreddit(name)
        if not s:
            return {"status": "failed", "output": f"subreddit {name} not found"}
        posts = [p for p in self.posts if p["subreddit"].lower() == name.lower()]
        if sort == "new":
            posts.sort(key=lambda p: p["created_utc"], reverse=True)
        else:
            posts.sort(key=lambda p: p["score"], reverse=True)
        return {"status": "ok", "output": self._listing(posts[: max(1, limit)], kind="t3")}

    def post_comments(self, post_id: str) -> Dict[str, Any]:
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"
        post = next((p for p in self.posts if p["id"] == post_id), None)
        if not post:
            return {"status": "failed", "output": f"post {post_id} not found"}
        post_listing = self._listing([post], kind="t3")
        comments = [c for c in self.comments if c["post_id"] == post_id]
        comments.sort(key=lambda c: c["score"], reverse=True)
        comment_listing = self._listing(comments, kind="t1")
        return {"status": "ok", "output": [post_listing, comment_listing]}

    def submit(self, sr: str, title: str, kind: str = "self", url: str | None = None,
               text: str | None = None, author: str | None = "devkat") -> Dict[str, Any]:
        author = author or "devkat"
        s = self._find_subreddit(sr)
        if not s:
            return {"status": "failed", "output": f"subreddit {sr} not found"}
        if not title:
            return {"status": "failed", "output": "title is required"}
        post = {
            "id": f"t3_{self.uuid()}",
            "subreddit": s["display_name"],
            "title": title,
            "author": author,
            "url": url if kind == "link" else None,
            "selftext": text or "" if kind == "self" else "",
            "score": 1,
            "ups": 1,
            "num_comments": 0,
            "created_utc": float(int(datetime.now().timestamp())),
            "is_self": kind == "self",
            "_likes": True,
        }
        self.posts.append(post)
        return {"status": "ok", "output": {"json": {"errors": [], "data": {
            "id": post["id"], "name": post["id"], "url": post["url"]}}}}

    def vote(self, id: str, dir: int) -> Dict[str, Any]:
        if dir not in (-1, 0, 1):
            return {"status": "failed", "output": "dir must be -1, 0, or 1"}
        target = None
        if id.startswith("t3_"):
            target = next((p for p in self.posts if p["id"] == id), None)
        elif id.startswith("t1_"):
            target = next((c for c in self.comments if c["id"] == id), None)
            if target is not None and "_likes" not in target:
                target["_likes"] = None
        if target is None:
            return {"status": "failed", "output": f"thing {id} not found"}
        self._adjust(target, dir)
        return {"status": "ok", "output": {"name": id, "score": target["score"], "likes": target["_likes"]}}

    def user_about(self, username: str) -> Dict[str, Any]:
        u = next((u for u in self.users if u["name"].lower() == username.lower()), None)
        if not u:
            return {"status": "failed", "output": f"user {username} not found"}
        return {"status": "ok", "output": {"kind": "t2", "data": u}}


if __name__ == "__main__":
    s = RedditSession(seed=12)
    print(s.subreddit_about("programming"))
    print(s.user_about("devkat"))
