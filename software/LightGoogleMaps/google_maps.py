import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import math
from copy import deepcopy
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"

EARTH_RADIUS_M = 6371000.0  # mean Earth radius in meters
WALK_SPEED_MPS = 1.39       # ~5 km/h
DRIVE_SPEED_MPS = 13.4      # ~48 km/h (urban average)


def _strict_float(v) -> float:
    return float(v)


def _strict_int(v) -> int:
    return int(float(v))


def _opt_csv_list(v, sep="|") -> List[str]:
    if v is None:
        return []
    return [t.strip() for t in str(v).split(sep) if t.strip()]


class GoogleMapsSession:
    """Deterministic sandbox for the Google Maps mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "google_maps.yaml") as f:
                info = yaml.safe_load(f)

            self.places: List[Dict[str, Any]] = [
                {
                    "place_id": r["place_id"],
                    "name": r["name"],
                    "formatted_address": r["formatted_address"],
                    "geometry": {"location": {"lat": _strict_float(r["lat"]), "lng": _strict_float(r["lng"])}},
                    "rating": _strict_float(r["rating"]),
                    "user_ratings_total": _strict_int(r["user_ratings_total"]),
                    "types": [t for t in _opt_csv_list(r.get("types"), sep="|") if t],
                    "business_status": r["business_status"],
                    "price_level": _strict_int(r["price_level"]),
                }
                for r in info.get("places", [])
            ]
            self.geocodes: List[Dict[str, Any]] = [
                {
                    "query": r["query"],
                    "formatted_address": r["formatted_address"],
                    "lat": _strict_float(r["lat"]),
                    "lng": _strict_float(r["lng"]),
                    "place_id": r["place_id"],
                    "location_type": r["location_type"],
                }
                for r in info.get("geocodes", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGoogleMaps')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"places": self.places, "geocodes": self.geocodes}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _haversine_meters(self, lat1, lng1, lat2, lng2):
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return EARTH_RADIUS_M * c

    def _parse_latlng(self, value):
        if not value:
            return None
        parts = value.split(",")
        if len(parts) != 2:
            return None
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            return None

    def _resolve_point(self, value):
        ll = self._parse_latlng(value)
        if ll:
            return ll[0], ll[1], value
        v = value.strip().lower()
        for g in self.geocodes:
            if g["query"].lower() == v or g["formatted_address"].lower() == v:
                return g["lat"], g["lng"], g["formatted_address"]
        for p in self.places:
            if p["place_id"] == value or p["name"].lower() == v:
                loc = p["geometry"]["location"]
                return loc["lat"], loc["lng"], p["formatted_address"]
        for g in self.geocodes:
            if v in g["query"].lower() or v in g["formatted_address"].lower():
                return g["lat"], g["lng"], g["formatted_address"]
        return None

    def _fmt_distance(self, meters):
        if meters >= 1000:
            return {"text": f"{meters / 1000:.1f} km", "value": int(round(meters))}
        return {"text": f"{int(round(meters))} m", "value": int(round(meters))}

    def _fmt_duration(self, seconds):
        mins = max(1, int(round(seconds / 60)))
        return {"text": f"{mins} min", "value": int(round(seconds))}

    # --- API methods -------------------------------------------------------
    def text_search(self, query: str) -> Dict[str, Any]:
        results = list(self.places)
        if query:
            q = query.lower()
            results = [p for p in results
                       if q in p["name"].lower()
                       or q in p["formatted_address"].lower()
                       or any(q in t for t in p["types"])]
        return {"status": "ok", "output": {"status": "OK", "results": results}}

    def place_details(self, place_id: str) -> Dict[str, Any]:
        for p in self.places:
            if p["place_id"] == place_id:
                return {"status": "ok", "output": {"status": "OK", "result": p}}
        return {"status": "failed", "output": f"Place {place_id} not found"}

    def nearby_search(self, location: str, radius: int = 5000, place_type: str | None = None) -> Dict[str, Any]:
        point = self._resolve_point(location)
        if not point:
            return {"status": "failed", "output": f"Could not resolve location '{location}'"}
        lat0, lng0 = point[0], point[1]
        out = []
        for p in self.places:
            loc = p["geometry"]["location"]
            dist = self._haversine_meters(lat0, lng0, loc["lat"], loc["lng"])
            if dist <= radius and (not place_type or place_type in p["types"]):
                entry = deepcopy(p)
                entry["distance_meters"] = int(round(dist))
                out.append(entry)
        out.sort(key=lambda p: p["distance_meters"])
        return {"status": "ok", "output": {"status": "OK", "results": out}}

    def geocode(self, address: str) -> Dict[str, Any]:
        point = self._resolve_point(address)
        if not point:
            return {"status": "ok", "output": {"status": "ZERO_RESULTS", "results": []}}
        lat, lng, label = point
        place_id = "ChIJgeo-derived"
        location_type = "APPROXIMATE"
        for g in self.geocodes:
            if abs(g["lat"] - lat) < 1e-6 and abs(g["lng"] - lng) < 1e-6:
                place_id = g["place_id"]
                location_type = g["location_type"]
                break
        return {"status": "ok", "output": {
            "status": "OK",
            "results": [{
                "formatted_address": label,
                "geometry": {"location": {"lat": lat, "lng": lng}, "location_type": location_type},
                "place_id": place_id,
            }],
        }}

    def directions(self, origin: str, destination: str, mode: str = "driving") -> Dict[str, Any]:
        o = self._resolve_point(origin)
        d = self._resolve_point(destination)
        if not o or not d:
            return {"status": "failed", "output": "Could not resolve origin or destination"}
        olat, olng, olabel = o
        dlat, dlng, dlabel = d
        meters = self._haversine_meters(olat, olng, dlat, dlng)
        route_meters = meters * 1.3
        speed = WALK_SPEED_MPS if mode == "walking" else DRIVE_SPEED_MPS
        seconds = route_meters / speed
        leg = {
            "start_address": olabel,
            "end_address": dlabel,
            "start_location": {"lat": olat, "lng": olng},
            "end_location": {"lat": dlat, "lng": dlng},
            "distance": self._fmt_distance(route_meters),
            "duration": self._fmt_duration(seconds),
        }
        return {"status": "ok", "output": {
            "status": "OK",
            "routes": [{
                "summary": f"{olabel} to {dlabel}",
                "legs": [leg],
                "overview_polyline": {"points": "mock_polyline"},
            }],
        }}

    def distance_matrix(self, origins: List[str], destinations: List[str], mode: str = "driving") -> Dict[str, Any]:
        o_points = [(self._resolve_point(o), o) for o in origins]
        d_points = [(self._resolve_point(d), d) for d in destinations]
        speed = WALK_SPEED_MPS if mode == "walking" else DRIVE_SPEED_MPS

        origin_addresses = [p[0][2] if p[0] else p[1] for p in o_points]
        dest_addresses = [p[0][2] if p[0] else p[1] for p in d_points]

        rows = []
        for op, _ in o_points:
            elements = []
            for dp, _ in d_points:
                if not op or not dp:
                    elements.append({"status": "NOT_FOUND"})
                    continue
                meters = self._haversine_meters(op[0], op[1], dp[0], dp[1]) * 1.3
                elements.append({
                    "status": "OK",
                    "distance": self._fmt_distance(meters),
                    "duration": self._fmt_duration(meters / speed),
                })
            rows.append({"elements": elements})

        return {"status": "ok", "output": {
            "status": "OK",
            "origin_addresses": origin_addresses,
            "destination_addresses": dest_addresses,
            "rows": rows,
        }}


if __name__ == "__main__":
    s = GoogleMapsSession(seed=12)
    print(s.text_search("coffee"))
    print(s.geocode("oakland"))
