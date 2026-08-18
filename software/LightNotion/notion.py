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


class NotionSession:
    """Deterministic sandbox for the Notion mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "notion.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = [
                {
                    **u,
                    "bot": _to_bool(u.get("bot", False)),
                    "avatar_url": (str(u.get("avatar_url") or "") or None),
                    "email": (str(u.get("email") or "") or None),
                }
                for u in info.get("users", [])
            ]
            self.databases: List[Dict[str, Any]] = [
                {**d, "archived": _to_bool(d.get("archived", False))} for d in info.get("databases", [])
            ]
            self.pages: List[Dict[str, Any]] = [
                {
                    **p,
                    "archived": _to_bool(p.get("archived", False)),
                    "cover_url": (str(p.get("cover_url") or "") or None),
                }
                for p in info.get("pages", [])
            ]
            self.blocks: List[Dict[str, Any]] = [
                {
                    **b,
                    "order": int(b.get("order") or 0),
                    "has_children": _to_bool(b.get("has_children", False)),
                    "checked": (_to_bool(b.get("checked")) if b.get("checked") else None),
                    "parent_block_id": (str(b.get("parent_block_id") or "") or None),
                }
                for b in info.get("blocks", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    **c,
                    "resolved": _to_bool(c.get("resolved", False)),
                    "parent_block_id": (str(c.get("parent_block_id") or "") or None),
                }
                for c in info.get("comments", [])
            ]
            self.properties: Dict[str, Dict[str, Any]] = self._group_properties(info.get("page_properties", []))
            self.workspace: Dict[str, Any] = info.get("workspace", {})
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightNotion')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    @staticmethod
    def _group_properties(rows):
        grouped: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            page_id = str(r.get("page_id"))
            grouped.setdefault(page_id, {})
            value = r.get("value")
            ptype = str(r.get("property_type"))
            if ptype == "number":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass
            grouped[page_id][str(r.get("property_name"))] = {"type": ptype, "value": value}
        return grouped

    def get_session_dict(self):
        return {"pages": self.pages, "blocks": self.blocks, "comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_id(self, prefix):
        return f"{prefix}-{self.uuid()}"

    def _attach_properties(self, page):
        page = dict(page)
        page["properties"] = self.properties.get(page["id"], {})
        return page

    def _paginate(self, items, start_cursor=None, page_size=50):
        if start_cursor:
            try:
                offset = int(start_cursor)
            except (TypeError, ValueError):
                offset = 0
        else:
            offset = 0
        page_size = max(1, min(page_size, 100))
        sliced = items[offset: offset + page_size]
        next_cursor = str(offset + page_size) if offset + page_size < len(items) else None
        return {
            "object": "list",
            "results": sliced,
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        }

    # --- Users -------------------------------------------------------------
    def list_users(self, start_cursor: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        return {"status": "ok", "output": self._paginate(list(self.users), start_cursor, page_size)}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == user_id:
                return {"status": "ok", "output": u}
        return {"status": "failed", "output": f"User {user_id} not found"}

    def get_me(self) -> Dict[str, Any]:
        for u in self.users:
            if not u["bot"]:
                return {"status": "ok", "output": u}
        return {"status": "ok", "output": self.users[0]}

    # --- Workspace / search ------------------------------------------------
    def get_workspace(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.workspace}

    def search(self, query: str | None = None, filter_value: str | None = None,
               start_cursor: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        pool = []
        if filter_value in (None, "page"):
            pool.extend({**self._attach_properties(p), "object": "page"} for p in self.pages if not p["archived"])
        if filter_value in (None, "database"):
            pool.extend({**d, "object": "database"} for d in self.databases if not d["archived"])
        if query:
            q = query.lower()
            pool = [p for p in pool if q in p.get("title", "").lower()]
        return {"status": "ok", "output": self._paginate(pool, start_cursor, page_size)}

    # --- Databases ---------------------------------------------------------
    def get_database(self, database_id: str) -> Dict[str, Any]:
        for d in self.databases:
            if d["id"] == database_id:
                return {"status": "ok", "output": d}
        return {"status": "failed", "output": f"Database {database_id} not found"}

    def query_database(self, database_id: str, filter_status: str | None = None,
                       filter_assignee: str | None = None, sort_by: str | None = None,
                       start_cursor: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        if not any(d["id"] == database_id for d in self.databases):
            return {"status": "failed", "output": f"Database {database_id} not found"}
        pages = [p for p in self.pages
                 if p["parent_type"] == "database" and p["parent_id"] == database_id and not p["archived"]]
        pages = [self._attach_properties(p) for p in pages]
        if filter_status:
            pages = [p for p in pages
                     if str(p["properties"].get("Status", {}).get("value", "")).lower() == filter_status.lower()]
        if filter_assignee:
            pages = [p for p in pages
                     if p["properties"].get("Assignee", {}).get("value") == filter_assignee]
        if sort_by == "last_edited_time":
            pages.sort(key=lambda p: p["last_edited_time"], reverse=True)
        elif sort_by == "created_time":
            pages.sort(key=lambda p: p["created_time"], reverse=True)
        return {"status": "ok", "output": self._paginate(pages, start_cursor, page_size)}

    # --- Pages -------------------------------------------------------------
    def get_page(self, page_id: str) -> Dict[str, Any]:
        for p in self.pages:
            if p["id"] == page_id:
                return {"status": "ok", "output": self._attach_properties(p)}
        return {"status": "failed", "output": f"Page {page_id} not found"}

    def create_page(self, parent_type: str, parent_id: str, title: str,
                    properties: Dict[str, Any] | None = None, created_by: str = "user-amelia") -> Dict[str, Any]:
        if parent_type == "database":
            if not any(d["id"] == parent_id for d in self.databases):
                return {"status": "failed", "output": f"Database {parent_id} not found"}
        elif parent_type == "page":
            if not any(p["id"] == parent_id for p in self.pages):
                return {"status": "failed", "output": f"Parent page {parent_id} not found"}
        elif parent_type == "workspace":
            if parent_id != self.workspace.get("id"):
                return {"status": "failed", "output": f"Workspace {parent_id} not found"}
        else:
            return {"status": "failed", "output": f"Unsupported parent_type: {parent_type}"}

        now = self._now()
        page = {
            "id": self._new_id("page"),
            "parent_type": parent_type,
            "parent_id": parent_id,
            "title": title,
            "created_time": now,
            "last_edited_time": now,
            "created_by": created_by,
            "archived": False,
            "icon": "",
            "cover_url": None,
        }
        self.pages.append(page)
        if properties:
            self.properties[page["id"]] = {
                k: ({"type": v.get("type", "rich_text"), "value": v.get("value")}
                    if isinstance(v, dict) else {"type": "rich_text", "value": v})
                for k, v in properties.items()
            }
        return {"status": "ok", "output": self._attach_properties(page)}

    def update_page(self, page_id: str, title: str | None = None, archived: bool | None = None,
                    properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        for p in self.pages:
            if p["id"] == page_id:
                if title is not None:
                    p["title"] = title
                if archived is not None:
                    p["archived"] = bool(archived)
                if properties:
                    existing = self.properties.setdefault(page_id, {})
                    for k, v in properties.items():
                        if isinstance(v, dict):
                            existing[k] = {"type": v.get("type", "rich_text"), "value": v.get("value")}
                        else:
                            existing[k] = {"type": existing.get(k, {}).get("type", "rich_text"), "value": v}
                p["last_edited_time"] = self._now()
                return {"status": "ok", "output": self._attach_properties(p)}
        return {"status": "failed", "output": f"Page {page_id} not found"}

    def delete_page(self, page_id: str) -> Dict[str, Any]:
        return self.update_page(page_id, archived=True)

    # --- Blocks ------------------------------------------------------------
    def list_block_children(self, block_id: str, start_cursor: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        if any(p["id"] == block_id for p in self.pages):
            children = [b for b in self.blocks if b["page_id"] == block_id and not b["parent_block_id"]]
        else:
            children = [b for b in self.blocks if b["parent_block_id"] == block_id]
        children = sorted(children, key=lambda b: b["order"])
        return {"status": "ok", "output": self._paginate(children, start_cursor, page_size)}

    def append_block_children(self, parent_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        if any(p["id"] == parent_id for p in self.pages):
            page_id = parent_id
            parent_block_id = None
            siblings = [b for b in self.blocks if b["page_id"] == page_id and not b["parent_block_id"]]
        else:
            parent_block = next((b for b in self.blocks if b["id"] == parent_id), None)
            if not parent_block:
                return {"status": "failed", "output": f"Parent {parent_id} not found"}
            page_id = parent_block["page_id"]
            parent_block_id = parent_id
            siblings = [b for b in self.blocks if b["parent_block_id"] == parent_id]

        next_order = max((b["order"] for b in siblings), default=-1) + 1
        now = self._now()
        created = []
        for blk in children:
            new_block = {
                "id": self._new_id("block"),
                "page_id": page_id,
                "parent_block_id": parent_block_id,
                "type": blk.get("type", "paragraph"),
                "text": blk.get("text", ""),
                "order": next_order,
                "created_time": now,
                "last_edited_time": now,
                "has_children": False,
                "checked": blk.get("checked") if blk.get("type") == "to_do" else None,
            }
            self.blocks.append(new_block)
            created.append(new_block)
            next_order += 1
        return {"status": "ok", "output": {"object": "list", "results": created}}

    def update_block(self, block_id: str, text: str | None = None, checked: bool | None = None) -> Dict[str, Any]:
        for b in self.blocks:
            if b["id"] == block_id:
                if text is not None:
                    b["text"] = text
                if checked is not None and b["type"] == "to_do":
                    b["checked"] = bool(checked)
                b["last_edited_time"] = self._now()
                return {"status": "ok", "output": b}
        return {"status": "failed", "output": f"Block {block_id} not found"}

    def delete_block(self, block_id: str) -> Dict[str, Any]:
        for i, b in enumerate(self.blocks):
            if b["id"] == block_id:
                self.blocks.pop(i)
                return {"status": "ok", "output": {"object": "block", "id": block_id, "deleted": True}}
        return {"status": "failed", "output": f"Block {block_id} not found"}

    # --- Comments ----------------------------------------------------------
    def list_comments(self, block_id: str | None = None, page_id: str | None = None) -> Dict[str, Any]:
        results = list(self.comments)
        if block_id:
            results = [c for c in results if c["parent_block_id"] == block_id]
        if page_id:
            results = [c for c in results if c["parent_page_id"] == page_id]
        return {"status": "ok", "output": {"object": "list", "results": results}}

    def create_comment(self, parent_page_id: str, author_id: str, text: str,
                       parent_block_id: str | None = None) -> Dict[str, Any]:
        if not any(p["id"] == parent_page_id for p in self.pages):
            return {"status": "failed", "output": f"Page {parent_page_id} not found"}
        comment = {
            "id": self._new_id("comment"),
            "parent_page_id": parent_page_id,
            "parent_block_id": parent_block_id,
            "author_id": author_id,
            "text": text,
            "created_time": self._now(),
            "resolved": False,
        }
        self.comments.append(comment)
        return {"status": "ok", "output": comment}


if __name__ == "__main__":
    s = NotionSession(seed=12)
    print(s.get_me())
    print(s.list_users())
