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


RESERVATION_STATUSES = ("booked", "checked_in", "checked_out", "cancelled")
ROOM_TYPES = ("single", "double", "suite", "family")
DEFAULT_CURRENCY = "USD"

SEED_HOTELS = [
    ("Grand Marina Hotel",   "San Francisco", 5, ["wifi", "pool", "gym", "spa", "restaurant"], 320.0),
    ("Bayview Inn",          "San Francisco", 3, ["wifi", "breakfast"],                        140.0),
    ("Central Park Suites",  "New York",      4, ["wifi", "gym", "restaurant"],                260.0),
    ("Times Square Lodge",   "New York",      3, ["wifi", "breakfast", "gym"],                 180.0),
    ("Lakeside Retreat",     "Chicago",       4, ["wifi", "pool", "spa"],                      210.0),
]

SEED_RESERVATIONS = [
    ("self",    "Grand Marina Hotel",  -14, -12, "double", "checked_out", 2),
    ("self",    "Central Park Suites",   3,   6, "suite",  "booked",      2),
    ("friend",  "Bayview Inn",           0,   2, "single", "checked_in",  1),
    ("friend",  "Lakeside Retreat",     -5,  -3, "family", "cancelled",   4),
]

SEED_REVIEWS = [
    ("Grand Marina Hotel",  "self",    5, "Amazing service, huge room, would return.",         -10),
    ("Central Park Suites", "friend",  4, "Great location, small bathroom.",                    -20),
    ("Bayview Inn",         "self",    3, "OK for the price, walls are thin.",                  -60),
    ("Lakeside Retreat",    "guest2",  5, "Perfect for families, kids loved the pool.",         -90),
]


@dataclass
class Hotel:
    hid: str
    name: str
    city: str
    star_rating: int
    amenities: List[str] = field(default_factory=list)
    price_per_night: float = 0.0
    currency: str = DEFAULT_CURRENCY


@dataclass
class Reservation:
    resid: str
    hotel_id: str
    guest: str
    check_in: str
    check_out: str
    room_type: str
    total_price: float
    currency: str
    status: str
    guests_count: int = 1


@dataclass
class Review:
    revid: str
    hotel_id: str
    guest: str
    rating: int
    comment: str
    date: str


