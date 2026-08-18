import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import json
from copy import deepcopy
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


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_json(v, default=None):
    if not v:
        return default if default is not None else {}
    if isinstance(v, (dict, list)):
        return v
    return json.loads(v)


class ContentfulSession:
    """Deterministic sandbox for the Contentful mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "contentful.yaml") as f:
                info = yaml.safe_load(f)

            self.space: Dict[str, Any] = info.get("space", {})

            self.content_types: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "displayField": r["displayField"],
                    "description": r["description"],
                    "fields": _parse_json(r.get("fields_json"), []),
                }
                for r in info.get("content_types", [])
            ]

            self.entries: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "content_type": r["content_type"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "published_version": _to_int(r.get("published_version"), default=0),
                    "fields": _parse_json(r.get("fields_json"), {}),
                }
                for r in info.get("entries", [])
            ]

            self.assets: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "published_version": _to_int(r.get("published_version"), default=0),
                    "title": r["title"],
                    "description": r["description"],
                    "file_url": r["file_url"],
                    "content_type": r["content_type"],
                    "file_name": r["file_name"],
                    "size": _to_int(r.get("size"), default=0),
                }
                for r in info.get("assets", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightContentful')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"entries": self.entries}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _content_type_obj(self, ct):
        return {
            "sys": {"id": ct["id"], "type": "ContentType"},
            "name": ct["name"],
            "displayField": ct["displayField"],
            "description": ct["description"],
            "fields": ct["fields"],
        }

    def _entry_obj(self, e):
        return {
            "sys": {
                "id": e["id"],
                "type": "Entry",
                "createdAt": e["created_at"],
                "updatedAt": e["updated_at"],
                "publishedVersion": e["published_version"],
                "contentType": {
                    "sys": {"type": "Link", "linkType": "ContentType", "id": e["content_type"]}
                },
            },
            "fields": deepcopy(e["fields"]),
        }

    def _asset_obj(self, a):
        return {
            "sys": {
                "id": a["id"],
                "type": "Asset",
                "createdAt": a["created_at"],
                "updatedAt": a["updated_at"],
                "publishedVersion": a["published_version"],
            },
            "fields": {
                "title": a["title"],
                "description": a["description"],
                "file": {
                    "url": a["file_url"],
                    "fileName": a["file_name"],
                    "contentType": a["content_type"],
                    "details": {"size": a["size"]},
                },
            },
        }

    def _collection(self, items):
        return {
            "sys": {"type": "Array"},
            "total": len(items),
            "skip": 0,
            "limit": len(items),
            "items": items,
        }

    # --- API methods -------------------------------------------------------
    def get_space(self) -> Dict[str, Any]:
        return {"status": "ok", "output": deepcopy(self.space)}

    def list_content_types(self) -> Dict[str, Any]:
        items = [self._content_type_obj(ct) for ct in self.content_types]
        return {"status": "ok", "output": self._collection(items)}

    def get_content_type(self, content_type_id: str) -> Dict[str, Any]:
        for ct in self.content_types:
            if ct["id"] == content_type_id:
                return {"status": "ok", "output": self._content_type_obj(ct)}
        return {"status": "failed", "output": f"Content type {content_type_id} not found"}

    def list_entries(self, content_type: str | None = None, field_filters: Dict[str, Any] | None = None,
                     limit: int = 100, skip: int = 0) -> Dict[str, Any]:
        entries = list(self.entries)
        if content_type:
            entries = [e for e in entries if e["content_type"] == content_type]
        if field_filters:
            for fname, fvalue in field_filters.items():
                entries = [e for e in entries if str(e["fields"].get(fname)) == str(fvalue)]
        total = len(entries)
        try:
            skip = max(0, int(skip))
        except (TypeError, ValueError):
            skip = 0
        try:
            limit = max(1, min(int(limit), 1000))
        except (TypeError, ValueError):
            limit = 100
        page = entries[skip: skip + limit]
        coll = self._collection([self._entry_obj(e) for e in page])
        coll["total"] = total
        coll["skip"] = skip
        coll["limit"] = limit
        return {"status": "ok", "output": coll}

    def get_entry(self, entry_id: str) -> Dict[str, Any]:
        for e in self.entries:
            if e["id"] == entry_id:
                return {"status": "ok", "output": self._entry_obj(e)}
        return {"status": "failed", "output": f"Entry {entry_id} not found"}

    def create_entry(self, content_type: str, fields: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not any(ct["id"] == content_type for ct in self.content_types):
            return {"status": "failed", "output": f"Content type {content_type} not found"}
        now = self._now()
        entry = {
            "id": self.uuid(),
            "content_type": content_type,
            "created_at": now,
            "updated_at": now,
            "published_version": 0,
            "fields": dict(fields or {}),
        }
        self.entries.append(entry)
        return {"status": "ok", "output": self._entry_obj(entry)}

    def update_entry(self, entry_id: str, fields: Dict[str, Any] | None = None) -> Dict[str, Any]:
        for e in self.entries:
            if e["id"] == entry_id:
                if fields:
                    e["fields"].update(fields)
                e["updated_at"] = self._now()
                return {"status": "ok", "output": self._entry_obj(e)}
        return {"status": "failed", "output": f"Entry {entry_id} not found"}

    def delete_entry(self, entry_id: str) -> Dict[str, Any]:
        for i, e in enumerate(self.entries):
            if e["id"] == entry_id:
                self.entries.pop(i)
                return {"status": "ok", "output": {"id": entry_id, "deleted": True}}
        return {"status": "failed", "output": f"Entry {entry_id} not found"}

    def list_assets(self) -> Dict[str, Any]:
        items = [self._asset_obj(a) for a in self.assets]
        return {"status": "ok", "output": self._collection(items)}

    def get_asset(self, asset_id: str) -> Dict[str, Any]:
        for a in self.assets:
            if a["id"] == asset_id:
                return {"status": "ok", "output": self._asset_obj(a)}
        return {"status": "failed", "output": f"Asset {asset_id} not found"}


if __name__ == "__main__":
    s = ContentfulSession(seed=12)
    print(s.get_space())
    print(s.list_content_types())
