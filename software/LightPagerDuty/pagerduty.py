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


def _strict_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _opt_str(v):
    s = "" if v is None else str(v)
    return s or None


class PagerDutySession:
    """Deterministic sandbox for the PagerDuty mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    VALID_STATUSES = {"triggered", "acknowledged", "resolved"}

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "pagerduty.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = list(info.get("users", []))
            self.services: List[Dict[str, Any]] = [
                {**s, "auto_resolve_timeout": _strict_int(s.get("auto_resolve_timeout"))}
                for s in info.get("services", [])
            ]
            self.incidents: List[Dict[str, Any]] = [
                {
                    **i,
                    "incident_number": _strict_int(i.get("incident_number")),
                    "assigned_to": _opt_str(i.get("assigned_to")),
                    "resolved_at": _opt_str(i.get("resolved_at")),
                }
                for i in info.get("incidents", [])
            ]
            self.policies: List[Dict[str, Any]] = [
                {**p, "num_loops": _strict_int(p.get("num_loops"))}
                for p in info.get("escalation_policies", [])
            ]
            self.schedules: List[Dict[str, Any]] = list(info.get("schedules", []))

            self.notes_store: Dict[str, List[Dict[str, Any]]] = {}
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPagerDuty')
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
        return ''.join(self.rng.choices(alphabet, k=10))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _get_user(self, user_id):
        return next((u for u in self.users if u["user_id"] == user_id), None)

    # --- Users -------------------------------------------------------------
    def list_users(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"users": list(self.users)}}

    # --- Services ----------------------------------------------------------
    def list_services(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"services": list(self.services)}}

    def get_service(self, service_id: str) -> Dict[str, Any]:
        for s in self.services:
            if s["service_id"] == service_id:
                return {"status": "ok", "output": s}
        return {"status": "failed", "output": f"Service {service_id} not found"}

    # --- Incidents ---------------------------------------------------------
    def list_incidents(self, statuses: List[str] | None = None, service_id: str | None = None,
                       urgency: str | None = None) -> Dict[str, Any]:
        results = list(self.incidents)
        if statuses:
            wanted = {s.lower() for s in statuses}
            results = [i for i in results if i["status"].lower() in wanted]
        if service_id:
            results = [i for i in results if i["service_id"] == service_id]
        if urgency:
            results = [i for i in results if i["urgency"].lower() == urgency.lower()]
        results.sort(key=lambda i: i["created_at"], reverse=True)
        return {"status": "ok", "output": {"incidents": results, "total": len(results)}}

    def get_incident(self, incident_id: str) -> Dict[str, Any]:
        for i in self.incidents:
            if i["incident_id"] == incident_id:
                return {"status": "ok", "output": i}
        return {"status": "failed", "output": f"Incident {incident_id} not found"}

    def create_incident(self, title: str, service_id: str, urgency: str = "high",
                        assigned_to: str | None = None) -> Dict[str, Any]:
        service = next((s for s in self.services if s["service_id"] == service_id), None)
        if not service:
            return {"status": "failed", "output": f"Service {service_id} not found"}
        if assigned_to and not self._get_user(assigned_to):
            return {"status": "failed", "output": f"User {assigned_to} not found"}
        incident_number = max((i["incident_number"] for i in self.incidents), default=1000) + 1
        incident = {
            "incident_id": self._new_id("PI"),
            "incident_number": incident_number,
            "title": title,
            "status": "triggered",
            "urgency": urgency,
            "service_id": service_id,
            "escalation_policy_id": service["escalation_policy_id"],
            "assigned_to": assigned_to,
            "created_at": self._now(),
            "resolved_at": None,
        }
        self.incidents.append(incident)
        return {"status": "ok", "output": incident}

    def update_incident(self, incident_id: str, status: str | None = None,
                        assigned_to: str | None = None) -> Dict[str, Any]:
        for i, inc in enumerate(self.incidents):
            if inc["incident_id"] == incident_id:
                if status is not None:
                    if status.lower() not in self.VALID_STATUSES:
                        return {"status": "failed", "output": f"Invalid status '{status}'"}
                    self.incidents[i]["status"] = status.lower()
                    if status.lower() == "resolved":
                        self.incidents[i]["resolved_at"] = self._now()
                    else:
                        self.incidents[i]["resolved_at"] = None
                if assigned_to is not None:
                    if not self._get_user(assigned_to):
                        return {"status": "failed", "output": f"User {assigned_to} not found"}
                    self.incidents[i]["assigned_to"] = assigned_to
                return {"status": "ok", "output": self.incidents[i]}
        return {"status": "failed", "output": f"Incident {incident_id} not found"}

    # --- Notes -------------------------------------------------------------
    def list_notes(self, incident_id: str) -> Dict[str, Any]:
        if not any(i["incident_id"] == incident_id for i in self.incidents):
            return {"status": "failed", "output": f"Incident {incident_id} not found"}
        return {"status": "ok", "output": {"notes": self.notes_store.get(incident_id, [])}}

    def create_note(self, incident_id: str, content: str, user_id: str | None = None) -> Dict[str, Any]:
        if not any(i["incident_id"] == incident_id for i in self.incidents):
            return {"status": "failed", "output": f"Incident {incident_id} not found"}
        note = {
            "note_id": self._new_id("NOTE"),
            "incident_id": incident_id,
            "content": content,
            "user_id": user_id,
            "created_at": self._now(),
        }
        self.notes_store.setdefault(incident_id, []).append(note)
        return {"status": "ok", "output": note}

    # --- On-call / schedules / escalation policies -------------------------
    def list_oncalls(self, escalation_policy_id: str | None = None) -> Dict[str, Any]:
        results = []
        for sch in self.schedules:
            if escalation_policy_id and sch["escalation_policy_id"] != escalation_policy_id:
                continue
            user = self._get_user(sch["current_oncall_user_id"])
            results.append({
                "schedule_id": sch["schedule_id"],
                "schedule_name": sch["name"],
                "escalation_policy_id": sch["escalation_policy_id"],
                "user": {"user_id": user["user_id"], "name": user["name"]} if user else None,
                "start": sch["oncall_start"],
                "end": sch["oncall_end"],
            })
        return {"status": "ok", "output": {"oncalls": results}}

    def list_schedules(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"schedules": list(self.schedules)}}

    def list_escalation_policies(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"escalation_policies": list(self.policies)}}


if __name__ == "__main__":
    s = PagerDutySession(seed=12)
    print(s.list_services())
    print(s.list_incidents())
