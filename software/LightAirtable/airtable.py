import random
import re
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


# Very small filterByFormula support: {Field}='Value' (also "=" with double quotes)
_FORMULA_RE = re.compile(r"^\{(?P<field>[^}]+)\}\s*=\s*(['\"])(?P<value>.*)\2$")


class AirtableSession:
    """Deterministic sandbox for the Airtable mock, ported from the FastAPI service.

    Records are modeled generically as {id, createdTime, fields:{...}}. Field
    value casting is driven by the field type declared in the corpus fields
    table (number -> float/int, checkbox -> bool); everything else stays a string.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "airtable.yaml") as f:
                info = yaml.safe_load(f)

            self.bases: List[Dict[str, Any]] = list(info.get("bases", []))
            self.tables: List[Dict[str, Any]] = list(info.get("tables", []))
            fields_rows: List[Dict[str, Any]] = list(info.get("fields", []))

            self._field_types: Dict[str, Dict[str, str]] = {}
            self._field_meta: Dict[str, List[Dict[str, Any]]] = {}
            for r in fields_rows:
                self._field_types.setdefault(r["tableId"], {})[r["name"]] = r["type"]
                self._field_meta.setdefault(r["tableId"], []).append({
                    "id": r["id"], "name": r["name"], "type": r["type"],
                })

            # one record list per table id (recXXX), coerced from the flat corpus rows
            self.records: Dict[str, List[Dict[str, Any]]] = {}
            for t in self.tables:
                key = t["records_csv"].replace(".json", "")
                self.records[t["id"]] = self._coerce_records(t["id"], info.get(key, []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAirtable')
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
        return "rec" + ''.join(self.rng.choices(alphabet, k=14))

    def _cast_field(self, table_id, name, value):
        ftype = self._field_types.get(table_id, {}).get(name)
        if value == "" or value is None:
            return None if ftype in ("number",) else value
        if ftype == "number":
            try:
                f = float(value)
                return int(f) if f.is_integer() else f
            except (TypeError, ValueError):
                return value
        if ftype == "checkbox":
            return _to_bool(value)
        return value

    def _coerce_records(self, table_id, rows):
        out = []
        for r in rows:
            fields = {}
            for k, v in r.items():
                if k in ("id", "createdTime"):
                    continue
                cast = self._cast_field(table_id, k, v)
                if cast is None:
                    continue
                fields[k] = cast
            out.append({
                "id": r["id"],
                "createdTime": r["createdTime"],
                "fields": fields,
            })
        return out

    def _resolve_table(self, base_id, table_id_or_name):
        for t in self.tables:
            if t["baseId"] != base_id:
                continue
            if t["id"] == table_id_or_name or t["name"].lower() == str(table_id_or_name).lower():
                return t
        return None

    def _apply_formula(self, records, formula):
        if not formula:
            return records
        m = _FORMULA_RE.match(formula.strip())
        if not m:
            return records
        field = m.group("field")
        value = m.group("value")
        out = []
        for rec in records:
            fv = rec["fields"].get(field)
            if fv is None:
                continue
            if str(fv) == value:
                out.append(rec)
        return out

    # --- API methods -------------------------------------------------------
    def list_bases(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"bases": [{
            "id": b["id"], "name": b["name"], "permissionLevel": b["permissionLevel"],
        } for b in self.bases]}}

    def list_tables(self, base_id: str) -> Dict[str, Any]:
        if not any(b["id"] == base_id for b in self.bases):
            return {"status": "failed", "output": f"Base {base_id} not found"}
        tables = []
        for t in self.tables:
            if t["baseId"] != base_id:
                continue
            tables.append({
                "id": t["id"],
                "name": t["name"],
                "primaryFieldId": t["primaryFieldId"],
                "fields": self._field_meta.get(t["id"], []),
            })
        return {"status": "ok", "output": {"tables": tables}}

    def list_records(self, base_id: str, table_id_or_name: str, page_size: int = 100,
                     offset: str | None = None, filter_by_formula: str | None = None) -> Dict[str, Any]:
        table = self._resolve_table(base_id, table_id_or_name)
        if not table:
            return {"status": "failed", "output": f"Table {table_id_or_name} not found in base {base_id}"}
        records = self.records.get(table["id"], [])
        records = self._apply_formula(records, filter_by_formula)

        page_size = max(1, min(int(page_size), 100))
        try:
            start = int(offset) if offset is not None else 0
        except (TypeError, ValueError):
            start = 0
        page = records[start: start + page_size]
        resp = {"records": page}
        next_offset = start + page_size
        if next_offset < len(records):
            resp["offset"] = str(next_offset)
        return {"status": "ok", "output": resp}

    def get_record(self, base_id: str, table_id_or_name: str, record_id: str) -> Dict[str, Any]:
        table = self._resolve_table(base_id, table_id_or_name)
        if not table:
            return {"status": "failed", "output": f"Table {table_id_or_name} not found in base {base_id}"}
        for rec in self.records.get(table["id"], []):
            if rec["id"] == record_id:
                return {"status": "ok", "output": rec}
        return {"status": "failed", "output": f"Record {record_id} not found"}

    def create_records(self, base_id: str, table_id_or_name: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        table = self._resolve_table(base_id, table_id_or_name)
        if not table:
            return {"status": "failed", "output": f"Table {table_id_or_name} not found in base {base_id}"}
        created = []
        rows = self.records.setdefault(table["id"], [])
        for item in records:
            fields = item.get("fields", {}) or {}
            rec = {
                "id": self.uuid(),
                "createdTime": self._now(),
                "fields": dict(fields),
            }
            rows.append(rec)
            created.append(rec)
        return {"status": "ok", "output": {"records": created}}

    def update_record(self, base_id: str, table_id_or_name: str, record_id: str,
                      fields: Dict[str, Any]) -> Dict[str, Any]:
        table = self._resolve_table(base_id, table_id_or_name)
        if not table:
            return {"status": "failed", "output": f"Table {table_id_or_name} not found in base {base_id}"}
        for rec in self.records.get(table["id"], []):
            if rec["id"] == record_id:
                rec["fields"] = {**rec["fields"], **(fields or {})}
                return {"status": "ok", "output": rec}
        return {"status": "failed", "output": f"Record {record_id} not found"}

    def delete_record(self, base_id: str, table_id_or_name: str, record_id: str) -> Dict[str, Any]:
        table = self._resolve_table(base_id, table_id_or_name)
        if not table:
            return {"status": "failed", "output": f"Table {table_id_or_name} not found in base {base_id}"}
        rows = self.records.get(table["id"], [])
        for i, rec in enumerate(rows):
            if rec["id"] == record_id:
                rows.pop(i)
                return {"status": "ok", "output": {"id": record_id, "deleted": True}}
        return {"status": "failed", "output": f"Record {record_id} not found"}


if __name__ == "__main__":
    s = AirtableSession(seed=12)
    print(s.list_bases())
    print(s.list_tables("appNW1studio0001"))
