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


ASSET_CATEGORIES = ("car", "bike", "scooter", "tool", "camera")
ASSET_CONDITIONS = ("excellent", "good", "fair", "poor")
BOOKING_STATUSES = ("reserved", "active", "returned", "cancelled")
DEFAULT_CURRENCY = "USD"

SEED_ASSETS = [
    ("Toyota Prius 2024",       "car",     45.00, "Downtown Garage",   True,  "excellent"),
    ("Tesla Model 3",           "car",     95.00, "Airport Lot",       True,  "excellent"),
    ("Trek Roam 7 Bike",        "bike",    18.00, "Bike Kiosk East",   True,  "good"),
    ("Segway Ninebot Scooter",  "scooter", 12.00, "Bike Kiosk East",   False, "good"),
    ("DeWalt Cordless Drill",   "tool",     9.50, "Tool Shed",         True,  "fair"),
    ("Sony A7 IV Camera",       "camera",  55.00, "Gear Locker",       False, "excellent"),
]

SEED_BOOKINGS = [
    ("Toyota Prius 2024",      "self",   -2,  1,  "active",   "Weekend errand car"),
    ("Sony A7 IV Camera",      "friend",  1,  4,  "reserved", "Wedding shoot"),
    ("DeWalt Cordless Drill",  "self",   -8, -5,  "returned", "Shelving project"),
]

SEED_DAMAGES = [
    ("DeWalt Cordless Drill",  0, "Chuck slipping under load",  25.00, -4),
    ("Toyota Prius 2024",      0, "Minor scratch on rear bumper", 120.00, -1),
]


@dataclass
class Asset:
    aid: str
    name: str
    category: str
    daily_rate: float
    currency: str
    location: str
    is_available: bool
    condition: str


@dataclass
class Booking:
    bid: str
    asset_id: str
    renter: str
    start_date: str
    end_date: str
    total_cost: float
    currency: str
    status: str
    notes: str = ""


@dataclass
class Damage:
    dmid: str
    asset_id: str
    booking_id: str
    description: str
    cost: float
    date: str