class HotelSession:
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
            self.hotels: Dict[str, Hotel] = {}
            self.reservations: Dict[str, Reservation] = {}
            self.reviews: Dict[str, Review] = {}
            self._name_to_hid: Dict[str, str] = {}
            self._seed_hotels()
            self._seed_reservations()
            self._seed_reviews()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightHotel')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _today_iso(self) -> str:
        return self._today.date().isoformat()

    def _price_nights(self, check_in: str, check_out: str, price_per_night: float) -> (int, float):
        try:
            d0 = datetime.fromisoformat(check_in).date()
            d1 = datetime.fromisoformat(check_out).date()
        except Exception:
            return 0, 0.0
        nights = max(0, (d1 - d0).days)
        return nights, round(nights * price_per_night, 2)

    def _seed_hotels(self) -> None:
        for name, city, stars, amenities, price in SEED_HOTELS:
            h = Hotel(
                hid="hot_" + self.uuid()[:8],
                name=name,
                city=city,
                star_rating=stars,
                amenities=list(amenities),
                price_per_night=price,
            )
            self.hotels[h.hid] = h
            self._name_to_hid[name] = h.hid

    def _seed_reservations(self) -> None:
        for guest, hname, in_off, out_off, room_type, status, guests_count in SEED_RESERVATIONS:
            hid = self._name_to_hid.get(hname)
            if hid is None:
                continue
            h = self.hotels[hid]
            check_in = (self._today + timedelta(days=in_off)).date().isoformat()
            check_out = (self._today + timedelta(days=out_off)).date().isoformat()
            _, total = self._price_nights(check_in, check_out, h.price_per_night)
            r = Reservation(
                resid="res_" + self.uuid()[:8],
                hotel_id=hid,
                guest=guest,
                check_in=check_in,
                check_out=check_out,
                room_type=room_type,
                total_price=total,
                currency=h.currency,
                status=status,
                guests_count=guests_count,
            )
            self.reservations[r.resid] = r

    def _seed_reviews(self) -> None:
        for hname, guest, rating, comment, day_off in SEED_REVIEWS:
            hid = self._name_to_hid.get(hname)
            if hid is None:
                continue
            date = (self._today + timedelta(days=day_off)).date().isoformat()
            rv = Review(
                revid="rev_" + self.uuid()[:8],
                hotel_id=hid,
                guest=guest,
                rating=rating,
                comment=comment,
                date=date,
            )
            self.reviews[rv.revid] = rv

    def get_session_dict(self) -> Dict:
        return {
            "hotels":       {hid: asdict(h) for hid, h in self.hotels.items()},
            "reservations": {rid: asdict(r) for rid, r in self.reservations.items()},
            "reviews":      {vid: asdict(v) for vid, v in self.reviews.items()},
        }

    def _res_summary(self, r: Reservation) -> Dict:
        return {
            "resid": r.resid,
            "hotel_id": r.hotel_id,
            "guest": r.guest,
            "check_in": r.check_in,
            "check_out": r.check_out,
            "status": r.status,
            "total_price": r.total_price,
            "currency": r.currency,
            "room_type": r.room_type,
            "guests_count": r.guests_count,
        }

    def list_hotels(self, city: Optional[str] = None, star_rating: Optional[int] = None) -> Dict:
        items = list(self.hotels.values())
        if city:
            items = [h for h in items if h.city.lower() == city.lower()]
        if star_rating is not None:
            items = [h for h in items if h.star_rating == star_rating]
        items.sort(key=lambda h: (-h.star_rating, h.price_per_night))
        return {"status": "ok", "output": [asdict(h) for h in items]}

    def get_hotel(self, hid: str) -> Dict:
        h = self.hotels.get(hid)
        if not h:
            return {"status": "failed", "output": f"hotel {hid} not found"}
        return {"status": "ok", "output": asdict(h)}

    def add_hotel(self, name: str, city: str, star_rating: int,
                  price_per_night: float, amenities: Optional[List[str]] = None,
                  currency: str = DEFAULT_CURRENCY) -> Dict:
        if not 1 <= star_rating <= 5:
            return {"status": "failed", "output": "star_rating must be 1..5"}
        h = Hotel(
            hid="hot_" + self.uuid()[:8],
            name=name,
            city=city,
            star_rating=star_rating,
            amenities=list(amenities) if amenities else [],
            price_per_night=price_per_night,
            currency=currency,
        )
        self.hotels[h.hid] = h
        return {"status": "ok", "output": asdict(h)}

    def list_reservations(self, status: Optional[str] = None, hotel_id: Optional[str] = None) -> Dict:
        items = list(self.reservations.values())
        if status:
            if status not in RESERVATION_STATUSES:
                return {"status": "failed", "output": f"status must be one of {RESERVATION_STATUSES}"}
            items = [r for r in items if r.status == status]
        if hotel_id:
            items = [r for r in items if r.hotel_id == hotel_id]
        items.sort(key=lambda r: r.check_in)
        return {"status": "ok", "output": [self._res_summary(r) for r in items]}

    def get_reservation(self, resid: str) -> Dict:
        r = self.reservations.get(resid)
        if not r:
            return {"status": "failed", "output": f"reservation {resid} not found"}
        return {"status": "ok", "output": asdict(r)}

    def create_reservation(self, hotel_id: str, guest: str, check_in: str, check_out: str,
                           room_type: str, guests_count: int = 1) -> Dict:
        h = self.hotels.get(hotel_id)
        if not h:
            return {"status": "failed", "output": f"hotel {hotel_id} not found"}
        if room_type not in ROOM_TYPES:
            return {"status": "failed", "output": f"room_type must be one of {ROOM_TYPES}"}
        nights, total = self._price_nights(check_in, check_out, h.price_per_night)
        if nights <= 0:
            return {"status": "failed", "output": "check_out must be after check_in"}
        r = Reservation(
            resid="res_" + self.uuid()[:8],
            hotel_id=hotel_id,
            guest=guest,
            check_in=check_in,
            check_out=check_out,
            room_type=room_type,
            total_price=total,
            currency=h.currency,
            status="booked",
            guests_count=guests_count,
        )
        self.reservations[r.resid] = r
        return {"status": "ok", "output": self._res_summary(r)}

    def cancel_reservation(self, resid: str) -> Dict:
        r = self.reservations.get(resid)
        if not r:
            return {"status": "failed", "output": f"reservation {resid} not found"}
        if r.status in {"checked_out", "cancelled"}:
            return {"status": "failed", "output": f"reservation {resid} cannot be cancelled (status={r.status})"}
        r.status = "cancelled"
        return {"status": "ok", "output": self._res_summary(r)}

    def check_in(self, resid: str) -> Dict:
        r = self.reservations.get(resid)
        if not r:
            return {"status": "failed", "output": f"reservation {resid} not found"}
        if r.status != "booked":
            return {"status": "failed", "output": f"reservation {resid} must be 'booked' to check in (status={r.status})"}
        r.status = "checked_in"
        return {"status": "ok", "output": self._res_summary(r)}

    def check_out(self, resid: str) -> Dict:
        r = self.reservations.get(resid)
        if not r:
            return {"status": "failed", "output": f"reservation {resid} not found"}
        if r.status != "checked_in":
            return {"status": "failed", "output": f"reservation {resid} must be 'checked_in' to check out (status={r.status})"}
        r.status = "checked_out"
        return {"status": "ok", "output": self._res_summary(r)}

    def list_reviews(self, hotel_id: Optional[str] = None) -> Dict:
        items = list(self.reviews.values())
        if hotel_id:
            items = [v for v in items if v.hotel_id == hotel_id]
        items.sort(key=lambda v: v.date, reverse=True)
        return {"status": "ok", "output": [asdict(v) for v in items]}

    def add_review(self, hotel_id: str, guest: str, rating: int, comment: str) -> Dict:
        if hotel_id not in self.hotels:
            return {"status": "failed", "output": f"hotel {hotel_id} not found"}
        if not 1 <= rating <= 5:
            return {"status": "failed", "output": "rating must be 1..5"}
        rv = Review(
            revid="rev_" + self.uuid()[:8],
            hotel_id=hotel_id,
            guest=guest,
            rating=rating,
            comment=comment,
            date=self._today_iso(),
        )
        self.reviews[rv.revid] = rv
        return {"status": "ok", "output": asdict(rv)}

    def get_average_rating(self, hid: str) -> Dict:
        if hid not in self.hotels:
            return {"status": "failed", "output": f"hotel {hid} not found"}
        ratings = [v.rating for v in self.reviews.values() if v.hotel_id == hid]
        avg = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
        return {"status": "ok", "output": {"hid": hid, "count": len(ratings), "average": avg}}

    def search_hotels(self, city: str, check_in: str, check_out: str) -> Dict:
        try:
            d0 = datetime.fromisoformat(check_in).date()
            d1 = datetime.fromisoformat(check_out).date()
        except Exception:
            return {"status": "failed", "output": "check_in/check_out must be ISO dates"}
        if d1 <= d0:
            return {"status": "failed", "output": "check_out must be after check_in"}
        nights = (d1 - d0).days
        hotels_in_city = [h for h in self.hotels.values() if h.city.lower() == city.lower()]
        results = []
        for h in hotels_in_city:
            conflict = False
            for r in self.reservations.values():
                if r.hotel_id != h.hid or r.status in {"cancelled", "checked_out"}:
                    continue
                try:
                    rin = datetime.fromisoformat(r.check_in).date()
                    rout = datetime.fromisoformat(r.check_out).date()
                except Exception:
                    continue
                if not (rout <= d0 or rin >= d1):
                    conflict = True
                    break
            if not conflict:
                results.append({
                    "hid": h.hid,
                    "name": h.name,
                    "city": h.city,
                    "star_rating": h.star_rating,
                    "price_per_night": h.price_per_night,
                    "total_price": round(nights * h.price_per_night, 2),
                    "currency": h.currency,
                    "nights": nights,
                })
        results.sort(key=lambda x: (-x["star_rating"], x["price_per_night"]))
        return {"status": "ok", "output": results}

    def list_upcoming_stays(self, guest: str, today: Optional[str] = None) -> Dict:
        anchor = datetime.fromisoformat(today).date() if today else self._today.date()
        items = []
        for r in self.reservations.values():
            if r.guest != guest or r.status not in {"booked", "checked_in"}:
                continue
            try:
                cin = datetime.fromisoformat(r.check_in).date()
            except Exception:
                continue
            if cin >= anchor:
                items.append(r)
        items.sort(key=lambda r: r.check_in)
        return {"status": "ok", "output": [self._res_summary(r) for r in items]}

    def get_amenities(self, hid: str) -> Dict:
        h = self.hotels.get(hid)
        if not h:
            return {"status": "failed", "output": f"hotel {hid} not found"}
        return {"status": "ok", "output": {"hid": hid, "amenities": list(h.amenities)}}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in RESERVATION_STATUSES}
        revenue = 0.0
        for r in self.reservations.values():
            by_status[r.status] = by_status.get(r.status, 0) + 1
            if r.status in {"booked", "checked_in", "checked_out"}:
                revenue += r.total_price
        return {
            "status": "ok",
            "output": {
                "hotels": len(self.hotels),
                "reservations": len(self.reservations),
                "by_status": by_status,
                "reviews": len(self.reviews),
                "booked_revenue": round(revenue, 2),
            },
        }
