from typing import Dict, List, Optional
from pathlib import Path
import random, sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


RX_STATUSES = ("active", "expired", "cancelled", "filled")
DEA_SCHEDULES = ("non_controlled", "II", "III", "IV", "V")
REFILL_STATUSES = ("pending", "filled", "rejected", "delayed")

SEED_PHARMACIES = [
    {"phid": "ph_downtown", "name": "Downtown Pharmacy", "address": "12 Main St", "phone": "+1-555-0100"},
    {"phid": "ph_riverside","name": "Riverside Drugs",   "address": "88 River Rd", "phone": "+1-555-0199"},
]

SEED_PRESCRIPTIONS = [
    ("Amoxicillin",   "500 mg", "3x daily",   30, 2, "Dr. Chen",   -10,  20, "active",    "non_controlled"),
    ("Adderall XR",   "20 mg",  "1x daily",   30, 5, "Dr. Patel",   -5,  25, "active",    "II"),
    ("Alprazolam",    "0.5 mg", "as needed",  30, 0, "Dr. Chen",   -60, -30, "expired",   "IV"),
    ("Lisinopril",    "10 mg",  "1x daily",   90, 3, "Dr. Nguyen", -20, 160, "filled",    "non_controlled"),
]

SEED_REFILLS = [
    (0, 0, -2,  None,  "pending"),
    (1, 0, -1,   0,    "filled"),
    (3, 1, -3,   -3,   "filled"),
]

SEED_AUDIT_LOGS = [
    ("prescribed", 0, "Dr. Chen",   -10, "Initial prescription written"),
    ("prescribed", 1, "Dr. Patel",   -5, "Controlled substance prescribed"),
    ("filled",     3, "ph_riverside",-3, "Refill filled at Riverside"),
    ("cancelled",  2, "Dr. Chen",  -32, "Marked expired by system"),
    ("refill_req", 0, "patient",    -2, "Refill requested via portal"),
]


@dataclass
class Prescription:
    rxid: str
    medication_name: str
    dosage: str
    frequency: str
    quantity: int
    refills_remaining: int
    prescribed_by: str
    prescribed_on: str
    expires_on: str
    status: str
    dea_schedule: str


@dataclass
class RefillRequest:
    refid: str
    prescription_id: str
    pharmacy_id: str
    requested_at: str
    filled_at: str
    status: str


@dataclass
class Pharmacy:
    phid: str
    name: str
    address: str
    phone: str


@dataclass
class AuditLog:
    alid: str
    action: str
    prescription_id: str
    actor: str
    timestamp: str
    details: str = ""


