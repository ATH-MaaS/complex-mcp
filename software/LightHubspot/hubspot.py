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


# Property keys that make up each object's "properties" map.
_CONTACT_PROPS = ["firstname", "lastname", "email", "phone", "jobtitle",
                  "company", "lifecyclestage", "createdate", "lastmodifieddate"]
_COMPANY_PROPS = ["name", "domain", "industry", "city", "state",
                  "numberofemployees", "annualrevenue", "createdate"]
_DEAL_PROPS = ["dealname", "pipeline", "dealstage", "amount", "closedate",
               "dealtype", "createdate", "lastmodifieddate"]


def _strict_int(v) -> int:
    return int(str(v).strip())


def _strict_bool(v) -> bool:
    token = str(v).strip().lower()
    if token in ("true", "1", "yes", "y", "t"):
        return True
    return False


def _opt_float(v, default: float = 0.0) -> float:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


class HubspotSession:
    """Deterministic sandbox for the HubSpot CRM mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    Objects are returned in the HubSpot shape:
    {"id": ..., "properties": {...}, "createdAt": ..., "updatedAt": ..., "archived": ...}.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "hubspot.yaml") as f:
                info = yaml.safe_load(f)

            self.contacts: List[Dict[str, Any]] = self._coerce_objects(info.get("contacts", []), _CONTACT_PROPS)
            self.companies: List[Dict[str, Any]] = self._coerce_objects(info.get("companies", []), _COMPANY_PROPS)
            self.deals: List[Dict[str, Any]] = self._coerce_objects(info.get("deals", []), _DEAL_PROPS, extra=self._deal_extra)
            self.pipelines: List[Dict[str, Any]] = self._coerce_stages(info.get("pipeline_stages", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightHubspot')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"contacts": self.contacts, "companies": self.companies, "deals": self.deals}

    # --- coercion / loaders ------------------------------------------------
    def _coerce_objects(self, rows, prop_keys, extra=None) -> List[Dict[str, Any]]:
        out = []
        for r in rows:
            props = {k: r.get(k, "") for k in prop_keys}
            obj = {
                "id": r["id"],
                "properties": props,
                "createdAt": r.get("createdate") or self._now(),
                "updatedAt": r.get("lastmodifieddate") or r.get("createdate") or self._now(),
                "archived": False,
            }
            if extra:
                extra(r, obj)
            out.append(obj)
        return out

    def _deal_extra(self, r, obj):
        obj["_company"] = r.get("associated_company") or None
        obj["_contact"] = r.get("associated_contact") or None

    def _coerce_stages(self, rows) -> List[Dict[str, Any]]:
        pipelines: Dict[str, Any] = {}
        for r in rows:
            pid = r["pipeline_id"]
            pipelines.setdefault(pid, {
                "id": pid,
                "label": r["pipeline_label"],
                "displayOrder": 0,
                "stages": [],
            })
            pipelines[pid]["stages"].append({
                "id": r["stage_id"],
                "label": r["stage_label"],
                "displayOrder": _strict_int(r["display_order"]),
                "metadata": {"isClosed": str(_strict_bool(r["closed"])).lower(),
                             "probability": str(_opt_float(r.get("probability"), default=0.0))},
            })
        return list(pipelines.values())

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        return str(self.rng.getrandbits(64) % 10**12)

    def _public(self, obj):
        return {k: v for k, v in obj.items() if not k.startswith("_")}

    def _paginate(self, items, limit, after):
        try:
            offset = int(after) if after else 0
        except (TypeError, ValueError):
            offset = 0
        limit = max(1, min(int(limit), 100))
        page = items[offset: offset + limit]
        body = {"results": [self._public(o) for o in page]}
        if offset + limit < len(items):
            body["paging"] = {"next": {"after": str(offset + limit)}}
        return body

    def _find(self, store, obj_id):
        return next((o for o in store if o["id"] == str(obj_id)), None)

    def _valid_stage(self, pipeline_id, stage_id):
        pipe = next((p for p in self.pipelines if p["id"] == pipeline_id), None)
        if not pipe:
            return False
        return any(s["id"] == stage_id for s in pipe["stages"])

    # --- Contacts ----------------------------------------------------------
    def list_contacts(self, limit: int = 10, after: str | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._paginate(self.contacts, limit, after)}

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        c = self._find(self.contacts, contact_id)
        if not c:
            return {"status": "failed", "output": f"Contact {contact_id} not found"}
        return {"status": "ok", "output": self._public(c)}

    def create_contact(self, properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = self._now()
        props = {k: "" for k in _CONTACT_PROPS}
        props.update({k: v for k, v in (properties or {}).items()})
        props["createdate"] = now
        props["lastmodifieddate"] = now
        contact = {
            "id": self.uuid(),
            "properties": props,
            "createdAt": now,
            "updatedAt": now,
            "archived": False,
        }
        self.contacts.append(contact)
        return {"status": "ok", "output": self._public(contact)}

    def update_contact(self, contact_id: str, properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        c = self._find(self.contacts, contact_id)
        if not c:
            return {"status": "failed", "output": f"Contact {contact_id} not found"}
        c["properties"].update({k: v for k, v in (properties or {}).items()})
        c["properties"]["lastmodifieddate"] = self._now()
        c["updatedAt"] = self._now()
        return {"status": "ok", "output": self._public(c)}

    # --- Companies ---------------------------------------------------------
    def list_companies(self, limit: int = 10, after: str | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._paginate(self.companies, limit, after)}

    def get_company(self, company_id: str) -> Dict[str, Any]:
        c = self._find(self.companies, company_id)
        if not c:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        return {"status": "ok", "output": self._public(c)}

    # --- Deals -------------------------------------------------------------
    def list_deals(self, limit: int = 10, after: str | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._paginate(self.deals, limit, after)}

    def get_deal(self, deal_id: str) -> Dict[str, Any]:
        d = self._find(self.deals, deal_id)
        if not d:
            return {"status": "failed", "output": f"Deal {deal_id} not found"}
        return {"status": "ok", "output": self._public(d)}

    def create_deal(self, properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = self._now()
        props = {k: "" for k in _DEAL_PROPS}
        props.update({k: v for k, v in (properties or {}).items()})
        props.setdefault("pipeline", "default")
        if not props.get("dealstage"):
            props["dealstage"] = "appointmentscheduled"
        props["createdate"] = now
        props["lastmodifieddate"] = now
        deal = {
            "id": self.uuid(),
            "properties": props,
            "createdAt": now,
            "updatedAt": now,
            "archived": False,
            "_company": None,
            "_contact": None,
        }
        self.deals.append(deal)
        return {"status": "ok", "output": self._public(deal)}

    def update_deal(self, deal_id: str, properties: Dict[str, Any] | None = None) -> Dict[str, Any]:
        d = self._find(self.deals, deal_id)
        if not d:
            return {"status": "failed", "output": f"Deal {deal_id} not found"}
        props = properties or {}
        if "dealstage" in props:
            pipeline_id = props.get("pipeline", d["properties"].get("pipeline", "default"))
            if not self._valid_stage(pipeline_id, props["dealstage"]):
                return {"status": "failed",
                        "output": f"Invalid stage {props['dealstage']} for pipeline {pipeline_id}"}
        d["properties"].update(props)
        d["properties"]["lastmodifieddate"] = self._now()
        d["updatedAt"] = self._now()
        return {"status": "ok", "output": self._public(d)}

    # --- Pipelines ---------------------------------------------------------
    def list_deal_pipelines(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"results": [dict(p) for p in self.pipelines]}}


if __name__ == "__main__":
    s = HubspotSession(seed=12)
    print(s.list_contacts())
    print(s.list_deal_pipelines())
