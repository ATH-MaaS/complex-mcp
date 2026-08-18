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


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _opt_int(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _split_ids(s):
    return [int(x) for x in (s or "").split(";") if str(x).strip()]


def _rendered(text):
    return {"rendered": text}


class WordpressSession:
    """Deterministic sandbox for the WordPress REST API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "wordpress.yaml") as f:
                info = yaml.safe_load(f)

            self.posts: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "title": _rendered(r["title"]),
                    "slug": r["slug"],
                    "status": r["status"],
                    "author": _to_int(r.get("author")),
                    "content": _rendered(r["content"]),
                    "excerpt": _rendered(r["excerpt"]),
                    "categories": _split_ids(r["category_ids"]),
                    "tags": _split_ids(r["tag_ids"]),
                    "comment_status": r["comment_status"],
                    "date": r["date"],
                    "modified": r["modified"],
                    "type": "post",
                }
                for r in info.get("posts", [])
            ]
            self.pages: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "title": _rendered(r["title"]),
                    "slug": r["slug"],
                    "status": r["status"],
                    "author": _to_int(r.get("author")),
                    "content": _rendered(r["content"]),
                    "date": r["date"],
                    "modified": r["modified"],
                    "parent": _to_int(r.get("parent")),
                    "type": "page",
                }
                for r in info.get("pages", [])
            ]
            self.categories: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "name": r["name"],
                    "slug": r["slug"],
                    "description": r["description"],
                    "parent": _to_int(r.get("parent")),
                    "count": _to_int(r.get("count")),
                    "taxonomy": "category",
                }
                for r in info.get("categories", [])
            ]
            self.tags: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "name": r["name"],
                    "slug": r["slug"],
                    "description": r["description"],
                    "count": _to_int(r.get("count")),
                    "taxonomy": "post_tag",
                }
                for r in info.get("tags", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "post": _to_int(r.get("post")),
                    "author_name": r["author_name"],
                    "author_email": r["author_email"],
                    "content": _rendered(r["content"]),
                    "status": r["status"],
                    "date": r["date"],
                    "parent": _to_int(r.get("parent")),
                }
                for r in info.get("comments", [])
            ]
            self.media: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "title": _rendered(r["title"]),
                    "slug": r["slug"],
                    "media_type": r["media_type"],
                    "mime_type": r["mime_type"],
                    "source_url": r["source_url"],
                    "alt_text": r["alt_text"],
                    "author": _to_int(r.get("author")),
                    "post": _opt_int(r.get("post")) or None,
                    "date": r["date"],
                    "type": "attachment",
                }
                for r in info.get("media", [])
            ]
            self.users: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "name": r["name"],
                    "slug": r["slug"],
                    "description": r["description"],
                    "url": r["url"],
                    "roles": [r["roles"]],
                    "avatar_urls": {"96": r["avatar_url"]},
                }
                for r in info.get("users", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightWordPress')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"posts": self.posts, "comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _next_id(self, store):
        return max((item["id"] for item in store), default=0) + 1

    # --- Posts -------------------------------------------------------------
    def list_posts(self, status: str | None = None, author: int | None = None,
                   search: str | None = None, category: int | None = None,
                   per_page: int = 10) -> Dict[str, Any]:
        posts = list(self.posts)
        posts = [p for p in posts if p["status"] == (status or "publish")]
        if author:
            posts = [p for p in posts if p["author"] == int(author)]
        if category:
            posts = [p for p in posts if int(category) in p["categories"]]
        if search:
            q = search.lower()
            posts = [p for p in posts
                     if q in p["title"]["rendered"].lower() or q in p["content"]["rendered"].lower()]
        posts.sort(key=lambda p: p["date"], reverse=True)
        return {"status": "ok", "output": posts[:per_page]}

    def get_post(self, post_id: int) -> Dict[str, Any]:
        for p in self.posts:
            if p["id"] == int(post_id):
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": {"error": f"Post {post_id} not found", "code": "rest_post_invalid_id"}}

    def create_post(self, title: str, content: str = "", status: str = "draft", author: int = 1,
                    excerpt: str = "", categories: List[int] | None = None,
                    tags: List[int] | None = None) -> Dict[str, Any]:
        now = self._now()
        post = {
            "id": self._next_id(self.posts),
            "title": _rendered(title),
            "slug": title.lower().replace(" ", "-")[:60],
            "status": status,
            "author": int(author),
            "content": _rendered(content),
            "excerpt": _rendered(excerpt),
            "categories": [int(c) for c in (categories or [])],
            "tags": [int(t) for t in (tags or [])],
            "comment_status": "open",
            "date": now,
            "modified": now,
            "type": "post",
        }
        self.posts.append(post)
        return {"status": "ok", "output": post}

    def update_post(self, post_id: int, title: str | None = None, content: str | None = None,
                    status: str | None = None, excerpt: str | None = None,
                    categories: List[int] | None = None, tags: List[int] | None = None) -> Dict[str, Any]:
        for p in self.posts:
            if p["id"] == int(post_id):
                if title is not None:
                    p["title"] = _rendered(title)
                if content is not None:
                    p["content"] = _rendered(content)
                if excerpt is not None:
                    p["excerpt"] = _rendered(excerpt)
                if status is not None:
                    p["status"] = status
                if categories is not None:
                    p["categories"] = [int(c) for c in categories]
                if tags is not None:
                    p["tags"] = [int(t) for t in tags]
                p["modified"] = self._now()
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": {"error": f"Post {post_id} not found", "code": "rest_post_invalid_id"}}

    def delete_post(self, post_id: int) -> Dict[str, Any]:
        for i, p in enumerate(self.posts):
            if p["id"] == int(post_id):
                removed = self.posts.pop(i)
                return {"status": "ok", "output": {"deleted": True, "previous": removed}}
        return {"status": "failed", "output": {"error": f"Post {post_id} not found", "code": "rest_post_invalid_id"}}

    # --- Pages -------------------------------------------------------------
    def list_pages(self, status: str = "publish", per_page: int = 10) -> Dict[str, Any]:
        pages = [p for p in self.pages if p["status"] == status]
        pages.sort(key=lambda p: p["date"], reverse=True)
        return {"status": "ok", "output": pages[:per_page]}

    # --- Taxonomies --------------------------------------------------------
    def list_categories(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.categories)}

    def list_tags(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.tags)}

    # --- Comments ----------------------------------------------------------
    def list_comments(self, post: int | None = None, status: str = "approved") -> Dict[str, Any]:
        comments = [c for c in self.comments if c["status"] == status]
        if post is not None:
            comments = [c for c in comments if c["post"] == int(post)]
        comments.sort(key=lambda c: c["date"])
        return {"status": "ok", "output": comments}

    def create_comment(self, post: int, author_name: str, author_email: str,
                       content: str, parent: int = 0) -> Dict[str, Any]:
        if not any(p["id"] == int(post) for p in self.posts):
            return {"status": "failed",
                    "output": {"error": f"Post {post} not found", "code": "rest_comment_invalid_post_id"}}
        comment = {
            "id": self._next_id(self.comments),
            "post": int(post),
            "author_name": author_name,
            "author_email": author_email,
            "content": _rendered(content),
            "status": "approved",
            "date": self._now(),
            "parent": int(parent),
        }
        self.comments.append(comment)
        return {"status": "ok", "output": comment}

    # --- Media / users -----------------------------------------------------
    def list_media(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.media)}

    def list_users(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.users)}


if __name__ == "__main__":
    s = WordpressSession(seed=12)
    print(s.list_posts())
    print(s.list_users())
