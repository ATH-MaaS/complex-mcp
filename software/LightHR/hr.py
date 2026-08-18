from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


EMPLOYEE_STATUSES = ("active", "terminated")
LEAVE_TYPES = ("vacation", "sick", "personal")
LEAVE_STATUSES = ("pending", "approved", "rejected")

SEED_EMPLOYEES = [
    ("Alice Chen",   "alice@company.com",  "Engineering", "Staff Engineer", "2022-03-15", None,   "active"),
    ("Bob Rivera",   "bob@company.com",    "Engineering", "Senior Engineer","2023-07-01", 0,      "active"),
    ("Carol Wu",     "carol@company.com",  "Product",     "Product Manager","2021-11-20", None,   "active"),
    ("Dan Patel",    "dan@company.com",    "Sales",       "AE",             "2024-02-10", None,   "active"),
    ("Eve Nakamura", "eve@company.com",    "Sales",       "SDR",            "2024-09-05", 3,      "active"),
]

SEED_LEAVES = [
    (0, "vacation", -20, -18, 3.0, "approved",  "Winter break."),
    (1, "sick",       1,   1, 1.0, "pending",   "Flu."),
    (3, "personal",   6,   6, 1.0, "pending",   "Family event."),
]

SEED_TIMESHEETS = [
    (0,  0, 8.0, "MCP-Bench",  "Ran full benchmark suite."),
    (0,  1, 7.5, "MCP-Bench",  "Analysis of results."),
    (1,  0, 8.0, "LightCRM",   "Backend endpoints."),
    (1,  1, 6.0, "LightCRM",   "Bug fixes."),
    (2,  0, 8.0, "Roadmap",    "Q1 planning doc."),
    (2,  1, 4.0, "Roadmap",    "Stakeholder review."),
    (3,  0, 8.0, "Sales-Ops",  "Prospect outreach."),
    (4,  0, 6.0, "Sales-Ops",  "SDR call blitz."),
]


@dataclass
class Employee:
    eid: str
    name: str
    email: str
    department: str
    role: str
    hire_date: str
    manager_id: Optional[str] = None
    status: str = "active"


@dataclass
class Leave:
    lid: str
    employee_id: str
    type: str
    start_date: str
    end_date: str
    days: float
    status: str = "pending"
    reason: str = ""


@dataclass
class TimeEntry:
    teid: str
    employee_id: str
    date: str
    hours: float
    project: str
    description: str = ""


class HRSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"],
            ) if os_cfg else DummyOSConnector()
            self.employees: Dict[str, Employee] = {}
            self.leaves: Dict[str, Leave] = {}
            self.timesheets: Dict[str, TimeEntry] = {}
            self._today = datetime(2026, 1, 5)
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightHR')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self) -> None:
        employee_ids: List[str] = []
        for name, email, dept, role, hire_date, mgr_idx, status in SEED_EMPLOYEES:
            e = Employee(
                eid=self.uuid(),
                name=name,
                email=email,
                department=dept,
                role=role,
                hire_date=hire_date,
                manager_id=None,
                status=status,
            )
            self.employees[e.eid] = e
            employee_ids.append(e.eid)
        for i, (_, _, _, _, _, mgr_idx, _) in enumerate(SEED_EMPLOYEES):
            if mgr_idx is not None:
                self.employees[employee_ids[i]].manager_id = employee_ids[mgr_idx]

        for emp_idx, ltype, start_off, end_off, days, status, reason in SEED_LEAVES:
            start = (self._today + timedelta(days=start_off)).date().isoformat()
            end = (self._today + timedelta(days=end_off)).date().isoformat()
            l = Leave(
                lid=self.uuid(),
                employee_id=employee_ids[emp_idx],
                type=ltype,
                start_date=start,
                end_date=end,
                days=days,
                status=status,
                reason=reason,
            )
            self.leaves[l.lid] = l

        for emp_idx, day_off, hours, project, desc in SEED_TIMESHEETS:
            date = (self._today + timedelta(days=day_off)).date().isoformat()
            te = TimeEntry(
                teid=self.uuid(),
                employee_id=employee_ids[emp_idx],
                date=date,
                hours=hours,
                project=project,
                description=desc,
            )
            self.timesheets[te.teid] = te

    def get_session_dict(self) -> Dict:
        return {
            "employees": {eid: asdict(e) for eid, e in self.employees.items()},
            "leaves": {lid: asdict(l) for lid, l in self.leaves.items()},
            "timesheets": {teid: asdict(t) for teid, t in self.timesheets.items()},
        }

    def _emp_summary(self, e: Employee) -> Dict:
        return {
            "eid": e.eid,
            "name": e.name,
            "email": e.email,
            "department": e.department,
            "role": e.role,
            "status": e.status,
        }

    def _leave_summary(self, l: Leave) -> Dict:
        return {
            "lid": l.lid,
            "employee_id": l.employee_id,
            "type": l.type,
            "start_date": l.start_date,
            "end_date": l.end_date,
            "days": l.days,
            "status": l.status,
        }

    def _time_summary(self, t: TimeEntry) -> Dict:
        return {
            "teid": t.teid,
            "employee_id": t.employee_id,
            "date": t.date,
            "hours": t.hours,
            "project": t.project,
        }

    def list_employees(self, department: Optional[str] = None) -> Dict:
        items = list(self.employees.values())
        if department:
            items = [e for e in items if e.department == department]
        items.sort(key=lambda e: e.name.lower())
        return {"status": "ok", "output": [self._emp_summary(e) for e in items]}

    def get_employee(self, eid: str) -> Dict:
        e = self.employees.get(eid)
        if not e:
            return {"status": "failed", "output": f"employee {eid} not found"}
        return {"status": "ok", "output": asdict(e)}

    def create_employee(self, name: str, email: str,
                        department: str, role: str,
                        hire_date: str = "",
                        manager_id: Optional[str] = None) -> Dict:
        if manager_id is not None and manager_id not in self.employees:
            return {"status": "failed", "output": f"manager {manager_id} not found"}
        e = Employee(
            eid=self.uuid(),
            name=name,
            email=email,
            department=department,
            role=role,
            hire_date=hire_date,
            manager_id=manager_id,
            status="active",
        )
        self.employees[e.eid] = e
        return {"status": "ok", "output": self._emp_summary(e)}

    def update_employee(self, eid: str,
                        name: Optional[str] = None,
                        email: Optional[str] = None,
                        department: Optional[str] = None,
                        role: Optional[str] = None,
                        hire_date: Optional[str] = None,
                        manager_id: Optional[str] = None) -> Dict:
        e = self.employees.get(eid)
        if not e:
            return {"status": "failed", "output": f"employee {eid} not found"}
        if manager_id is not None and manager_id != "" and manager_id not in self.employees:
            return {"status": "failed", "output": f"manager {manager_id} not found"}
        for k, v in {
            "name": name, "email": email, "department": department,
            "role": role, "hire_date": hire_date, "manager_id": manager_id,
        }.items():
            if v is not None:
                setattr(e, k, v)
        return {"status": "ok", "output": self._emp_summary(e)}

    def terminate_employee(self, eid: str) -> Dict:
        e = self.employees.get(eid)
        if not e:
            return {"status": "failed", "output": f"employee {eid} not found"}
        e.status = "terminated"
        return {"status": "ok", "output": self._emp_summary(e)}

    def list_leaves(self, employee_id: Optional[str] = None,
                    status: Optional[str] = None) -> Dict:
        items = list(self.leaves.values())
        if employee_id:
            items = [l for l in items if l.employee_id == employee_id]
        if status:
            if status not in LEAVE_STATUSES:
                return {"status": "failed", "output": f"status must be one of {LEAVE_STATUSES}"}
            items = [l for l in items if l.status == status]
        items.sort(key=lambda l: l.start_date)
        return {"status": "ok", "output": [self._leave_summary(l) for l in items]}

    def request_leave(self, employee_id: str, type: str,
                      start_date: str, end_date: str,
                      days: float, reason: str = "") -> Dict:
        if employee_id not in self.employees:
            return {"status": "failed", "output": f"employee {employee_id} not found"}
        if type not in LEAVE_TYPES:
            return {"status": "failed", "output": f"type must be one of {LEAVE_TYPES}"}
        l = Leave(
            lid=self.uuid(),
            employee_id=employee_id,
            type=type,
            start_date=start_date,
            end_date=end_date,
            days=days,
            status="pending",
            reason=reason,
        )
        self.leaves[l.lid] = l
        return {"status": "ok", "output": self._leave_summary(l)}

    def approve_leave(self, lid: str) -> Dict:
        l = self.leaves.get(lid)
        if not l:
            return {"status": "failed", "output": f"leave {lid} not found"}
        l.status = "approved"
        return {"status": "ok", "output": self._leave_summary(l)}

    def reject_leave(self, lid: str) -> Dict:
        l = self.leaves.get(lid)
        if not l:
            return {"status": "failed", "output": f"leave {lid} not found"}
        l.status = "rejected"
        return {"status": "ok", "output": self._leave_summary(l)}

    def list_pending_leaves(self) -> Dict:
        items = [l for l in self.leaves.values() if l.status == "pending"]
        items.sort(key=lambda l: l.start_date)
        return {"status": "ok", "output": [self._leave_summary(l) for l in items]}

    def list_timesheets(self, employee_id: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> Dict:
        items = list(self.timesheets.values())
        if employee_id:
            items = [t for t in items if t.employee_id == employee_id]
        if start_date:
            items = [t for t in items if t.date >= start_date]
        if end_date:
            items = [t for t in items if t.date <= end_date]
        items.sort(key=lambda t: (t.date, t.employee_id))
        return {"status": "ok", "output": [self._time_summary(t) for t in items]}

    def log_time(self, employee_id: str, date: str, hours: float,
                 project: str, description: str = "") -> Dict:
        if employee_id not in self.employees:
            return {"status": "failed", "output": f"employee {employee_id} not found"}
        if hours <= 0:
            return {"status": "failed", "output": "hours must be positive"}
        te = TimeEntry(
            teid=self.uuid(),
            employee_id=employee_id,
            date=date,
            hours=hours,
            project=project,
            description=description,
        )
        self.timesheets[te.teid] = te
        return {"status": "ok", "output": self._time_summary(te)}

    def delete_time_entry(self, teid: str) -> Dict:
        t = self.timesheets.pop(teid, None)
        if not t:
            return {"status": "failed", "output": f"time entry {teid} not found"}
        return {"status": "ok", "output": {"teid": teid, "deleted": True}}

    def get_employee_hours(self, employee_id: str,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> Dict:
        if employee_id not in self.employees:
            return {"status": "failed", "output": f"employee {employee_id} not found"}
        total = 0.0
        by_project: Dict[str, float] = {}
        for t in self.timesheets.values():
            if t.employee_id != employee_id:
                continue
            if start_date and t.date < start_date:
                continue
            if end_date and t.date > end_date:
                continue
            total += float(t.hours)
            by_project[t.project] = by_project.get(t.project, 0.0) + float(t.hours)
        return {
            "status": "ok",
            "output": {
                "employee_id": employee_id,
                "total_hours": total,
                "by_project": by_project,
            },
        }

    def list_by_department(self, department: str) -> Dict:
        items = [e for e in self.employees.values() if e.department == department]
        items.sort(key=lambda e: e.name.lower())
        return {"status": "ok", "output": [self._emp_summary(e) for e in items]}

    def get_stats(self) -> Dict:
        by_department: Dict[str, int] = {}
        active = 0
        terminated = 0
        for e in self.employees.values():
            by_department[e.department] = by_department.get(e.department, 0) + 1
            if e.status == "active":
                active += 1
            else:
                terminated += 1
        leave_by_status: Dict[str, int] = {s: 0 for s in LEAVE_STATUSES}
        for l in self.leaves.values():
            leave_by_status[l.status] = leave_by_status.get(l.status, 0) + 1
        total_hours = sum(float(t.hours) for t in self.timesheets.values())
        return {
            "status": "ok",
            "output": {
                "employees": len(self.employees),
                "active": active,
                "terminated": terminated,
                "by_department": by_department,
                "leaves": len(self.leaves),
                "leave_by_status": leave_by_status,
                "time_entries": len(self.timesheets),
                "total_hours": total_hours,
            },
        }
