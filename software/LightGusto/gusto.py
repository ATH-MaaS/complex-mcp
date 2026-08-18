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
    return str(v).strip().lower() in ("true", "1", "yes")


def _opt_float(v, default: float = 0.0) -> float:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_int(v, default: int = 0) -> int:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


class GustoSession:
    """Deterministic sandbox for the Gusto Payroll mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "gusto.yaml") as f:
                info = yaml.safe_load(f)

            self.company: Dict[str, Any] = dict(info.get("company", {}))

            self.employees: List[Dict[str, Any]] = [
                {
                    **e,
                    "rate": _opt_float(e.get("rate"), default=0.0),
                    "terminated": _to_bool(e.get("terminated", False)),
                }
                for e in info.get("employees", [])
            ]

            self.compensations: List[Dict[str, Any]] = [
                {
                    **c,
                    "rate": _opt_float(c.get("rate"), default=0.0),
                }
                for c in info.get("compensations", [])
            ]

            self.payrolls: List[Dict[str, Any]] = [
                {
                    **p,
                    "processed": _to_bool(p.get("processed", False)),
                    "gross_pay": _opt_float(p.get("gross_pay"), default=0.0),
                    "net_pay": _opt_float(p.get("net_pay"), default=0.0),
                    "employee_count": _opt_int(p.get("employee_count"), default=0),
                }
                for p in info.get("payrolls", [])
            ]

            self.contractors: List[Dict[str, Any]] = [
                {
                    **c,
                    "hourly_rate": _opt_float(c.get("hourly_rate"), default=0.0),
                }
                for c in info.get("contractors", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGusto')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"payrolls": self.payrolls}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _find(self, rows, obj_id):
        return next((x for x in rows if x["id"] == obj_id), None)

    def _comp_for(self, employee_id):
        return next((c for c in self.compensations if c["employee_id"] == employee_id), None)

    # --- Company -----------------------------------------------------------
    def get_company(self, company_id: str) -> Dict[str, Any]:
        if company_id != self.company["id"]:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        return {"status": "ok", "output": self.company}

    # --- Employees / compensations -----------------------------------------
    def list_company_employees(self, company_id: str) -> Dict[str, Any]:
        if company_id != self.company["id"]:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        out = []
        for e in self.employees:
            if e["company_id"] != company_id:
                continue
            rec = dict(e)
            rec["compensation"] = self._comp_for(e["id"])
            out.append(rec)
        return {"status": "ok", "output": out}

    def get_employee(self, employee_id: str) -> Dict[str, Any]:
        e = self._find(self.employees, employee_id)
        if not e:
            return {"status": "failed", "output": f"Employee {employee_id} not found"}
        rec = dict(e)
        rec["compensation"] = self._comp_for(employee_id)
        return {"status": "ok", "output": rec}

    # --- Payrolls ----------------------------------------------------------
    def list_company_payrolls(self, company_id: str, processed: bool | None = None) -> Dict[str, Any]:
        if company_id != self.company["id"]:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        results = [p for p in self.payrolls if p["company_id"] == company_id]
        if processed is not None:
            results = [p for p in results if p["processed"] == processed]
        return {"status": "ok", "output": results}

    def get_payroll(self, payroll_id: str) -> Dict[str, Any]:
        p = self._find(self.payrolls, payroll_id)
        if not p:
            return {"status": "failed", "output": f"Payroll {payroll_id} not found"}
        return {"status": "ok", "output": p}

    def create_payroll(self, company_id: str, pay_period_start: str, pay_period_end: str,
                       check_date: str | None = None) -> Dict[str, Any]:
        if company_id != self.company["id"]:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        if not pay_period_start or not pay_period_end:
            return {"status": "failed", "output": "pay_period_start and pay_period_end are required"}
        p = {
            "id": self._new_id("pay"),
            "company_id": company_id,
            "pay_period_start": pay_period_start,
            "pay_period_end": pay_period_end,
            "check_date": check_date or "",
            "processed": False,
            "gross_pay": 0.0,
            "net_pay": 0.0,
            "employee_count": len([e for e in self.employees
                                   if e["company_id"] == company_id and not e["terminated"]]),
        }
        self.payrolls.append(p)
        return {"status": "ok", "output": p}

    def submit_payroll(self, payroll_id: str) -> Dict[str, Any]:
        p = self._find(self.payrolls, payroll_id)
        if not p:
            return {"status": "failed", "output": f"Payroll {payroll_id} not found"}
        if p["processed"]:
            return {"status": "failed", "output": f"Payroll {payroll_id} already processed"}
        gross = 0.0
        for e in self.employees:
            if e["company_id"] != p["company_id"] or e["terminated"]:
                continue
            comp = self._comp_for(e["id"]) or {}
            rate = comp.get("rate", e.get("rate", 0.0))
            unit = comp.get("payment_unit", e.get("payment_unit", "Year"))
            if unit == "Year":
                gross += rate / 24.0  # 24 semimonthly periods
            elif unit == "Hour":
                gross += rate * 86.67  # ~ semimonthly hours
            else:
                gross += rate
        gross = round(gross, 2)
        p["processed"] = True
        p["gross_pay"] = gross
        p["net_pay"] = round(gross * 0.726, 2)
        return {"status": "ok", "output": p}

    # --- Contractors -------------------------------------------------------
    def list_company_contractors(self, company_id: str) -> Dict[str, Any]:
        if company_id != self.company["id"]:
            return {"status": "failed", "output": f"Company {company_id} not found"}
        return {"status": "ok", "output": [c for c in self.contractors if c["company_id"] == company_id]}


if __name__ == "__main__":
    s = GustoSession(seed=12)
    print(s.get_company("comp-001"))
    print(s.list_company_payrolls("comp-001", processed=False))
