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


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class AmadeusSession:
    """Deterministic sandbox for the Amadeus mock, ported from the FastAPI service.

    Mirrors a subset of the Amadeus Self-Service APIs: flight offers search,
    reference data for locations/airports and airlines, and offer pricing.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "amadeus.yaml") as f:
                info = yaml.safe_load(f)

            self.airports: List[Dict[str, Any]] = [
                {**a, "latitude": _to_float(a.get("latitude")), "longitude": _to_float(a.get("longitude"))}
                for a in info.get("airports", [])
            ]
            self.airlines: List[Dict[str, Any]] = list(info.get("airlines", []))
            self.offers: List[Dict[str, Any]] = list(info.get("flight_offers", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAmadeus')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"offers": self.offers}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _airport_by_code(self, code):
        return next((a for a in self.airports if a["iata_code"] == code), None)

    def _location_id(self, code):
        return f"A{code}"

    def _location_view(self, a):
        return {
            "type": "location",
            "subType": "AIRPORT",
            "id": self._location_id(a["iata_code"]),
            "name": a["name"],
            "iataCode": a["iata_code"],
            "address": {
                "cityName": a["city_name"],
                "cityCode": a["city_code"],
                "countryName": a["country_name"],
                "countryCode": a["country_code"],
            },
            "geoCode": {"latitude": a["latitude"], "longitude": a["longitude"]},
            "timeZone": {"offset": a["timezone"]},
        }

    def _public_offer(self, offer):
        out = dict(offer)
        out.pop("originLocationCode", None)
        out.pop("destinationLocationCode", None)
        out.pop("departureDate", None)
        return out

    def _get_offer(self, offer_id):
        return next((o for o in self.offers if o["id"] == str(offer_id)), None)

    # --- API methods -------------------------------------------------------
    def search_flight_offers(self, origin: str, destination: str, departure_date: str | None = None,
                             adults: int = 1, max_results: int = 50) -> Dict[str, Any]:
        matches = [
            o for o in self.offers
            if o["originLocationCode"] == origin and o["destinationLocationCode"] == destination
        ]
        if departure_date:
            matches = [o for o in matches if o["departureDate"] == departure_date]

        adults = max(1, int(adults or 1))
        data = []
        for o in matches[:max_results]:
            view = self._public_offer(o)
            base = float(o["price"]["base"])
            per_adult_total = float(o["price"]["total"])
            per_adult_fees = round(per_adult_total - base, 2)
            total = round(per_adult_total * adults, 2)
            view["price"] = {
                "currency": o["price"]["currency"],
                "total": f"{total:.2f}",
                "base": f"{round(base * adults, 2):.2f}",
                "grandTotal": f"{total:.2f}",
                "fees": [{"amount": f"{round(per_adult_fees * adults, 2):.2f}", "type": "SUPPLIER"}],
            }
            view["travelerPricings"] = [
                {
                    "travelerId": str(i + 1),
                    "fareOption": "STANDARD",
                    "travelerType": "ADULT",
                    "price": {"currency": o["price"]["currency"], "total": f"{per_adult_total:.2f}"},
                }
                for i in range(adults)
            ]
            data.append(view)

        return {"status": "ok", "output": {
            "meta": {"count": len(data)},
            "data": data,
            "dictionaries": {
                "carriers": {a["iata_code"]: a["business_name"] for a in self.airlines},
                "locations": {
                    a["iata_code"]: {"cityCode": a["city_code"], "countryCode": a["country_code"]}
                    for a in self.airports
                },
            },
        }}

    def price_flight_offer(self, offer: Dict[str, Any]) -> Dict[str, Any]:
        offer_id = str(offer.get("id", "")) if isinstance(offer, dict) else ""
        seeded = self._get_offer(offer_id) if offer_id else None
        if seeded:
            priced = self._public_offer(seeded)
        elif isinstance(offer, dict):
            priced = dict(offer)
        else:
            return {"status": "failed", "output": "Invalid flight offer payload"}
        return {"status": "ok", "output": {
            "data": {
                "type": "flight-offers-pricing",
                "flightOffers": [priced],
            }
        }}

    def search_locations(self, keyword: str | None = None, sub_type: str = "AIRPORT,CITY") -> Dict[str, Any]:
        types = [t.strip().upper() for t in (sub_type or "AIRPORT,CITY").split(",") if t.strip()]
        pool = self.airports
        if keyword:
            k = keyword.lower()
            pool = [
                a for a in pool
                if k in a["iata_code"].lower()
                or k in a["name"].lower()
                or k in a["city_name"].lower()
            ]
        data = []
        for a in pool:
            if "AIRPORT" in types:
                data.append(self._location_view(a))
            if "CITY" in types:
                city = self._location_view(a)
                city["subType"] = "CITY"
                city["id"] = f"C{a['city_code']}"
                city["name"] = a["city_name"]
                data.append(city)
        return {"status": "ok", "output": {"meta": {"count": len(data)}, "data": data}}

    def get_location(self, location_id: str) -> Dict[str, Any]:
        code = location_id[1:] if location_id and location_id[0] in ("A", "C") else location_id
        a = self._airport_by_code(code)
        if not a:
            a = next((x for x in self.airports if x["city_code"] == code), None)
        if not a:
            return {"status": "failed", "output": f"Location {location_id} not found"}
        return {"status": "ok", "output": {"data": self._location_view(a)}}

    def get_airlines(self, airline_codes: str | None = None) -> Dict[str, Any]:
        pool = self.airlines
        if airline_codes:
            codes = {c.strip().upper() for c in airline_codes.split(",") if c.strip()}
            pool = [a for a in pool if a["iata_code"] in codes]
        data = [
            {
                "type": "airline",
                "iataCode": a["iata_code"],
                "icaoCode": a["icao_code"],
                "businessName": a["business_name"],
                "commonName": a["common_name"],
            }
            for a in pool
        ]
        return {"status": "ok", "output": {"meta": {"count": len(data)}, "data": data}}


if __name__ == "__main__":
    s = AmadeusSession(seed=12)
    print(s.search_flight_offers("JFK", "LHR"))
    print(s.get_airlines("BA"))
