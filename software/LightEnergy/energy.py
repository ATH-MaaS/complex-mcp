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


METER_KINDS = ("electric", "gas", "water", "solar")
BILL_STATUSES = ("unpaid", "paid", "overdue")
ALERT_KINDS = ("high_usage", "leak", "outage")

SEED_METERS = [
    ("Main Electric", "electric", 12345.0, 0.18),
    ("Kitchen Gas",   "gas",       892.5,  0.09),
    ("Home Water",    "water",     3200.0, 0.004),
    ("Rooftop Solar", "solar",     -540.0, 0.12),
]

SEED_READINGS = [
    (0, -6, 12310.0),
    (0, -3, 12328.0),
    (0, -1, 12345.0),
    (1, -6,   870.0),
    (1, -3,   881.2),
    (1, -1,   892.5),
    (2, -6,  3140.0),
    (2, -3,  3170.5),
    (2, -1,  3200.0),
    (3, -6,  -500.0),
    (3, -3,  -525.0),
    (3, -1,  -540.0),
]

SEED_BILLS = [
    (0, -60, -30,  200.0, 36.0, "USD", "paid"),
    (1, -60, -30,   30.0,  2.7, "USD", "unpaid"),
    (2, -60, -30,   80.0,  0.32,"USD", "overdue"),
]

SEED_ALERTS = [
    (0, 500.0,  "high_usage", True),
    (2, 100.0,  "leak",       True),
]


@dataclass
class Meter:
    mid: str
    name: str
    kind: str
    current_reading: float
    currency_rate_per_unit: float


@dataclass
class Reading:
    rdid: str
    meter_id: str
    timestamp: str
    value: float
    cost: float


@dataclass
class Bill:
    bill_id: str
    meter_id: str
    period_start: str
    period_end: str
    consumption: float
    amount: float
    currency: str
    status: str


@dataclass
class Alert:
    aid: str
    meter_id: str
    threshold: float
    kind: str
    is_active: bool = True


