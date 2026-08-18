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


class ServicenowSession:
    """Deterministic sandbox for the ServiceNow Table API mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    # state numeric codes used by the incident table
    INCIDENT_STATES = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed"}

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "servicenow.yaml") as f:
                info = yaml.safe_load(f)

            self.incidents: List[Dict[str, Any]] = list(info.get("incident", []))
            self.changes: List[Dict[str, Any]] = list(info.get("change_request", []))
            self.problems: List[Dict[str, Any]] = list(info.get("problem", []))
            self.users: List[Dict[str, Any]] = [
                {**u, "active": _to_bool(u.get("active", False))} for u in info.get("sys_user", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightServiceNow')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"incidents": self.incidents}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=32))

    def _find(self, rows, sys_id):
        return next((r for r in rows if r["sys_id"] == sys_id), None)

    def _parse_query(self, sysparm_query):
        conditions = []
        if not sysparm_query:
            return conditions
        for clause in sysparm_query.split("^"):
            clause = clause.strip()
            if not clause or "=" not in clause:
                continue
            field, _, value = clause.partition("=")
            conditions.append((field.strip(), value.strip()))
        return conditions

    def _apply_query(self, rows, sysparm_query, sysparm_limit=None):
        conditions = self._parse_query(sysparm_query)
        results = list(rows)
        for field, value in conditions:
            results = [r for r in results if str(r.get(field, "")) == value]
        if sysparm_limit is not None:
            try:
                limit = int(sysparm_limit)
                results = results[:limit]
            except (TypeError, ValueError):
                pass
        return results

    # --- Incidents ---------------------------------------------------------
    def list_incidents(self, sysparm_query: str | None = None,
                       sysparm_limit: int | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._apply_query(self.incidents, sysparm_query, sysparm_limit)}

    def get_incident(self, sys_id: str) -> Dict[str, Any]:
        rec = self._find(self.incidents, sys_id)
        if not rec:
            return {"status": "failed", "output": f"Incident {sys_id} not found"}
        return {"status": "ok", "output": rec}

    def create_incident(self, short_description: str, description: str | None = None,
                        priority: str = "3", impact: str = "3", urgency: str = "3",
                        category: str = "inquiry", assigned_to: str | None = None,
                        opened_by: str | None = None) -> Dict[str, Any]:
        if not short_description:
            return {"status": "failed", "output": "short_description is required"}
        now = self._now()
        seq = 1001 + len(self.incidents)
        rec = {
            "sys_id": self.uuid(),
            "number": f"INC{seq:07d}",
            "short_description": short_description,
            "description": description or "",
            "state": "1",
            "priority": str(priority),
            "impact": str(impact),
            "urgency": str(urgency),
            "category": category or "inquiry",
            "assigned_to": assigned_to or "",
            "opened_by": opened_by or "",
            "opened_at": now,
            "updated_at": now,
        }
        self.incidents.append(rec)
        return {"status": "ok", "output": rec}

    def update_incident(self, sys_id: str, short_description: str | None = None,
                        description: str | None = None, state: str | None = None,
                        priority: str | None = None, impact: str | None = None,
                        urgency: str | None = None, category: str | None = None,
                        assigned_to: str | None = None) -> Dict[str, Any]:
        rec = self._find(self.incidents, sys_id)
        if not rec:
            return {"status": "failed", "output": f"Incident {sys_id} not found"}
        fields = {
            "short_description": short_description,
            "description": description,
            "state": state,
            "priority": priority,
            "impact": impact,
            "urgency": urgency,
            "category": category,
            "assigned_to": assigned_to,
        }
        for key in ("short_description", "description", "state", "priority", "impact",
                    "urgency", "category", "assigned_to"):
            val = fields.get(key)
            if val is not None:
                rec[key] = str(val)
        rec["updated_at"] = self._now()
        return {"status": "ok", "output": rec}

    # --- Change requests ---------------------------------------------------
    def list_change_requests(self, sysparm_query: str | None = None,
                             sysparm_limit: int | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._apply_query(self.changes, sysparm_query, sysparm_limit)}

    def get_change_request(self, sys_id: str) -> Dict[str, Any]:
        rec = self._find(self.changes, sys_id)
        if not rec:
            return {"status": "failed", "output": f"Change request {sys_id} not found"}
        return {"status": "ok", "output": rec}

    # --- Problems ----------------------------------------------------------
    def list_problems(self, sysparm_query: str | None = None,
                      sysparm_limit: int | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._apply_query(self.problems, sysparm_query, sysparm_limit)}

    def get_problem(self, sys_id: str) -> Dict[str, Any]:
        rec = self._find(self.problems, sys_id)
        if not rec:
            return {"status": "failed", "output": f"Problem {sys_id} not found"}
        return {"status": "ok", "output": rec}

    # --- Users -------------------------------------------------------------
    def list_users(self, sysparm_query: str | None = None,
                   sysparm_limit: int | None = None) -> Dict[str, Any]:
        return {"status": "ok", "output": self._apply_query(self.users, sysparm_query, sysparm_limit)}

    def get_user(self, sys_id: str) -> Dict[str, Any]:
        rec = self._find(self.users, sys_id)
        if not rec:
            return {"status": "failed", "output": f"User {sys_id} not found"}
        return {"status": "ok", "output": rec}


if __name__ == "__main__":
    s = ServicenowSession(seed=12)
    print(s.list_incidents())
    print(s.get_user("usr-amelia"))
