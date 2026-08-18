import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime, date

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"

SERVICE_FEE_PCT = 14.0  # guest service fee as percent of nightly subtotal


def _to_bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def _to_int(v) -> int:
    return int(str(v).strip())


def _to_float(v) -> float:
    return float(str(v).strip())


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class AirbnbSession:
    """Deterministic sandbox for the Airbnb mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "airbnb.yaml") as f:
                info = yaml.safe_load(f)

            self.listings: List[Dict[str, Any]] = [
                {
                    **l,
                    "price_per_night": _to_float(l["price_per_night"]),
                    "cleaning_fee": _to_float(l["cleaning_fee"]),
                    "beds": _to_int(l["beds"]),
                    "baths": _to_float(l["baths"]),
                    "max_guests": _to_int(l["max_guests"]),
                    "rating": _to_float(l["rating"]),
                    "review_count": _to_int(l["review_count"]),
                    "instant_book": _to_bool(l["instant_book"]),
                }
                for l in info.get("listings", [])
            ]
            self.hosts: List[Dict[str, Any]] = [
                {
                    **h,
                    "superhost": _to_bool(h["superhost"]),
                    "joined_year": _to_int(h["joined_year"]),
                    "response_rate": _to_int(h["response_rate"]),
                    "languages": [x.strip() for x in str(h.get("languages", "")).split(",") if x.strip() != ""],
                }
                for h in info.get("hosts", [])
            ]
            self.availability: List[Dict[str, Any]] = [
                {**a, "available": _to_bool(a["available"])}
                for a in info.get("availability", [])
            ]
            self.reviews: List[Dict[str, Any]] = [
                {**r, "rating": _to_int(r["rating"])}
                for r in info.get("reviews", [])
            ]
            self.reservations: List[Dict[str, Any]] = []
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAirbnb')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"reservations": self.reservations}

    # --- helpers -----------------------------------------------------------
    def _now_iso(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=10))

    def _new_id(self, prefix) -> str:
        return f"{prefix}-{self.uuid()}"

    def _get_host(self, host_id):
        return next((h for h in self.hosts if h["host_id"] == host_id), None)

    def _attach_host(self, listing):
        listing = dict(listing)
        listing["host"] = self._get_host(listing["host_id"])
        return listing

    def _is_available(self, listing_id, checkin, checkout):
        windows = [a for a in self.availability if a["listing_id"] == listing_id]
        covered = False
        for w in windows:
            ws, we = _parse_date(w["start_date"]), _parse_date(w["end_date"])
            if ws is None or we is None:
                continue
            overlaps = checkin < we and checkout > ws
            if not w["available"] and overlaps:
                return False
            if w["available"] and ws <= checkin and we >= checkout:
                covered = True
        return covered

    # --- API methods -------------------------------------------------------
    def search_listings(self, location=None, checkin=None, checkout=None, guests=None,
                        min_price=None, max_price=None) -> Dict[str, Any]:
        results = list(self.listings)
        if location:
            loc = location.lower()
            results = [l for l in results if loc in l["city"].lower() or loc in l["country"].lower()]
        if guests:
            results = [l for l in results if l["max_guests"] >= int(guests)]
        if min_price is not None:
            results = [l for l in results if l["price_per_night"] >= float(min_price)]
        if max_price is not None:
            results = [l for l in results if l["price_per_night"] <= float(max_price)]
        ci, co = _parse_date(checkin), _parse_date(checkout)
        if ci and co:
            results = [l for l in results if self._is_available(l["listing_id"], ci, co)]
        results = [self._attach_host(l) for l in results]
        results.sort(key=lambda l: l["rating"], reverse=True)
        return {"status": "ok", "output": {"count": len(results), "listings": results}}

    def get_listing(self, listing_id) -> Dict[str, Any]:
        for l in self.listings:
            if l["listing_id"] == listing_id:
                return {"status": "ok", "output": self._attach_host(l)}
        return {"status": "failed", "output": f"Listing {listing_id} not found"}

    def get_availability(self, listing_id) -> Dict[str, Any]:
        if not any(l["listing_id"] == listing_id for l in self.listings):
            return {"status": "failed", "output": f"Listing {listing_id} not found"}
        windows = [a for a in self.availability if a["listing_id"] == listing_id]
        return {"status": "ok", "output": {"listing_id": listing_id, "windows": windows}}

    def get_reviews(self, listing_id) -> Dict[str, Any]:
        if not any(l["listing_id"] == listing_id for l in self.listings):
            return {"status": "failed", "output": f"Listing {listing_id} not found"}
        revs = [r for r in self.reviews if r["listing_id"] == listing_id]
        return {"status": "ok", "output": {"listing_id": listing_id, "count": len(revs), "reviews": revs}}

    def create_reservation(self, listing_id, checkin, checkout, guests=1, guest_name="Guest") -> Dict[str, Any]:
        listing = next((l for l in self.listings if l["listing_id"] == listing_id), None)
        if not listing:
            return {"status": "failed", "output": f"Listing {listing_id} not found"}
        ci, co = _parse_date(checkin), _parse_date(checkout)
        if not ci or not co:
            return {"status": "failed", "output": "checkin and checkout must be ISO dates (YYYY-MM-DD)"}
        if co <= ci:
            return {"status": "failed", "output": "checkout must be after checkin"}
        if int(guests) > listing["max_guests"]:
            return {"status": "failed", "output": f"Guest count {guests} exceeds max_guests {listing['max_guests']}"}
        if not self._is_available(listing_id, ci, co):
            return {"status": "failed", "output": "Listing is not available for the requested dates"}

        nights = (co - ci).days
        nightly_subtotal = round(listing["price_per_night"] * nights, 2)
        cleaning_fee = listing["cleaning_fee"]
        service_fee = round(nightly_subtotal * SERVICE_FEE_PCT / 100, 2)
        total = round(nightly_subtotal + cleaning_fee + service_fee, 2)

        reservation = {
            "reservation_id": self._new_id("res"),
            "listing_id": listing_id,
            "guest_name": guest_name or "Guest",
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "guests": int(guests),
            "status": "confirmed",
            "nightly_subtotal": nightly_subtotal,
            "cleaning_fee": cleaning_fee,
            "service_fee": service_fee,
            "total": total,
            "created_at": self._now_iso(),
        }
        self.reservations.append(reservation)
        return {"status": "ok", "output": reservation}

    def get_reservation(self, reservation_id) -> Dict[str, Any]:
        found = next((r for r in self.reservations if r["reservation_id"] == reservation_id), None)
        if found is not None:
            return {"status": "ok", "output": found}
        return {"status": "failed", "output": f"Reservation {reservation_id} not found"}

    def cancel_reservation(self, reservation_id) -> Dict[str, Any]:
        existing = next((r for r in self.reservations if r["reservation_id"] == reservation_id), None)
        if existing is None:
            return {"status": "failed", "output": f"Reservation {reservation_id} not found"}
        if existing["status"] == "cancelled":
            return {"status": "failed", "output": f"Reservation {reservation_id} is already cancelled"}
        existing["status"] = "cancelled"
        return {"status": "ok", "output": existing}


if __name__ == "__main__":
    s = AirbnbSession(seed=12)
    print(s.search_listings())
    print(s.get_listing("lst-101"))
