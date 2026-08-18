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


def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _maybe_number(v):
    if v is None or v == "":
        return v
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _csv_list(v):
    if v is None:
        return []
    return [a.strip() for a in str(v).split(",") if a.strip()]


_NUMERIC_FIELDS = {"price"}
_BOOL_FIELDS = {"in_stock"}


class AlgoliaSession:
    """Deterministic sandbox for the Algolia mock, ported from the FastAPI service.

    Models hosted-search objects: indices, records (objects with an objectID),
    and per-index settings. Query implements a case-insensitive substring match
    across string fields and a simple attr:value equality filter syntax.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "algolia.yaml") as f:
                info = yaml.safe_load(f)

            indices_meta = list(info.get("indices", []))
            self.indices: List[Dict[str, Any]] = [
                {
                    "name": m["name"],
                    "entries": _to_int(m.get("entries"), default=0),
                    "dataSize": _to_int(m.get("data_size"), default=0),
                    "createdAt": m["created_at"],
                    "updatedAt": m["updated_at"],
                }
                for m in indices_meta
            ]

            # one record list per index name, keyed by objectID
            self.records: Dict[str, List[Dict[str, Any]]] = {}
            for m in indices_meta:
                key = m["records_csv"].replace(".json", "")
                self.records[m["name"]] = [self._coerce_record(r) for r in info.get(key, [])]

            self.settings: List[Dict[str, Any]] = [
                {"index": r["index"], **self._coerce_settings(r)} for r in info.get("settings", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAlgolia')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"records": self.records}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _coerce_record(self, row):
        out = {}
        for k, v in row.items():
            if k in _BOOL_FIELDS:
                out[k] = _to_bool(v)
            elif k in _NUMERIC_FIELDS:
                out[k] = _maybe_number(v)
            else:
                out[k] = v
        return out

    def _coerce_settings(self, row):
        return {
            "searchableAttributes": _csv_list(row.get("searchableAttributes")),
            "attributesForFaceting": _csv_list(row.get("attributesForFaceting")),
            "hitsPerPage": _to_int(row.get("hitsPerPage"), default=20),
            "ranking": _csv_list(row.get("ranking")),
        }

    def _index_exists(self, index):
        return any(i["name"] == index for i in self.indices)

    def _ensure_index(self, index):
        if self._index_exists(index):
            return
        self.indices.append({
            "name": index, "entries": 0, "dataSize": 0,
            "createdAt": "", "updatedAt": "",
        })
        self.records.setdefault(index, [])

    def _get_record(self, index, object_id):
        for r in self.records.get(index, []):
            if r.get("objectID") == object_id:
                return r
        return None

    def _matches_query(self, record, query):
        if not query:
            return True
        q = query.lower()
        for v in record.values():
            if isinstance(v, str) and q in v.lower():
                return True
        return False

    def _matches_filters(self, record, filters):
        if not filters:
            return True
        clauses = [c.strip() for c in filters.replace(" AND ", "\n").split("\n") if c.strip()]
        for clause in clauses:
            if ":" not in clause:
                continue
            attr, _, value = clause.partition(":")
            attr = attr.strip()
            value = value.strip().strip('"')
            rv = record.get(attr)
            if rv is None:
                return False
            if str(rv).lower() != value.lower():
                return False
        return True

    # --- API methods -------------------------------------------------------
    def list_indexes(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"items": list(self.indices), "nbPages": 1}}

    def get_settings(self, index: str) -> Dict[str, Any]:
        if not self._index_exists(index):
            return {"status": "failed", "output": f"Index {index} not found"}
        for s in self.settings:
            if s["index"] == index:
                return {"status": "ok", "output": {k: v for k, v in s.items() if k != "index"}}
        return {"status": "ok", "output": {
            "searchableAttributes": [],
            "attributesForFaceting": [],
            "hitsPerPage": 20,
            "ranking": [],
        }}

    def query_index(self, index: str, query: str | None = None, filters: str | None = None,
                    hits_per_page: int = 20, page: int = 0) -> Dict[str, Any]:
        if not self._index_exists(index):
            return {"status": "failed", "output": f"Index {index} not found"}
        records = self.records.get(index, [])
        hits = [r for r in records if self._matches_query(r, query) and self._matches_filters(r, filters)]
        nb_hits = len(hits)
        try:
            hits_per_page = max(1, int(hits_per_page))
        except (TypeError, ValueError):
            hits_per_page = 20
        try:
            page = max(0, int(page))
        except (TypeError, ValueError):
            page = 0
        nb_pages = (nb_hits + hits_per_page - 1) // hits_per_page if nb_hits else 0
        start = page * hits_per_page
        page_hits = hits[start: start + hits_per_page]
        return {"status": "ok", "output": {
            "hits": page_hits,
            "nbHits": nb_hits,
            "page": page,
            "nbPages": nb_pages,
            "hitsPerPage": hits_per_page,
            "query": query or "",
            "params": f"query={query or ''}&hitsPerPage={hits_per_page}&page={page}",
        }}

    def get_object(self, index: str, object_id: str) -> Dict[str, Any]:
        if not self._index_exists(index):
            return {"status": "failed", "output": f"Index {index} not found"}
        r = self._get_record(index, object_id)
        if r:
            return {"status": "ok", "output": r}
        return {"status": "failed", "output": f"Object {object_id} not found in index {index}"}

    def add_object(self, index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_index(index)
        record = dict(body or {})
        object_id = record.get("objectID") or self.uuid()
        record["objectID"] = object_id
        rows = self.records.setdefault(index, [])
        cur = self._get_record(index, object_id)
        if cur:
            cur.clear()
            cur.update(record)
        else:
            rows.append(record)
        return {"status": "ok", "output": {"objectID": object_id, "createdAt": "",
                "taskID": _to_int(self.rng.randint(0, 999999))}}

    def update_object(self, index: str, object_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self._index_exists(index):
            return {"status": "failed", "output": f"Index {index} not found"}
        cur = self._get_record(index, object_id)
        if cur:
            merged = {**cur, **(body or {}), "objectID": object_id}
            cur.clear()
            cur.update(merged)
        else:
            record = dict(body or {})
            record["objectID"] = object_id
            self.records.setdefault(index, []).append(record)
        return {"status": "ok", "output": {"objectID": object_id, "updatedAt": "",
                "taskID": _to_int(self.rng.randint(0, 999999))}}

    def delete_object(self, index: str, object_id: str) -> Dict[str, Any]:
        if not self._index_exists(index):
            return {"status": "failed", "output": f"Index {index} not found"}
        rows = self.records.get(index, [])
        for i, r in enumerate(rows):
            if r.get("objectID") == object_id:
                rows.pop(i)
                return {"status": "ok", "output": {"objectID": object_id, "deletedAt": "",
                        "taskID": _to_int(self.rng.randint(0, 999999))}}
        return {"status": "failed", "output": f"Object {object_id} not found in index {index}"}


if __name__ == "__main__":
    s = AlgoliaSession(seed=12)
    print(s.list_indexes())
    print(s.query_index("products", query="wireless"))
