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


class WebflowSession:
    """Deterministic sandbox for the Webflow Data API v2 mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "webflow.yaml") as f:
                info = yaml.safe_load(f)

            self.sites: List[Dict[str, Any]] = [
                {
                    "id": s["id"],
                    "workspace_id": s["workspace_id"],
                    "display_name": s["display_name"],
                    "short_name": s["short_name"],
                    "preview_url": s["preview_url"],
                    "time_zone": s["time_zone"],
                    "created_on": s["created_on"],
                    "last_published": s["last_published"],
                    "custom_domains": [d for d in str(s.get("custom_domains") or "").split(";") if d],
                }
                for s in info.get("sites", [])
            ]
            self.collections: List[Dict[str, Any]] = [
                {
                    "id": c["id"],
                    "site_id": c["site_id"],
                    "display_name": c["display_name"],
                    "singular_name": c["singular_name"],
                    "slug": c["slug"],
                    "created_on": c["created_on"],
                    "last_updated": c["last_updated"],
                }
                for c in info.get("collections", [])
            ]
            self.items: List[Dict[str, Any]] = [
                {
                    "id": i["id"],
                    "collection_id": i["collection_id"],
                    "name": i["name"],
                    "slug": i["slug"],
                    "is_draft": _to_bool(i.get("is_draft", False)),
                    "is_archived": _to_bool(i.get("is_archived", False)),
                    "summary": i["summary"],
                    "created_on": i["created_on"],
                    "last_updated": i["last_updated"],
                }
                for i in info.get("items", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightWebflow')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"items": self.items}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=24))

    def _hex(self, k: int) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=k))

    def _slugify(self, value) -> str:
        out = []
        for ch in (value or "").lower():
            if ch.isalnum():
                out.append(ch)
            elif ch in " -_":
                out.append("-")
        slug = "".join(out).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug or "item"

    # --- serializers -------------------------------------------------------
    def _serialize_site(self, s):
        return {
            "id": s["id"],
            "workspaceId": s["workspace_id"],
            "displayName": s["display_name"],
            "shortName": s["short_name"],
            "previewUrl": s["preview_url"],
            "timeZone": s["time_zone"],
            "createdOn": s["created_on"],
            "lastPublished": s["last_published"],
            "customDomains": [{"id": self._hex(16), "url": d} for d in s["custom_domains"]],
        }

    def _serialize_collection(self, c):
        return {
            "id": c["id"],
            "siteId": c["site_id"],
            "displayName": c["display_name"],
            "singularName": c["singular_name"],
            "slug": c["slug"],
            "createdOn": c["created_on"],
            "lastUpdated": c["last_updated"],
        }

    def _serialize_item(self, i):
        return {
            "id": i["id"],
            "cmsLocaleId": None,
            "lastPublished": None,
            "lastUpdated": i["last_updated"],
            "createdOn": i["created_on"],
            "isArchived": i["is_archived"],
            "isDraft": i["is_draft"],
            "fieldData": {
                "name": i["name"],
                "slug": i["slug"],
                "summary": i["summary"],
            },
        }

    # --- API methods -------------------------------------------------------
    def list_sites(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "sites": [self._serialize_site(s) for s in self.sites],
        }}

    def get_site(self, site_id: str) -> Dict[str, Any]:
        s = next((x for x in self.sites if x["id"] == site_id), None)
        if not s:
            return {"status": "failed", "output": f"Site {site_id} not found"}
        return {"status": "ok", "output": self._serialize_site(s)}

    def list_collections(self, site_id: str) -> Dict[str, Any]:
        if not any(s["id"] == site_id for s in self.sites):
            return {"status": "failed", "output": f"Site {site_id} not found"}
        cols = [c for c in self.collections if c["site_id"] == site_id]
        return {"status": "ok", "output": {
            "collections": [self._serialize_collection(c) for c in cols],
        }}

    def list_items(self, collection_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == collection_id for c in self.collections):
            return {"status": "failed", "output": f"Collection {collection_id} not found"}
        items = [i for i in self.items if i["collection_id"] == collection_id]
        total = len(items)
        window = items[offset:offset + limit]
        return {"status": "ok", "output": {
            "items": [self._serialize_item(i) for i in window],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }}

    def create_item(self, collection_id: str, field_data: Dict[str, Any] | None = None,
                    is_draft: bool = False, is_archived: bool = False) -> Dict[str, Any]:
        if not any(c["id"] == collection_id for c in self.collections):
            return {"status": "failed", "output": f"Collection {collection_id} not found"}
        field_data = field_data or {}
        name = field_data.get("name") or "Untitled"
        slug = field_data.get("slug") or self._slugify(name)
        now = self._now()
        item = {
            "id": self.uuid(),
            "collection_id": collection_id,
            "name": name,
            "slug": slug,
            "is_draft": bool(is_draft),
            "is_archived": bool(is_archived),
            "summary": field_data.get("summary", ""),
            "created_on": now,
            "last_updated": now,
        }
        self.items.append(item)
        serialized = self._serialize_item(item)
        # Surface any extra custom fields the caller supplied.
        for k, v in field_data.items():
            serialized["fieldData"].setdefault(k, v)
        return {"status": "ok", "output": serialized}


if __name__ == "__main__":
    s = WebflowSession(seed=12)
    print(s.list_sites())
    print(s.list_collections("650a1f0000000000000001a1"))
    print(s.create_item("660b2a0000000000000002b1", {"name": "Hello World"}))