class EnergySession:
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
            self.meters: Dict[str, Meter] = {}
            self.readings: Dict[str, Reading] = {}
            self.bills: Dict[str, Bill] = {}
            self.alerts: Dict[str, Alert] = {}
            self._seed_meters()
            self._seed_readings()
            self._seed_bills()
            self._seed_alerts()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightEnergy')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _ts_days(self, day_offset: int) -> str:
        return (self._today + timedelta(days=day_offset)).isoformat(timespec="minutes")

    def _date_days(self, day_offset: int) -> str:
        return (self._today + timedelta(days=day_offset)).date().isoformat()

    def _seed_meters(self) -> None:
        self._seed_mids: List[str] = []
        for name, kind, reading, rate in SEED_METERS:
            m = Meter(
                mid=self.uuid(),
                name=name,
                kind=kind,
                current_reading=reading,
                currency_rate_per_unit=rate,
            )
            self.meters[m.mid] = m
            self._seed_mids.append(m.mid)

    def _seed_readings(self) -> None:
        for meter_idx, day_offset, value in SEED_READINGS:
            if meter_idx >= len(self._seed_mids):
                continue
            mid = self._seed_mids[meter_idx]
            m = self.meters[mid]
            r = Reading(
                rdid=self.uuid(),
                meter_id=mid,
                timestamp=self._ts_days(day_offset),
                value=float(value),
                cost=float(value) * m.currency_rate_per_unit,
            )
            self.readings[r.rdid] = r

    def _seed_bills(self) -> None:
        for meter_idx, ps_off, pe_off, cons, amt, cur, status in SEED_BILLS:
            if meter_idx >= len(self._seed_mids):
                continue
            b = Bill(
                bill_id=self.uuid(),
                meter_id=self._seed_mids[meter_idx],
                period_start=self._date_days(ps_off),
                period_end=self._date_days(pe_off),
                consumption=float(cons),
                amount=float(amt),
                currency=cur,
                status=status,
            )
            self.bills[b.bill_id] = b

    def _seed_alerts(self) -> None:
        for meter_idx, threshold, kind, active in SEED_ALERTS:
            if meter_idx >= len(self._seed_mids):
                continue
            a = Alert(
                aid=self.uuid(),
                meter_id=self._seed_mids[meter_idx],
                threshold=float(threshold),
                kind=kind,
                is_active=active,
            )
            self.alerts[a.aid] = a

    def get_session_dict(self) -> Dict:
        return {
            "meters": {mid: asdict(m) for mid, m in self.meters.items()},
            "readings": {rdid: asdict(r) for rdid, r in self.readings.items()},
            "bills": {bid: asdict(b) for bid, b in self.bills.items()},
            "alerts": {aid: asdict(a) for aid, a in self.alerts.items()},
        }

    def _readings_for(self, meter_id: str) -> List[Reading]:
        return sorted(
            [r for r in self.readings.values() if r.meter_id == meter_id],
            key=lambda r: r.timestamp,
        )

    def list_meters(self, kind: Optional[str] = None) -> Dict:
        items = list(self.meters.values())
        if kind:
            items = [m for m in items if m.kind == kind]
        items.sort(key=lambda m: m.name)
        return {"status": "ok", "output": [asdict(m) for m in items]}

    def get_meter(self, mid: str) -> Dict:
        m = self.meters.get(mid)
        if not m:
            return {"status": "failed", "output": f"meter {mid} not found"}
        return {"status": "ok", "output": asdict(m)}

    def add_meter(self, name: str, kind: str,
                  current_reading: float = 0.0,
                  currency_rate_per_unit: float = 0.0) -> Dict:
        if kind not in METER_KINDS:
            return {"status": "failed", "output": f"kind must be one of {METER_KINDS}"}
        m = Meter(
            mid=self.uuid(),
            name=name,
            kind=kind,
            current_reading=float(current_reading),
            currency_rate_per_unit=float(currency_rate_per_unit),
        )
        self.meters[m.mid] = m
        return {"status": "ok", "output": asdict(m)}

    def list_readings(self, meter_id: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> Dict:
        items = list(self.readings.values())
        if meter_id:
            items = [r for r in items if r.meter_id == meter_id]
        if start_date:
            items = [r for r in items if r.timestamp >= start_date]
        if end_date:
            items = [r for r in items if r.timestamp <= end_date]
        items.sort(key=lambda r: r.timestamp)
        return {"status": "ok", "output": [asdict(r) for r in items]}

    def record_reading(self, meter_id: str, value: float) -> Dict:
        m = self.meters.get(meter_id)
        if not m:
            return {"status": "failed", "output": f"meter {meter_id} not found"}
        r = Reading(
            rdid=self.uuid(),
            meter_id=meter_id,
            timestamp=self._now(),
            value=float(value),
            cost=float(value) * m.currency_rate_per_unit,
        )
        self.readings[r.rdid] = r
        m.current_reading = float(value)
        return {"status": "ok", "output": asdict(r)}

    def get_latest_reading(self, mid: str) -> Dict:
        m = self.meters.get(mid)
        if not m:
            return {"status": "failed", "output": f"meter {mid} not found"}
        rs = self._readings_for(mid)
        if not rs:
            return {"status": "failed", "output": f"no readings for meter {mid}"}
        return {"status": "ok", "output": asdict(rs[-1])}

    def get_usage(self, meter_id: str,
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None) -> Dict:
        m = self.meters.get(meter_id)
        if not m:
            return {"status": "failed", "output": f"meter {meter_id} not found"}
        rs = self._readings_for(meter_id)
        if start_date:
            rs = [r for r in rs if r.timestamp >= start_date]
        if end_date:
            rs = [r for r in rs if r.timestamp <= end_date]
        if len(rs) < 2:
            return {
                "status": "ok",
                "output": {"meter_id": meter_id, "consumption": 0.0, "cost": 0.0, "readings": len(rs)},
            }
        consumption = rs[-1].value - rs[0].value
        return {
            "status": "ok",
            "output": {
                "meter_id": meter_id,
                "start": rs[0].timestamp,
                "end": rs[-1].timestamp,
                "consumption": consumption,
                "cost": consumption * m.currency_rate_per_unit,
                "readings": len(rs),
            },
        }

    def list_bills(self, meter_id: Optional[str] = None,
                   status: Optional[str] = None) -> Dict:
        items = list(self.bills.values())
        if meter_id:
            items = [b for b in items if b.meter_id == meter_id]
        if status:
            items = [b for b in items if b.status == status]
        items.sort(key=lambda b: b.period_end, reverse=True)
        return {"status": "ok", "output": [asdict(b) for b in items]}

    def get_bill(self, bill_id: str) -> Dict:
        b = self.bills.get(bill_id)
        if not b:
            return {"status": "failed", "output": f"bill {bill_id} not found"}
        return {"status": "ok", "output": asdict(b)}

    def generate_bill(self, meter_id: str, period_start: str, period_end: str) -> Dict:
        m = self.meters.get(meter_id)
        if not m:
            return {"status": "failed", "output": f"meter {meter_id} not found"}
        rs = self._readings_for(meter_id)
        rs = [r for r in rs if period_start <= r.timestamp[:10] <= period_end]
        if len(rs) < 2:
            consumption = 0.0
        else:
            consumption = rs[-1].value - rs[0].value
        amount = consumption * m.currency_rate_per_unit
        b = Bill(
            bill_id=self.uuid(),
            meter_id=meter_id,
            period_start=period_start,
            period_end=period_end,
            consumption=consumption,
            amount=amount,
            currency="USD",
            status="unpaid",
        )
        self.bills[b.bill_id] = b
        return {"status": "ok", "output": asdict(b)}

    def pay_bill(self, bill_id: str) -> Dict:
        b = self.bills.get(bill_id)
        if not b:
            return {"status": "failed", "output": f"bill {bill_id} not found"}
        if b.status == "paid":
            return {"status": "failed", "output": f"bill {bill_id} already paid"}
        b.status = "paid"
        return {"status": "ok", "output": asdict(b)}

    def list_alerts(self, is_active: Optional[bool] = None) -> Dict:
        items = list(self.alerts.values())
        if is_active is not None:
            items = [a for a in items if a.is_active == is_active]
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def create_alert(self, meter_id: str, threshold: float, kind: str) -> Dict:
        if meter_id not in self.meters:
            return {"status": "failed", "output": f"meter {meter_id} not found"}
        if kind not in ALERT_KINDS:
            return {"status": "failed", "output": f"kind must be one of {ALERT_KINDS}"}
        a = Alert(
            aid=self.uuid(),
            meter_id=meter_id,
            threshold=float(threshold),
            kind=kind,
            is_active=True,
        )
        self.alerts[a.aid] = a
        return {"status": "ok", "output": asdict(a)}

    def toggle_alert(self, aid: str) -> Dict:
        a = self.alerts.get(aid)
        if not a:
            return {"status": "failed", "output": f"alert {aid} not found"}
        a.is_active = not a.is_active
        return {"status": "ok", "output": asdict(a)}

    def compare_periods(self, meter_id: str,
                        period_a_start: str, period_a_end: str,
                        period_b_start: str, period_b_end: str) -> Dict:
        m = self.meters.get(meter_id)
        if not m:
            return {"status": "failed", "output": f"meter {meter_id} not found"}

        def usage(ps: str, pe: str) -> Dict:
            rs = self._readings_for(meter_id)
            rs = [r for r in rs if ps <= r.timestamp <= pe]
            if len(rs) < 2:
                return {"consumption": 0.0, "cost": 0.0, "readings": len(rs)}
            cons = rs[-1].value - rs[0].value
            return {"consumption": cons, "cost": cons * m.currency_rate_per_unit, "readings": len(rs)}

        a = usage(period_a_start, period_a_end)
        b = usage(period_b_start, period_b_end)
        delta_cons = b["consumption"] - a["consumption"]
        delta_cost = b["cost"] - a["cost"]
        return {
            "status": "ok",
            "output": {
                "meter_id": meter_id,
                "period_a": {"start": period_a_start, "end": period_a_end, **a},
                "period_b": {"start": period_b_start, "end": period_b_end, **b},
                "delta_consumption": delta_cons,
                "delta_cost": delta_cost,
            },
        }

    def get_stats(self) -> Dict:
        by_kind: Dict[str, int] = {k: 0 for k in METER_KINDS}
        for m in self.meters.values():
            by_kind[m.kind] = by_kind.get(m.kind, 0) + 1
        bills_by_status: Dict[str, int] = {s: 0 for s in BILL_STATUSES}
        total_unpaid = 0.0
        for b in self.bills.values():
            bills_by_status[b.status] = bills_by_status.get(b.status, 0) + 1
            if b.status in {"unpaid", "overdue"}:
                total_unpaid += b.amount
        active_alerts = sum(1 for a in self.alerts.values() if a.is_active)
        return {
            "status": "ok",
            "output": {
                "meters": len(self.meters),
                "readings": len(self.readings),
                "bills": len(self.bills),
                "alerts": len(self.alerts),
                "by_meter_kind": by_kind,
                "bills_by_status": bills_by_status,
                "total_unpaid": total_unpaid,
                "active_alerts": active_alerts,
            },
        }
