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


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class ConfluenceSession:
    """Deterministic sandbox for the Confluence mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    BASE = "/wiki/rest/api"

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "confluence.yaml") as f:
                info = yaml.safe_load(f)

            self.spaces: List[Dict[str, Any]] = [
                {
                    "id": _to_int(s.get("id"), 0),
                    "key": s["key"],
                    "name": s["name"],
                    "type": s["type"],
                    "status": s["status"],
                    "description": {"plain": {"value": s["description"], "representation": "plain"}},
                }
                for s in info.get("spaces", [])
            ]
            self.pages: List[Dict[str, Any]] = [
                {
                    "id": p["id"],
                    "type": p["type"],
                    "status": p["status"],
                    "title": p["title"],
                    "space_key": p["space_key"],
                    "parent_id": (p.get("parent_id") or None),
                    "version": _to_int(p.get("version"), 1),
                    "body": p["body"],
                    "created_by": p["created_by"],
                    "created_at": p["created_at"],
                }
                for p in info.get("pages", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    "id": c["id"],
                    "page_id": c["page_id"],
                    "author": c["author"],
                    "body": c["body"],
                    "created_at": c["created_at"],
                }
                for c in info.get("comments", [])
            ]
            self.labels: List[Dict[str, Any]] = [
                {
                    "id": l["id"],
                    "page_id": l["page_id"],
                    "name": l["name"],
                    "prefix": l["prefix"],
                }
                for l in info.get("labels", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightConfluence')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"pages": self.pages}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        return str(self.rng.getrandbits(64) % 9_000_000 + 1_000_000)

    def _find_page(self, page_id):
        return next((p for p in self.pages if p["id"] == page_id), None)

    def _find_space(self, space_key):
        return next((s for s in self.spaces if s["key"] == space_key), None)

    def _content_view(self, page, expand_body=True):
        view = {
            "id": page["id"],
            "type": page["type"],
            "status": page["status"],
            "title": page["title"],
            "space": {"key": page["space_key"]},
            "version": {"number": page["version"]},
            "history": {"createdBy": {"username": page["created_by"]}, "createdDate": page["created_at"]},
            "_links": {"webui": f"/spaces/{page['space_key']}/pages/{page['id']}"},
        }
        if page["parent_id"]:
            view["ancestors"] = [{"id": page["parent_id"], "type": "page"}]
        if expand_body:
            view["body"] = {"storage": {"value": page["body"], "representation": "storage"}}
        return view

    # --- Spaces ------------------------------------------------------------
    def list_spaces(self, limit: int = 25) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "results": [dict(s) for s in self.spaces[:limit]],
            "size": min(len(self.spaces), limit),
            "_links": {"base": self.BASE},
        }}

    def get_space(self, space_key: str) -> Dict[str, Any]:
        s = self._find_space(space_key)
        if not s:
            return {"status": "failed", "output": f"No space with key: {space_key}"}
        return {"status": "ok", "output": dict(s)}

    # --- Content (pages) ---------------------------------------------------
    def list_content(self, type: str = "page", space_key: str | None = None, limit: int = 25) -> Dict[str, Any]:
        results = [p for p in self.pages if p["type"] == type]
        if space_key:
            results = [p for p in results if p["space_key"] == space_key]
        views = [self._content_view(p) for p in results[:limit]]
        return {"status": "ok", "output": {"results": views, "size": len(views), "_links": {"base": self.BASE}}}

    def get_content(self, content_id: str) -> Dict[str, Any]:
        p = self._find_page(content_id)
        if not p:
            return {"status": "failed", "output": f"No content with id: {content_id}"}
        return {"status": "ok", "output": self._content_view(p)}

    def create_content(self, title: str, space_key: str, body: str = "",
                       parent_id: str | None = None, created_by: str = "apiuser") -> Dict[str, Any]:
        if not self._find_space(space_key):
            return {"status": "failed", "output": f"No space with key: {space_key}"}
        if parent_id and not self._find_page(parent_id):
            return {"status": "failed", "output": f"No parent content with id: {parent_id}"}
        page = {
            "id": self.uuid(),
            "type": "page",
            "status": "current",
            "title": title,
            "space_key": space_key,
            "parent_id": parent_id,
            "version": 1,
            "body": body or "",
            "created_by": created_by,
            "created_at": self._now(),
        }
        self.pages.append(page)
        return {"status": "ok", "output": self._content_view(page)}

    def update_content(self, content_id: str, title: str | None = None, body: str | None = None,
                       version_number: int | None = None) -> Dict[str, Any]:
        page = self._find_page(content_id)
        if not page:
            return {"status": "failed", "output": f"No content with id: {content_id}"}
        expected = page["version"] + 1
        if version_number is not None and version_number != expected:
            return {"status": "failed", "output": f"Version must be incremented; expected {expected}, got {version_number}"}
        if title is not None:
            page["title"] = title
        if body is not None:
            page["body"] = body
        page["version"] = expected
        return {"status": "ok", "output": self._content_view(page)}

    def list_child_pages(self, content_id: str, limit: int = 25) -> Dict[str, Any]:
        if not self._find_page(content_id):
            return {"status": "failed", "output": f"No content with id: {content_id}"}
        children = [p for p in self.pages if p["parent_id"] == content_id and p["type"] == "page"]
        views = [self._content_view(c, expand_body=False) for c in children[:limit]]
        return {"status": "ok", "output": {"results": views, "size": len(views), "_links": {"base": self.BASE}}}

    def list_labels(self, content_id: str) -> Dict[str, Any]:
        if not self._find_page(content_id):
            return {"status": "failed", "output": f"No content with id: {content_id}"}
        labels = [
            {"id": l["id"], "name": l["name"], "prefix": l["prefix"], "label": l["name"]}
            for l in self.labels if l["page_id"] == content_id
        ]
        return {"status": "ok", "output": {"results": labels, "size": len(labels)}}

    def list_comments(self, content_id: str) -> Dict[str, Any]:
        if not self._find_page(content_id):
            return {"status": "failed", "output": f"No content with id: {content_id}"}
        comments = [
            {
                "id": c["id"],
                "type": "comment",
                "container": {"id": content_id, "type": "page"},
                "history": {"createdBy": {"username": c["author"]}, "createdDate": c["created_at"]},
                "body": {"storage": {"value": c["body"], "representation": "storage"}},
            }
            for c in self.comments if c["page_id"] == content_id
        ]
        return {"status": "ok", "output": {"results": comments, "size": len(comments)}}

    # --- Search (simplified CQL) -------------------------------------------
    def search_content(self, cql: str) -> Dict[str, Any]:
        if not cql:
            return {"status": "failed", "output": "cql parameter is required"}
        results = list(self.pages)
        parts = [p.strip() for p in cql.split(" AND ")]
        for part in parts:
            if part.startswith("space="):
                key = part.split("=", 1)[1].strip().strip('"').strip("'")
                results = [p for p in results if p["space_key"] == key]
            elif part.startswith("title~"):
                term = part.split("~", 1)[1].strip().strip('"').strip("'").lower()
                results = [p for p in results if term in p["title"].lower()]
            elif part.startswith("type="):
                t = part.split("=", 1)[1].strip().strip('"').strip("'")
                results = [p for p in results if p["type"] == t]
        views = [self._content_view(p, expand_body=False) for p in results]
        return {"status": "ok", "output": {
            "results": [{"content": v, "title": v["title"]} for v in views],
            "size": len(views),
            "totalSize": len(views),
            "cqlQuery": cql,
        }}


if __name__ == "__main__":
    s = ConfluenceSession(seed=12)
    print(s.list_spaces())
    print(s.list_content())