class RentalSession:
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
            self.assets: Dict[str, Asset] = {}
            self.bookings: Dict[str, Booking] = {}
            self.damages: Dict[str, Damage] = {}
            self._name_to_aid: Dict[str, str] = {}
            self._seed_assets()
            self._seed_bookings()
            self._seed_damages()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightRental')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _today_iso(self) -> str:
        return self._today.date().isoformat()

    def _days_and_cost(self, start_date: str, end_date: str, daily_rate: float) -> (int, float):
        try:
            d0 = datetime.fromisoformat(start_date).date()
            d1 = datetime.fromisoformat(end_date).date()
        except Exception:
            return 0, 0.0
        days = max(0, (d1 - d0).days + 1)
        return days, round(days * daily_rate, 2)

    def _seed_assets(self) -> None:
        for name, cat, rate, loc, avail, cond in SEED_ASSETS:
            a = Asset(
                aid="ast_" + self.uuid()[:8],
                name=name,
                category=cat,
                daily_rate=rate,
                currency=DEFAULT_CURRENCY,
                location=loc,
                is_available=avail,
                condition=cond,
            )
            self.assets[a.aid] = a
            self._name_to_aid[name] = a.aid

    def _seed_bookings(self) -> None:
        self._seeded_bookings_by_asset: Dict[str, str] = {}
        for aname, renter, start_off, end_off, status, notes in SEED_BOOKINGS:
            aid = self._name_to_aid.get(aname)
            if aid is None:
                continue
            a = self.assets[aid]
            start = (self._today + timedelta(days=start_off)).date().isoformat()
            end = (self._today + timedelta(days=end_off)).date().isoformat()
            _, cost = self._days_and_cost(start, end, a.daily_rate)
            b = Booking(
                bid="bkg_" + self.uuid()[:8],
                asset_id=aid,
                renter=renter,
                start_date=start,
                end_date=end,
                total_cost=cost,
                currency=a.currency,
                status=status,
                notes=notes,
            )
            self.bookings[b.bid] = b
            self._seeded_bookings_by_asset[aname] = b.bid
            if status == "active":
                a.is_available = False

    def _seed_damages(self) -> None:
        for aname, bidx, desc, cost, day_off in SEED_DAMAGES:
            aid = self._name_to_aid.get(aname)
            if aid is None:
                continue
            bid = self._seeded_bookings_by_asset.get(aname, "")
            d = Damage(
                dmid="dmg_" + self.uuid()[:8],
                asset_id=aid,
                booking_id=bid,
                description=desc,
                cost=cost,
                date=(self._today + timedelta(days=day_off)).date().isoformat(),
            )
            self.damages[d.dmid] = d

    def get_session_dict(self) -> Dict:
        return {
            "assets":   {aid: asdict(a) for aid, a in self.assets.items()},
            "bookings": {bid: asdict(b) for bid, b in self.bookings.items()},
            "damages":  {did: asdict(d) for did, d in self.damages.items()},
        }

    def _booking_summary(self, b: Booking) -> Dict:
        return {
            "bid": b.bid,
            "asset_id": b.asset_id,
            "renter": b.renter,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "status": b.status,
            "total_cost": b.total_cost,
            "currency": b.currency,
        }

    def list_assets(self, category: Optional[str] = None, is_available: Optional[bool] = None) -> Dict:
        items = list(self.assets.values())
        if category:
            if category not in ASSET_CATEGORIES:
                return {"status": "failed", "output": f"category must be one of {ASSET_CATEGORIES}"}
            items = [a for a in items if a.category == category]
        if is_available is not None:
            items = [a for a in items if a.is_available == is_available]
        items.sort(key=lambda a: (a.category, a.daily_rate))
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def get_asset(self, aid: str) -> Dict:
        a = self.assets.get(aid)
        if not a:
            return {"status": "failed", "output": f"asset {aid} not found"}
        return {"status": "ok", "output": asdict(a)}

    def add_asset(self, name: str, category: str, daily_rate: float, location: str,
                  condition: str = "good", is_available: bool = True,
                  currency: str = DEFAULT_CURRENCY) -> Dict:
        if category not in ASSET_CATEGORIES:
            return {"status": "failed", "output": f"category must be one of {ASSET_CATEGORIES}"}
        if condition not in ASSET_CONDITIONS:
            return {"status": "failed", "output": f"condition must be one of {ASSET_CONDITIONS}"}
        a = Asset(
            aid="ast_" + self.uuid()[:8],
            name=name,
            category=category,
            daily_rate=daily_rate,
            currency=currency,
            location=location,
            is_available=is_available,
            condition=condition,
        )
        self.assets[a.aid] = a
        return {"status": "ok", "output": asdict(a)}

    def list_bookings(self, status: Optional[str] = None, renter: Optional[str] = None) -> Dict:
        items = list(self.bookings.values())
        if status:
            if status not in BOOKING_STATUSES:
                return {"status": "failed", "output": f"status must be one of {BOOKING_STATUSES}"}
            items = [b for b in items if b.status == status]
        if renter:
            items = [b for b in items if b.renter == renter]
        items.sort(key=lambda b: b.start_date, reverse=True)
        return {"status": "ok", "output": [self._booking_summary(b) for b in items]}

    def get_booking(self, bid: str) -> Dict:
        b = self.bookings.get(bid)
        if not b:
            return {"status": "failed", "output": f"booking {bid} not found"}
        return {"status": "ok", "output": asdict(b)}

    def _has_conflict(self, aid: str, start_date: str, end_date: str,
                      exclude_bid: Optional[str] = None) -> bool:
        try:
            d0 = datetime.fromisoformat(start_date).date()
            d1 = datetime.fromisoformat(end_date).date()
        except Exception:
            return True
        for b in self.bookings.values():
            if b.asset_id != aid or b.status in {"cancelled", "returned"}:
                continue
            if exclude_bid and b.bid == exclude_bid:
                continue
            try:
                bs = datetime.fromisoformat(b.start_date).date()
                be = datetime.fromisoformat(b.end_date).date()
            except Exception:
                continue
            if not (be < d0 or bs > d1):
                return True
        return False

    def book_asset(self, aid: str, renter: str, start_date: str, end_date: str) -> Dict:
        a = self.assets.get(aid)
        if not a:
            return {"status": "failed", "output": f"asset {aid} not found"}
        days, cost = self._days_and_cost(start_date, end_date, a.daily_rate)
        if days <= 0:
            return {"status": "failed", "output": "end_date must be on or after start_date"}
        if self._has_conflict(aid, start_date, end_date):
            return {"status": "failed", "output": f"asset {aid} is not available in that range"}
        b = Booking(
            bid="bkg_" + self.uuid()[:8],
            asset_id=aid,
            renter=renter,
            start_date=start_date,
            end_date=end_date,
            total_cost=cost,
            currency=a.currency,
            status="reserved",
            notes="",
        )
        self.bookings[b.bid] = b
        return {"status": "ok", "output": self._booking_summary(b)}

    def cancel_booking(self, bid: str) -> Dict:
        b = self.bookings.get(bid)
        if not b:
            return {"status": "failed", "output": f"booking {bid} not found"}
        if b.status in {"returned", "cancelled"}:
            return {"status": "failed", "output": f"booking {bid} cannot be cancelled (status={b.status})"}
        b.status = "cancelled"
        return {"status": "ok", "output": self._booking_summary(b)}

    def return_asset(self, bid: str) -> Dict:
        b = self.bookings.get(bid)
        if not b:
            return {"status": "failed", "output": f"booking {bid} not found"}
        if b.status not in {"reserved", "active"}:
            return {"status": "failed", "output": f"booking {bid} cannot be returned (status={b.status})"}
        b.status = "returned"
        a = self.assets.get(b.asset_id)
        if a:
            a.is_available = True
        return {"status": "ok", "output": self._booking_summary(b)}

    def report_damage(self, aid: str, bid: str, description: str, cost: float) -> Dict:
        if aid not in self.assets:
            return {"status": "failed", "output": f"asset {aid} not found"}
        if bid and bid not in self.bookings:
            return {"status": "failed", "output": f"booking {bid} not found"}
        d = Damage(
            dmid="dmg_" + self.uuid()[:8],
            asset_id=aid,
            booking_id=bid,
            description=description,
            cost=cost,
            date=self._today_iso(),
        )
        self.damages[d.dmid] = d
        return {"status": "ok", "output": asdict(d)}

    def list_damages(self, asset_id: Optional[str] = None) -> Dict:
        items = list(self.damages.values())
        if asset_id:
            items = [d for d in items if d.asset_id == asset_id]
        items.sort(key=lambda d: d.date, reverse=True)
        return {"status": "ok", "output": [asdict(d) for d in items]}

    def get_asset_availability(self, aid: str, start_date: str, end_date: str) -> Dict:
        if aid not in self.assets:
            return {"status": "failed", "output": f"asset {aid} not found"}
        available = not self._has_conflict(aid, start_date, end_date)
        return {"status": "ok", "output": {
            "aid": aid, "start_date": start_date, "end_date": end_date, "available": available,
        }}

    def get_asset_revenue(self, aid: str) -> Dict:
        if aid not in self.assets:
            return {"status": "failed", "output": f"asset {aid} not found"}
        total = 0.0
        count = 0
        for b in self.bookings.values():
            if b.asset_id == aid and b.status in {"active", "returned"}:
                total += b.total_cost
                count += 1
        return {"status": "ok", "output": {
            "aid": aid, "bookings_counted": count, "revenue": round(total, 2),
        }}

    def search_assets(self, query: str) -> Dict:
        q = query.lower()
        items = [a for a in self.assets.values()
                 if q in a.name.lower() or q in a.category.lower() or q in a.location.lower()]
        items.sort(key=lambda a: a.name)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in BOOKING_STATUSES}
        by_category: Dict[str, int] = {c: 0 for c in ASSET_CATEGORIES}
        revenue = 0.0
        for b in self.bookings.values():
            by_status[b.status] = by_status.get(b.status, 0) + 1
            if b.status in {"active", "returned"}:
                revenue += b.total_cost
        for a in self.assets.values():
            by_category[a.category] = by_category.get(a.category, 0) + 1
        return {
            "status": "ok",
            "output": {
                "assets": len(self.assets),
                "by_category": by_category,
                "bookings": len(self.bookings),
                "by_status": by_status,
                "damages": len(self.damages),
                "revenue": round(revenue, 2),
            },
        }
