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

VALID_TIME_OFF_STATUS = {"requested", "approved", "denied", "canceled"}


def _to_int(v, default=0) -> int:
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class BamboohrSession:
    """Deterministic sandbox for the BambooHR mock, ported from the FastAPI service.

    Covers employees, time-off requests, who's-out, company info and a synthetic
    headcount report. State is loaded from the corpus at init; mutations persist in
    the in-memory tables within the session.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "bamboohr.yaml") as f:
                info = yaml.safe_load(f)

            self.employees: List[Dict[str, Any]] = [
                {**e, "supervisorId": (str(e.get("supervisorId", "")).strip() or None)}
                for e in info.get("employees", [])
            ]
            self.time_off: List[Dict[str, Any]] = [
                {**t, "amount": _to_int(t.get("amount"), 0)} for t in info.get("time_off", [])
            ]
            self.whos_out: List[Dict[str, Any]] = list(info.get("whos_out", []))
            self.company: Dict[str, Any] = dict(info.get("company", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightBambooHR')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"employees": self.employees, "time_off": self.time_off}

    # --- helpers -----------------------------------------------------------
    def _now_date(self) -> str:
        return self.os.now()[:10]

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{''.join(self.rng.choices('0123456789abcdef', k=8))}"

    def _find(self, rows, obj_id):
        return next((x for x in rows if x["id"] == obj_id), None)

    # --- Company -----------------------------------------------------------
    def get_company(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.company}

    # --- Employees ---------------------------------------------------------
    def employees_directory(self) -> Dict[str, Any]:
        fields = ["id", "firstName", "lastName", "workEmail", "department",
                  "jobTitle", "location", "hireDate", "status", "supervisorId"]
        employees = [{k: e.get(k) for k in fields} for e in self.employees]
        return {"status": "ok", "output": {"employees": employees}}

    def get_employee(self, employee_id: str) -> Dict[str, Any]:
        e = self._find(self.employees, employee_id)
        if not e:
            return {"status": "failed", "output": f"Employee {employee_id} not found"}
        return {"status": "ok", "output": e}

    def create_employee(self, firstName: str, lastName: str, workEmail: str | None = None,
                        department: str | None = None, jobTitle: str | None = None,
                        location: str | None = None, hireDate: str | None = None,
                        supervisorId: str | None = None) -> Dict[str, Any]:
        if not firstName or not lastName:
            return {"status": "failed", "output": "firstName and lastName are required"}
        emp = {
            "id": self._new_id("emp"),
            "firstName": firstName,
            "lastName": lastName,
            "workEmail": workEmail or "",
            "department": department or "",
            "jobTitle": jobTitle or "",
            "location": location or "",
            "hireDate": hireDate or self._now_date(),
            "status": "Active",
            "supervisorId": supervisorId or None,
        }
        self.employees.append(emp)
        return {"status": "ok", "output": emp}

    # --- Time-off requests -------------------------------------------------
    def list_time_off_requests(self, status: str | None = None,
                               employeeId: str | None = None) -> Dict[str, Any]:
        results = list(self.time_off)
        if status:
            results = [r for r in results if r["status"] == status]
        if employeeId:
            results = [r for r in results if r["employeeId"] == employeeId]
        return {"status": "ok", "output": results}

    def create_time_off_request(self, employeeId: str, start: str, end: str,
                                type: str = "Vacation", amount: int = 1,
                                unit: str = "days", notes: str | None = None) -> Dict[str, Any]:
        if not self._find(self.employees, employeeId):
            return {"status": "failed", "output": f"Employee {employeeId} not found"}
        req = {
            "id": self._new_id("tor"),
            "employeeId": employeeId,
            "type": type or "Vacation",
            "status": "requested",
            "start": start,
            "end": end,
            "amount": _to_int(amount, 1),
            "unit": unit or "days",
            "notes": notes or "",
            "created": self._now_date(),
        }
        self.time_off.append(req)
        return {"status": "ok", "output": req}

    def update_time_off_status(self, request_id: str, status: str) -> Dict[str, Any]:
        req = self._find(self.time_off, request_id)
        if not req:
            return {"status": "failed", "output": f"Time-off request {request_id} not found"}
        if status not in VALID_TIME_OFF_STATUS:
            return {"status": "failed", "output": f"Invalid status: {status}"}
        req["status"] = status
        return {"status": "ok", "output": req}

    def whos_out(self, start: str | None = None, end: str | None = None) -> Dict[str, Any]:
        results = list(self.whos_out)
        if start:
            results = [r for r in results if r["end"] >= start]
        if end:
            results = [r for r in results if r["start"] <= end]
        return {"status": "ok", "output": results}

    # --- Reports -----------------------------------------------------------
    def get_report(self, report_id: str) -> Dict[str, Any]:
        if str(report_id) == "1":
            by_dept: Dict[str, int] = {}
            for e in self.employees:
                if e.get("status") == "Active":
                    by_dept[e["department"]] = by_dept.get(e["department"], 0) + 1
            rows = [{"department": d, "headcount": c} for d, c in sorted(by_dept.items())]
            return {"status": "ok", "output": {
                "title": "Headcount by Department",
                "fields": [{"id": "department", "name": "Department"},
                           {"id": "headcount", "name": "Headcount"}],
                "employees": rows,
            }}
        return {"status": "failed", "output": f"Report {report_id} not found"}


if __name__ == "__main__":
    s = BamboohrSession(seed=12)
    print(s.get_company())
    print(s.employees_directory())