class MedSession:
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
            self._today = datetime(2026, 1, 5)
            self.pharmacies: Dict[str, Pharmacy] = {
                p["phid"]: Pharmacy(**p) for p in SEED_PHARMACIES
            }
            self.prescriptions: Dict[str, Prescription] = {}
            self.refills: Dict[str, RefillRequest] = {}
            self.audit_logs: Dict[str, AuditLog] = {}
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMed')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _offset(self, days: int) -> str:
        return (self._today + timedelta(days=days)).date().isoformat()

    def _offset_dt(self, days: int) -> str:
        return (self._today + timedelta(days=days)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        rx_ids: List[str] = []
        for (name, dose, freq, qty, refills, presc_by,
             presc_off, exp_off, status, schedule) in SEED_PRESCRIPTIONS:
            rx = Prescription(
                rxid=self.uuid(),
                medication_name=name,
                dosage=dose,
                frequency=freq,
                quantity=qty,
                refills_remaining=refills,
                prescribed_by=presc_by,
                prescribed_on=self._offset(presc_off),
                expires_on=self._offset(exp_off),
                status=status,
                dea_schedule=schedule,
            )
            self.prescriptions[rx.rxid] = rx
            rx_ids.append(rx.rxid)

        pharm_ids = list(self.pharmacies.keys())
        for rx_idx, ph_idx, req_off, fill_off, status in SEED_REFILLS:
            rid = self.uuid()
            self.refills[rid] = RefillRequest(
                refid=rid,
                prescription_id=rx_ids[rx_idx],
                pharmacy_id=pharm_ids[ph_idx],
                requested_at=self._offset_dt(req_off),
                filled_at=self._offset_dt(fill_off) if fill_off is not None else "",
                status=status,
            )

        for action, rx_idx, actor, ts_off, details in SEED_AUDIT_LOGS:
            aid = self.uuid()
            self.audit_logs[aid] = AuditLog(
                alid=aid,
                action=action,
                prescription_id=rx_ids[rx_idx],
                actor=actor,
                timestamp=self._offset_dt(ts_off),
                details=details,
            )

    def get_session_dict(self) -> Dict:
        return {
            "prescriptions": {k: asdict(v) for k, v in self.prescriptions.items()},
            "refills": {k: asdict(v) for k, v in self.refills.items()},
            "pharmacies": {k: asdict(v) for k, v in self.pharmacies.items()},
            "audit_logs": {k: asdict(v) for k, v in self.audit_logs.items()},
        }

    def _log(self, action: str, rxid: str, actor: str, details: str = "") -> None:
        aid = self.uuid()
        self.audit_logs[aid] = AuditLog(
            alid=aid,
            action=action,
            prescription_id=rxid,
            actor=actor,
            timestamp=self._now(),
            details=details,
        )

    def list_prescriptions(self, status: Optional[str] = None,
                           dea_schedule: Optional[str] = None) -> Dict:
        items = list(self.prescriptions.values())
        if status:
            items = [p for p in items if p.status == status]
        if dea_schedule:
            items = [p for p in items if p.dea_schedule == dea_schedule]
        items.sort(key=lambda p: p.prescribed_on, reverse=True)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def get_prescription(self, rxid: str) -> Dict:
        p = self.prescriptions.get(rxid)
        if not p:
            return {"status": "failed", "output": f"prescription {rxid} not found"}
        return {"status": "ok", "output": asdict(p)}

    def add_prescription(self, medication_name: str, dosage: str, frequency: str,
                         quantity: int, refills_remaining: int, prescribed_by: str,
                         prescribed_on: str, expires_on: str,
                         dea_schedule: str = "non_controlled") -> Dict:
        if dea_schedule not in DEA_SCHEDULES:
            return {"status": "failed", "output": f"dea_schedule must be one of {DEA_SCHEDULES}"}
        rx = Prescription(
            rxid=self.uuid(),
            medication_name=medication_name,
            dosage=dosage,
            frequency=frequency,
            quantity=quantity,
            refills_remaining=refills_remaining,
            prescribed_by=prescribed_by,
            prescribed_on=prescribed_on,
            expires_on=expires_on,
            status="active",
            dea_schedule=dea_schedule,
        )
        self.prescriptions[rx.rxid] = rx
        self._log("prescribed", rx.rxid, prescribed_by, f"{medication_name} {dosage}")
        return {"status": "ok", "output": asdict(rx)}

    def update_prescription(self, rxid: str,
                            dosage: Optional[str] = None,
                            frequency: Optional[str] = None,
                            quantity: Optional[int] = None,
                            refills_remaining: Optional[int] = None,
                            expires_on: Optional[str] = None,
                            status: Optional[str] = None) -> Dict:
        rx = self.prescriptions.get(rxid)
        if not rx:
            return {"status": "failed", "output": f"prescription {rxid} not found"}
        if status is not None and status not in RX_STATUSES:
            return {"status": "failed", "output": f"status must be one of {RX_STATUSES}"}
        for k, v in {
            "dosage": dosage, "frequency": frequency, "quantity": quantity,
            "refills_remaining": refills_remaining, "expires_on": expires_on,
            "status": status,
        }.items():
            if v is not None:
                setattr(rx, k, v)
        self._log("updated", rxid, "self", "prescription updated")
        return {"status": "ok", "output": asdict(rx)}

    def cancel_prescription(self, rxid: str) -> Dict:
        rx = self.prescriptions.get(rxid)
        if not rx:
            return {"status": "failed", "output": f"prescription {rxid} not found"}
        rx.status = "cancelled"
        self._log("cancelled", rxid, "self", "prescription cancelled")
        return {"status": "ok", "output": asdict(rx)}

    def list_refills(self, prescription_id: Optional[str] = None,
                     status: Optional[str] = None) -> Dict:
        items = list(self.refills.values())
        if prescription_id:
            items = [r for r in items if r.prescription_id == prescription_id]
        if status:
            items = [r for r in items if r.status == status]
        items.sort(key=lambda r: r.requested_at, reverse=True)
        return {"status": "ok", "output": [asdict(r) for r in items]}

    def request_refill(self, prescription_id: str, pharmacy_id: str) -> Dict:
        rx = self.prescriptions.get(prescription_id)
        if not rx:
            return {"status": "failed", "output": f"prescription {prescription_id} not found"}
        if pharmacy_id not in self.pharmacies:
            return {"status": "failed", "output": f"pharmacy {pharmacy_id} not found"}
        if rx.status != "active":
            return {"status": "failed", "output": f"prescription is {rx.status}, cannot refill"}
        if rx.refills_remaining <= 0:
            return {"status": "failed", "output": "no refills remaining"}
        r = RefillRequest(
            refid=self.uuid(),
            prescription_id=prescription_id,
            pharmacy_id=pharmacy_id,
            requested_at=self._now(),
            filled_at="",
            status="pending",
        )
        self.refills[r.refid] = r
        self._log("refill_req", prescription_id, "patient", f"requested at {pharmacy_id}")
        return {"status": "ok", "output": asdict(r)}

    def fill_refill(self, refid: str) -> Dict:
        r = self.refills.get(refid)
        if not r:
            return {"status": "failed", "output": f"refill {refid} not found"}
        if r.status != "pending":
            return {"status": "failed", "output": f"refill is {r.status}, cannot fill"}
        rx = self.prescriptions.get(r.prescription_id)
        if not rx:
            return {"status": "failed", "output": "underlying prescription missing"}
        if rx.refills_remaining <= 0:
            return {"status": "failed", "output": "no refills remaining"}
        r.status = "filled"
        r.filled_at = self._now()
        rx.refills_remaining -= 1
        self._log("filled", rx.rxid, r.pharmacy_id, f"refill {refid} filled")
        return {"status": "ok", "output": asdict(r)}

    def reject_refill(self, refid: str, reason: str) -> Dict:
        r = self.refills.get(refid)
        if not r:
            return {"status": "failed", "output": f"refill {refid} not found"}
        if r.status != "pending":
            return {"status": "failed", "output": f"refill is {r.status}, cannot reject"}
        r.status = "rejected"
        self._log("rejected", r.prescription_id, r.pharmacy_id, f"refill {refid} rejected: {reason}")
        return {"status": "ok", "output": asdict(r)}

    def list_pharmacies(self) -> Dict:
        return {"status": "ok", "output": [asdict(p) for p in self.pharmacies.values()]}

    def get_pharmacy(self, phid: str) -> Dict:
        p = self.pharmacies.get(phid)
        if not p:
            return {"status": "failed", "output": f"pharmacy {phid} not found"}
        return {"status": "ok", "output": asdict(p)}

    def add_pharmacy(self, name: str, address: str, phone: str) -> Dict:
        phid = "ph_" + self.uuid()[:8]
        p = Pharmacy(phid=phid, name=name, address=address, phone=phone)
        self.pharmacies[phid] = p
        return {"status": "ok", "output": asdict(p)}

    def list_audit_logs(self, prescription_id: Optional[str] = None) -> Dict:
        items = list(self.audit_logs.values())
        if prescription_id:
            items = [a for a in items if a.prescription_id == prescription_id]
        items.sort(key=lambda a: a.timestamp, reverse=True)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def search_prescriptions(self, query: str) -> Dict:
        q = query.lower()
        items = [p for p in self.prescriptions.values()
                 if q in p.medication_name.lower()
                 or q in p.prescribed_by.lower()
                 or q in p.dosage.lower()
                 or q in p.frequency.lower()]
        items.sort(key=lambda p: p.medication_name)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def get_controlled_substances(self) -> Dict:
        items = [p for p in self.prescriptions.values() if p.dea_schedule != "non_controlled"]
        items.sort(key=lambda p: p.dea_schedule)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def get_expiring_soon(self, days: int = 30, today: Optional[str] = None) -> Dict:
        try:
            anchor = datetime.fromisoformat(today).date() if today else self._today.date()
        except ValueError:
            return {"status": "failed", "output": "today must be ISO YYYY-MM-DD"}
        horizon = anchor + timedelta(days=days)
        items: List[Prescription] = []
        for p in self.prescriptions.values():
            if p.status != "active":
                continue
            try:
                d = datetime.fromisoformat(p.expires_on).date()
            except ValueError:
                continue
            if anchor <= d <= horizon:
                items.append(p)
        items.sort(key=lambda p: p.expires_on)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in RX_STATUSES}
        by_schedule: Dict[str, int] = {s: 0 for s in DEA_SCHEDULES}
        for p in self.prescriptions.values():
            by_status[p.status] = by_status.get(p.status, 0) + 1
            by_schedule[p.dea_schedule] = by_schedule.get(p.dea_schedule, 0) + 1
        by_refill_status: Dict[str, int] = {s: 0 for s in REFILL_STATUSES}
        for r in self.refills.values():
            by_refill_status[r.status] = by_refill_status.get(r.status, 0) + 1
        return {
            "status": "ok",
            "output": {
                "prescriptions": len(self.prescriptions),
                "refills": len(self.refills),
                "pharmacies": len(self.pharmacies),
                "audit_logs": len(self.audit_logs),
                "by_status": by_status,
                "by_dea_schedule": by_schedule,
                "by_refill_status": by_refill_status,
            },
        }
