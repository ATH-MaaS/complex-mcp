import random
import math
from copy import deepcopy
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
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    return int(str(v).strip())


def _to_float(v) -> float:
    return float(str(v).strip())


_DRIVERS = [
    ("Sofia Marquez", "Toyota Corolla White", "4DRV883"),
    ("Daniel Osei", "Hyundai Sonata Gray", "6CAB220"),
    ("Mei Tanaka", "Tesla Model 3 Black", "8EVX771"),
]


class UberSession:
    """Deterministic sandbox for the Uber Rides API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "uber.yaml") as f:
                info = yaml.safe_load(f)

            self.products: List[Dict[str, Any]] = [
                {
                    **p,
                    "capacity": _to_int(p["capacity"]),
                    "base_fare": _to_float(p["base_fare"]),
                    "cost_per_mile": _to_float(p["cost_per_mile"]),
                    "cost_per_minute": _to_float(p["cost_per_minute"]),
                    "booking_fee": _to_float(p["booking_fee"]),
                    "minimum_fare": _to_float(p["minimum_fare"]),
                    "shared": _to_bool(p["shared"]),
                }
                for p in info.get("products", [])
            ]
            self.trips: List[Dict[str, Any]] = [
                {
                    **t,
                    "start_latitude": _to_float(t["start_latitude"]),
                    "start_longitude": _to_float(t["start_longitude"]),
                    "end_latitude": _to_float(t["end_latitude"]),
                    "end_longitude": _to_float(t["end_longitude"]),
                    "distance_miles": _to_float(t["distance_miles"]),
                    "duration_minutes": _to_float(t["duration_minutes"]),
                    "fare": _to_float(t["fare"]),
                    "surge_multiplier": _to_float(t["surge_multiplier"]),
                    "driver_name": (str(t.get("driver_name") or "") or None),
                    "vehicle": (str(t.get("vehicle") or "") or None),
                    "license_plate": (str(t.get("license_plate") or "") or None),
                    "completed_at": (str(t.get("completed_at") or "") or None),
                }
                for t in info.get("trips", [])
            ]
            self.rider: Dict[str, Any] = dict(info.get("rider", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightUber')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"trips": self.trips}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _haversine_miles(self, lat1, lon1, lat2, lon2):
        radius_miles = 3958.8
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (math.sin(dphi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_miles * c

    def _estimate_minutes(self, distance_miles):
        return round(distance_miles / 18.0 * 60.0 + 2.0, 1)

    # --- Products ----------------------------------------------------------
    def list_products(self, latitude=None, longitude=None) -> Dict[str, Any]:
        return {"status": "ok", "output": {"products": deepcopy(self.products)}}

    def get_product(self, product_id: str) -> Dict[str, Any]:
        for p in self.products:
            if p["product_id"] == product_id:
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": f"Product {product_id} not found"}

    # --- Estimates ---------------------------------------------------------
    def price_estimates(self, start_latitude, start_longitude, end_latitude, end_longitude) -> Dict[str, Any]:
        distance = self._haversine_miles(start_latitude, start_longitude,
                                         end_latitude, end_longitude)
        duration = self._estimate_minutes(distance)
        prices = []
        for p in self.products:
            raw = (p["base_fare"] + p["booking_fee"]
                   + p["cost_per_mile"] * distance
                   + p["cost_per_minute"] * duration)
            low = max(raw, p["minimum_fare"])
            high = low * 1.25
            prices.append({
                "product_id": p["product_id"],
                "display_name": p["display_name"],
                "currency_code": "USD",
                "distance": round(distance, 2),
                "duration": int(round(duration * 60)),
                "estimate": f"${low:.2f}-{high:.2f}",
                "low_estimate": round(low, 2),
                "high_estimate": round(high, 2),
                "surge_multiplier": 1.0,
            })
        return {"status": "ok", "output": {"prices": prices}}

    def time_estimates(self, start_latitude, start_longitude, product_id=None) -> Dict[str, Any]:
        times = []
        for p in self.products:
            if product_id and p["product_id"] != product_id:
                continue
            eta_minutes = {"uberx": 3, "uberxl": 5, "uberblack": 8, "uberpool": 4}.get(
                p["product_id"], 4)
            times.append({
                "product_id": p["product_id"],
                "display_name": p["display_name"],
                "estimate": eta_minutes * 60,
            })
        return {"status": "ok", "output": {"times": times}}

    # --- Ride requests / trips ---------------------------------------------
    def create_request(self, product_id, start_latitude, start_longitude,
                       end_latitude=None, end_longitude=None, rider_id=None) -> Dict[str, Any]:
        product = next((p for p in self.products if p["product_id"] == product_id), None)
        if not product:
            return {"status": "failed", "output": f"Product {product_id} not found"}

        distance = duration = fare = 0.0
        if end_latitude is not None and end_longitude is not None:
            distance = self._haversine_miles(start_latitude, start_longitude,
                                            end_latitude, end_longitude)
            duration = self._estimate_minutes(distance)
            raw = (product["base_fare"] + product["booking_fee"]
                   + product["cost_per_mile"] * distance
                   + product["cost_per_minute"] * duration)
            fare = round(max(raw, product["minimum_fare"]), 2)

        driver_name, vehicle, plate = _DRIVERS[len(self.trips) % len(_DRIVERS)]
        trip = {
            "request_id": self._new_id("req"),
            "product_id": product_id,
            "status": "processing",
            "rider_id": rider_id or self.rider["rider_id"],
            "driver_name": driver_name,
            "vehicle": vehicle,
            "license_plate": plate,
            "start_latitude": start_latitude,
            "start_longitude": start_longitude,
            "start_address": "",
            "end_latitude": end_latitude if end_latitude is not None else 0.0,
            "end_longitude": end_longitude if end_longitude is not None else 0.0,
            "end_address": "",
            "distance_miles": round(distance, 2),
            "duration_minutes": duration,
            "fare": fare,
            "surge_multiplier": 1.0,
            "eta_minutes": 3,
            "requested_at": self._now(),
            "completed_at": None,
        }
        self.trips.append(trip)
        return {"status": "ok", "output": trip}

    def get_request(self, request_id: str) -> Dict[str, Any]:
        for t in self.trips:
            if t["request_id"] == request_id:
                return {"status": "ok", "output": t}
        return {"status": "failed", "output": f"Request {request_id} not found"}

    def cancel_request(self, request_id: str) -> Dict[str, Any]:
        for i, t in enumerate(self.trips):
            if t["request_id"] == request_id:
                if t["status"] in {"completed", "canceled_rider", "canceled_driver"}:
                    return {"status": "failed", "output": f"Request {request_id} cannot be canceled (status: {t['status']})"}
                self.trips[i]["status"] = "canceled_rider"
                return {"status": "ok", "output": self.trips[i]}
        return {"status": "failed", "output": f"Request {request_id} not found"}

    def get_history(self, rider_id=None, limit=50, offset=0) -> Dict[str, Any]:
        results = [t for t in self.trips if t["completed_at"]]
        if rider_id:
            results = [t for t in results if t["rider_id"] == rider_id]
        results.sort(key=lambda t: t["requested_at"], reverse=True)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "count": len(results),
            "limit": limit,
            "offset": offset,
            "history": page,
        }}

    # --- Rider profile -----------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.rider}


if __name__ == "__main__":
    s = UberSession(seed=12)
    print(s.list_products())
    print(s.get_me())
