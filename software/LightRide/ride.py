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


RIDE_STATUSES = ("requested", "accepted", "in_progress", "completed", "cancelled")
DEFAULT_CURRENCY = "USD"

SEED_DRIVERS = [
    ("Alice Chen",     "Toyota Camry",   "ABC-1234", 4.9, True),
    ("Bob Rivera",     "Honda Civic",    "XYZ-9911", 4.7, True),
    ("Carla Nguyen",   "Tesla Model 3",  "EV-2026",  4.8, False),
    ("Daniel Park",    "Ford Escape",    "FRD-5580", 4.5, True),
]

SEED_RIDERS = [
    ("self",   "123 Main St",   "500 Market St", ["Gym - 88 5th Ave", "Cafe Blue - 22 Oak"]),
    ("friend", "9 Elm Ave",     "Startup HQ - 1 Innovation Way", ["Airport SFO"]),
]

SEED_RIDES = [
    ("self",   "123 Main St",   "500 Market St",              5.2, 12.40, "completed",   -240, -230, -210, 5),
    ("self",   "500 Market St", "123 Main St",                5.4, 12.90, "completed",   -180, -170, -150, 4),
    ("friend", "9 Elm Ave",     "Airport SFO",               18.7, 42.30, "completed",   -720, -700, -650, 5),
    ("self",   "Gym - 88 5th Ave", "123 Main St",             3.1,  8.10, "in_progress", -20,  -10,  None,  0),
    ("friend", "Startup HQ - 1 Innovation Way", "9 Elm Ave", 11.0, 24.60, "accepted",    -5,   None, None,  0),
    ("self",   "Cafe Blue - 22 Oak", "500 Market St",         4.4, 10.20, "requested",    0,   None, None,  0),
]


@dataclass
class Driver:
    did: str
    name: str
    car_model: str
    license_plate: str
    rating: float
    is_available: bool


@dataclass
class Rider:
    ruid: str
    name: str
    home_address: str
    work_address: str
    saved_places: List[str] = field(default_factory=list)


@dataclass
class Ride:
    rid: str
    rider: str
    driver: str
    pickup: str
    dropoff: str
    distance_km: float
    fare: float
    currency: str
    status: str
    requested_at: str
    started_at: str = ""
    completed_at: str = ""
    rating: int = 0


