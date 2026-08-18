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

@dataclass
class Subscription:
    sid: str
    name: str
    provider: str
    amount: float
    currency: str = "USD"
    period: str = "monthly"  # monthly|yearly|weekly
    next_charge: str = ""
    status: str = "active"  # active|paused|cancelled
    category: str = "general"

@dataclass
class Payment:
    pid: str
    subscription_id: str
    amount: float
    currency: str
    date: str
    status: str = "paid"  # paid|failed|pending

SEED_SUBS = [
    ("Netflix", "Netflix", 15.99, "monthly", "entertainment"),
    ("Spotify", "Spotify", 9.99, "monthly", "music"),
    ("iCloud", "Apple", 2.99, "monthly", "storage"),
    ("NYT", "New York Times", 17.00, "monthly", "news"),
]

class SubscriptionSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.subs: Dict[str, Subscription] = {}
            self.payments: Dict[str, Payment] = {}
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSubscription')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self):
        base = datetime(2026, 2, 1)
        for name, provider, amount, period, cat in SEED_SUBS:
            nxt = base.isoformat(timespec="minutes")
            s = Subscription(sid=self.uuid(), name=name, provider=provider, amount=amount,
                             period=period, next_charge=nxt, category=cat)
            self.subs[s.sid] = s

    def get_session_dict(self):
        return {
            "subscriptions": {k: asdict(v) for k, v in self.subs.items()},
            "payments": {k: asdict(v) for k, v in self.payments.items()},
        }

    def list_subscriptions(self, status: Optional[str] = None, category: Optional[str] = None):
        out = []
        for s in self.subs.values():
            if status and s.status != status: continue
            if category and s.category != category: continue
            out.append(asdict(s))
        return {"status": "ok", "output": out}

    def get_subscription(self, sid: str):
        s = self.subs.get(sid)
        if not s: return {"status": "failed", "output": f"subscription {sid} not found"}
        return {"status": "ok", "output": asdict(s)}

    def add_subscription(self, name: str, provider: str, amount: float, period: str = "monthly", currency: str = "USD", next_charge: str = "", category: str = "general"):
        s = Subscription(sid=self.uuid(), name=name, provider=provider, amount=amount,
                         period=period, currency=currency, next_charge=next_charge, category=category)
        self.subs[s.sid] = s
        return {"status": "ok", "output": asdict(s)}

    def update_subscription(self, sid: str, **fields):
        s = self.subs.get(sid)
        if not s: return {"status": "failed", "output": "subscription not found"}
        for k, v in fields.items():
            if v is not None and hasattr(s, k):
                setattr(s, k, v)
        return {"status": "ok", "output": asdict(s)}

    def cancel_subscription(self, sid: str):
        s = self.subs.get(sid)
        if not s: return {"status": "failed", "output": "subscription not found"}
        s.status = "cancelled"
        return {"status": "ok", "output": asdict(s)}

    def pause_subscription(self, sid: str):
        s = self.subs.get(sid)
        if not s: return {"status": "failed", "output": "subscription not found"}
        s.status = "paused"
        return {"status": "ok", "output": asdict(s)}

    def resume_subscription(self, sid: str):
        s = self.subs.get(sid)
        if not s: return {"status": "failed", "output": "subscription not found"}
        s.status = "active"
        return {"status": "ok", "output": asdict(s)}

    def delete_subscription(self, sid: str):
        if sid not in self.subs: return {"status": "failed", "output": "subscription not found"}
        del self.subs[sid]
        return {"status": "ok", "output": sid}

    def record_payment(self, subscription_id: str, amount: float, date: str, currency: str = "USD", status: str = "paid"):
        if subscription_id not in self.subs: return {"status": "failed", "output": "subscription not found"}
        p = Payment(pid=self.uuid(), subscription_id=subscription_id, amount=amount,
                    currency=currency, date=date, status=status)
        self.payments[p.pid] = p
        return {"status": "ok", "output": asdict(p)}

    def list_payments(self, subscription_id: Optional[str] = None, status: Optional[str] = None):
        out = []
        for p in self.payments.values():
            if subscription_id and p.subscription_id != subscription_id: continue
            if status and p.status != status: continue
            out.append(asdict(p))
        return {"status": "ok", "output": out}

    def monthly_cost(self):
        total = 0.0
        for s in self.subs.values():
            if s.status != "active": continue
            if s.period == "monthly": total += s.amount
            elif s.period == "yearly": total += s.amount / 12.0
            elif s.period == "weekly": total += s.amount * 52 / 12.0
        return {"status": "ok", "output": {"monthly_cost": round(total, 2)}}

    def yearly_cost(self):
        r = self.monthly_cost()
        return {"status": "ok", "output": {"yearly_cost": round(r["output"]["monthly_cost"] * 12, 2)}}

    def cost_by_category(self):
        by_cat: Dict[str, float] = {}
        for s in self.subs.values():
            if s.status != "active": continue
            monthly = s.amount if s.period == "monthly" else (s.amount / 12.0 if s.period == "yearly" else s.amount * 52 / 12.0)
            by_cat[s.category] = by_cat.get(s.category, 0.0) + monthly
        return {"status": "ok", "output": {k: round(v, 2) for k, v in by_cat.items()}}

    def upcoming_charges(self, limit: int = 5):
        active = [asdict(s) for s in self.subs.values() if s.status == "active"]
        active.sort(key=lambda x: x["next_charge"] or "")
        return {"status": "ok", "output": active[:limit]}

    def search(self, query: str):
        q = query.lower()
        hits = [asdict(s) for s in self.subs.values() if q in s.name.lower() or q in s.provider.lower()]
        return {"status": "ok", "output": hits}

    def get_stats(self):
        return {"status": "ok", "output": {
            "total_subscriptions": len(self.subs),
            "active": sum(1 for s in self.subs.values() if s.status == "active"),
            "paused": sum(1 for s in self.subs.values() if s.status == "paused"),
            "cancelled": sum(1 for s in self.subs.values() if s.status == "cancelled"),
            "total_payments": len(self.payments),
        }}
