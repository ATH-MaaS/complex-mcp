import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import re
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


_NUMERIC_FIELDS = {
    "AnnualRevenue", "NumberOfEmployees", "Amount", "Probability",
}

_SOBJECT_TABLE = {
    "Account": "accounts",
    "Contact": "contacts",
    "Lead": "leads",
    "Opportunity": "opportunities",
}

_ID_PREFIX = {
    "Account": "001",
    "Contact": "003",
    "Lead": "00Q",
    "Opportunity": "006",
}

_SOQL_RE = re.compile(
    r"^\s*SELECT\s+(?P<fields>.+?)\s+FROM\s+(?P<object>\w+)"
    r"(?:\s+WHERE\s+(?P<field>\w+)\s*=\s*'(?P<value>[^']*)')?\s*$",
    re.IGNORECASE | re.DOTALL,
)


class SalesforceSession:
    """Deterministic sandbox for the Salesforce mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "salesforce.yaml") as f:
                info = yaml.safe_load(f)

            # Tables keyed by canonical sObject name; rows coerced like the source _coerce().
            self.tables: Dict[str, List[Dict[str, Any]]] = {}
            for sobject, table in _SOBJECT_TABLE.items():
                self.tables[sobject] = [
                    self._coerce_row(dict(r), sobject) for r in info.get(table, [])
                ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSalesforce')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"tables": self.tables}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789ABCDEF"
        return ''.join(self.rng.choices(alphabet, k=15))

    def _coerce_row(self, rec: Dict[str, Any], sobject: str) -> Dict[str, Any]:
        for k, v in list(rec.items()):
            if k in _NUMERIC_FIELDS and v not in (None, ""):
                try:
                    rec[k] = float(v) if "." in str(v) else int(v)
                except (TypeError, ValueError):
                    pass
            elif v == "":
                rec[k] = None
        rec["attributes"] = {
            "type": sobject,
            "url": f"/services/data/v59.0/sobjects/{sobject}/{rec['Id']}",
        }
        return rec

    def _canonical(self, sobject):
        if not sobject:
            return None
        for name in _SOBJECT_TABLE:
            if name.lower() == sobject.lower():
                return name
        return None

    def _new_id(self, sobject) -> str:
        prefix = _ID_PREFIX.get(sobject, "0XX")
        return f"{prefix}{self.uuid().upper()}"[:18]

    def _records(self, sobject):
        return self.tables[sobject]

    def _find(self, sobject, record_id):
        for r in self.tables[sobject]:
            if r.get("Id") == record_id:
                return r
        return None

    # --- API methods -------------------------------------------------------
    def list_records(self, sobject: str, limit: int = 200) -> Dict[str, Any]:
        name = self._canonical(sobject)
        if not name:
            return {"status": "failed", "output": f"sObject type '{sobject}' is not supported"}
        records = self._records(name)[:limit]
        return {"status": "ok", "output": {
            "totalSize": len(records),
            "done": True,
            "records": records,
        }}

    def get_record(self, sobject: str, record_id: str) -> Dict[str, Any]:
        name = self._canonical(sobject)
        if not name:
            return {"status": "failed", "output": f"sObject type '{sobject}' is not supported"}
        rec = self._find(name, record_id)
        if not rec:
            return {"status": "failed", "output": f"Provided external ID field does not exist or is not accessible: {record_id}"}
        return {"status": "ok", "output": rec}

    def create_record(self, sobject: str, fields: Dict[str, Any] | None = None) -> Dict[str, Any]:
        name = self._canonical(sobject)
        if not name:
            return {"status": "failed", "output": f"sObject type '{sobject}' is not supported"}
        rec_id = self._new_id(name)
        record = {"Id": rec_id}
        for k, v in (fields or {}).items():
            if k == "Id":
                continue
            record[k] = v
        record["attributes"] = {
            "type": name,
            "url": f"/services/data/v59.0/sobjects/{name}/{rec_id}",
        }
        record.setdefault("CreatedDate", self._now())
        self.tables[name].append(record)
        return {"status": "ok", "output": {"id": rec_id, "success": True, "errors": []}}

    def update_record(self, sobject: str, record_id: str, fields: Dict[str, Any] | None = None) -> Dict[str, Any]:
        name = self._canonical(sobject)
        if not name:
            return {"status": "failed", "output": f"sObject type '{sobject}' is not supported"}
        rec = self._find(name, record_id)
        if not rec:
            return {"status": "failed", "output": f"Provided external ID field does not exist or is not accessible: {record_id}"}
        for k, v in (fields or {}).items():
            if k in ("Id", "attributes"):
                continue
            rec[k] = v
        rec["LastModifiedDate"] = self._now()
        return {"status": "ok", "output": {"updated": True, "id": record_id}}

    def soql_query(self, q: str) -> Dict[str, Any]:
        if not q:
            return {"status": "failed", "output": "MALFORMED_QUERY: empty query string"}
        m = _SOQL_RE.match(q.strip())
        if not m:
            return {"status": "failed", "output": f"MALFORMED_QUERY: unable to parse '{q}'"}
        name = self._canonical(m.group("object"))
        if not name:
            return {"status": "failed", "output": f"INVALID_TYPE: sObject type '{m.group('object')}' is not supported"}

        raw_fields = m.group("fields").strip()
        if raw_fields == "*" or raw_fields.upper() == "FIELDS(ALL)":
            fields = None
        else:
            fields = [f.strip() for f in raw_fields.split(",") if f.strip()]

        records = self._records(name)
        where_field = m.group("field")
        where_value = m.group("value")
        if where_field:
            def _match(rec):
                actual = rec.get(where_field)
                return str(actual) == where_value
            records = [r for r in records if _match(r)]

        results = []
        for rec in records:
            if fields is None:
                results.append(rec)
            else:
                projected = {"attributes": rec["attributes"]}
                for f in fields:
                    projected[f] = rec.get(f)
                results.append(projected)

        return {"status": "ok", "output": {
            "totalSize": len(results),
            "done": True,
            "records": results,
        }}


if __name__ == "__main__":
    s = SalesforceSession(seed=12)
    print(s.list_records("Account"))
    print(s.soql_query("SELECT Name, Industry FROM Account WHERE Industry = 'Retail'"))