class RideSession:
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
            self.drivers: Dict[str, Driver] = {}
            self.riders: Dict[str, Rider] = {}
            self.rides: Dict[str, Ride] = {}
            self._seed_drivers()
            self._seed_riders()
            self._seed_rides()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightRide')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_drivers(self) -> None:
        for name, car, plate, rating, avail in SEED_DRIVERS:
            d = Driver(
                did="drv_" + self.uuid()[:8],
                name=name,
                car_model=car,
                license_plate=plate,
                rating=rating,
                is_available=avail,
            )
            self.drivers[d.did] = d

    def _seed_riders(self) -> None:
        for name, home, work, saved in SEED_RIDERS:
            r = Rider(
                ruid="rid_" + self.uuid()[:8],
                name=name,
                home_address=home,
                work_address=work,
                saved_places=list(saved),
            )
            self.riders[r.ruid] = r

    def _pick_driver(self) -> str:
        avail = [d for d in self.drivers.values() if d.is_available]
        if not avail:
            return ""
        return self.rng.choice(avail).did

    def _seed_rides(self) -> None:
        driver_ids = list(self.drivers.keys())
        for rider, pickup, dropoff, dist, fare, status, req_off, start_off, done_off, rating in SEED_RIDES:
            req_at = (self._today + timedelta(minutes=req_off)).isoformat(timespec="minutes")
            if status == "requested":
                did = ""
                started = ""
                completed = ""
            else:
                did = self.rng.choice(driver_ids)
                started = (self._today + timedelta(minutes=start_off)).isoformat(timespec="minutes") if start_off is not None else ""
                completed = (self._today + timedelta(minutes=done_off)).isoformat(timespec="minutes") if done_off is not None else ""
            r = Ride(
                rid="ride_" + self.uuid()[:8],
                rider=rider,
                driver=did,
                pickup=pickup,
                dropoff=dropoff,
                distance_km=dist,
                fare=fare,
                currency=DEFAULT_CURRENCY,
                status=status,
                requested_at=req_at,
                started_at=started,
                completed_at=completed,
                rating=rating,
            )
            self.rides[r.rid] = r

    def get_session_dict(self) -> Dict:
        return {
            "drivers": {did: asdict(d) for did, d in self.drivers.items()},
            "riders":  {ruid: asdict(r) for ruid, r in self.riders.items()},
            "rides":   {rid: asdict(r) for rid, r in self.rides.items()},
        }

    def _ride_summary(self, r: Ride) -> Dict:
        return {
            "rid": r.rid,
            "rider": r.rider,
            "driver": r.driver,
            "pickup": r.pickup,
            "dropoff": r.dropoff,
            "status": r.status,
            "fare": r.fare,
            "currency": r.currency,
            "distance_km": r.distance_km,
        }

    def list_rides(self, status: Optional[str] = None, rider: Optional[str] = None) -> Dict:
        items = list(self.rides.values())
        if status:
            if status not in RIDE_STATUSES:
                return {"status": "failed", "output": f"status must be one of {RIDE_STATUSES}"}
            items = [r for r in items if r.status == status]
        if rider:
            items = [r for r in items if r.rider == rider]
        items.sort(key=lambda r: r.requested_at, reverse=True)
        return {"status": "ok", "output": [self._ride_summary(r) for r in items]}

    def get_ride(self, rid: str) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        return {"status": "ok", "output": asdict(r)}

    def request_ride(self, rider: str, pickup: str, dropoff: str) -> Dict:
        r = Ride(
            rid="ride_" + self.uuid()[:8],
            rider=rider,
            driver="",
            pickup=pickup,
            dropoff=dropoff,
            distance_km=0.0,
            fare=0.0,
            currency=DEFAULT_CURRENCY,
            status="requested",
            requested_at=self._now(),
        )
        self.rides[r.rid] = r
        return {"status": "ok", "output": self._ride_summary(r)}

    def accept_ride(self, rid: str, did: str) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        if r.status != "requested":
            return {"status": "failed", "output": f"ride {rid} is not requested (status={r.status})"}
        d = self.drivers.get(did)
        if not d:
            return {"status": "failed", "output": f"driver {did} not found"}
        if not d.is_available:
            return {"status": "failed", "output": f"driver {did} not available"}
        r.driver = did
        r.status = "accepted"
        d.is_available = False
        return {"status": "ok", "output": self._ride_summary(r)}

    def start_ride(self, rid: str) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        if r.status != "accepted":
            return {"status": "failed", "output": f"ride {rid} not accepted (status={r.status})"}
        r.status = "in_progress"
        r.started_at = self._now()
        return {"status": "ok", "output": self._ride_summary(r)}

    def complete_ride(self, rid: str, fare: float) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        if r.status != "in_progress":
            return {"status": "failed", "output": f"ride {rid} not in progress (status={r.status})"}
        r.status = "completed"
        r.completed_at = self._now()
        r.fare = fare
        if r.driver in self.drivers:
            self.drivers[r.driver].is_available = True
        return {"status": "ok", "output": self._ride_summary(r)}

    def cancel_ride(self, rid: str) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        if r.status in {"completed", "cancelled"}:
            return {"status": "failed", "output": f"ride {rid} cannot be cancelled (status={r.status})"}
        r.status = "cancelled"
        if r.driver in self.drivers:
            self.drivers[r.driver].is_available = True
        return {"status": "ok", "output": self._ride_summary(r)}

    def rate_ride(self, rid: str, rating: int) -> Dict:
        r = self.rides.get(rid)
        if not r:
            return {"status": "failed", "output": f"ride {rid} not found"}
        if r.status != "completed":
            return {"status": "failed", "output": f"ride {rid} must be completed to rate"}
        if not 1 <= rating <= 5:
            return {"status": "failed", "output": "rating must be 1..5"}
        r.rating = rating
        return {"status": "ok", "output": self._ride_summary(r)}

    def list_drivers(self, is_available: Optional[bool] = None) -> Dict:
        items = list(self.drivers.values())
        if is_available is not None:
            items = [d for d in items if d.is_available == is_available]
        return {"status": "ok", "output": [asdict(d) for d in items]}

    def get_driver(self, did: str) -> Dict:
        d = self.drivers.get(did)
        if not d:
            return {"status": "failed", "output": f"driver {did} not found"}
        return {"status": "ok", "output": asdict(d)}

    def add_driver(self, name: str, car_model: str, license_plate: str,
                   rating: float = 5.0, is_available: bool = True) -> Dict:
        d = Driver(
            did="drv_" + self.uuid()[:8],
            name=name,
            car_model=car_model,
            license_plate=license_plate,
            rating=rating,
            is_available=is_available,
        )
        self.drivers[d.did] = d
        return {"status": "ok", "output": asdict(d)}

    def list_riders(self) -> Dict:
        return {"status": "ok", "output": [asdict(r) for r in self.riders.values()]}

    def add_rider(self, name: str, home_address: str = "", work_address: str = "") -> Dict:
        r = Rider(
            ruid="rid_" + self.uuid()[:8],
            name=name,
            home_address=home_address,
            work_address=work_address,
            saved_places=[],
        )
        self.riders[r.ruid] = r
        return {"status": "ok", "output": asdict(r)}

    def add_saved_place(self, ruid: str, place: str) -> Dict:
        r = self.riders.get(ruid)
        if not r:
            return {"status": "failed", "output": f"rider {ruid} not found"}
        if place not in r.saved_places:
            r.saved_places.append(place)
        return {"status": "ok", "output": asdict(r)}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in RIDE_STATUSES}
        total_fare = 0.0
        completed = 0
        rating_sum = 0
        rating_count = 0
        for r in self.rides.values():
            by_status[r.status] = by_status.get(r.status, 0) + 1
            if r.status == "completed":
                total_fare += r.fare
                completed += 1
                if r.rating:
                    rating_sum += r.rating
                    rating_count += 1
        avg_rating = (rating_sum / rating_count) if rating_count else 0.0
        return {
            "status": "ok",
            "output": {
                "total_rides": len(self.rides),
                "by_status": by_status,
                "drivers": len(self.drivers),
                "riders": len(self.riders),
                "total_completed_fare": round(total_fare, 2),
                "avg_rating": round(avg_rating, 2),
            },
        }
