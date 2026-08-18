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


def _to_float(v, default=0.0) -> float:
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0) -> int:
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class TicketmasterSession:
    """Deterministic sandbox for the Ticketmaster Discovery API v2 mock, ported from the FastAPI service.

    List responses use the {"_embedded": {...}, "page": {...}} shape. State is loaded
    from the corpus at init.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "ticketmaster.yaml") as f:
                info = yaml.safe_load(f)

            self.classifications: List[Dict[str, Any]] = [dict(c) for c in info.get("classifications", [])]
            self.venues: List[Dict[str, Any]] = [
                {**v, "latitude": _to_float(v.get("latitude"), 0.0), "longitude": _to_float(v.get("longitude"), 0.0)}
                for v in info.get("venues", [])
            ]
            self.attractions: List[Dict[str, Any]] = [
                {**a, "upcoming_events": _to_int(a.get("upcoming_events"), 0)}
                for a in info.get("attractions", [])
            ]
            self.events: List[Dict[str, Any]] = [
                {**e, "price_min": _to_float(e.get("price_min"), 0.0), "price_max": _to_float(e.get("price_max"), 0.0)}
                for e in info.get("events", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTicketmaster')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"events": self.events, "venues": self.venues}

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _find(store, obj_id):
        return next((x for x in store if x["id"] == obj_id), None)

    def _page(self, items, key):
        size = len(items)
        return {
            "_embedded": {key: items},
            "page": {"size": size, "totalElements": size, "totalPages": 1, "number": 0},
        }

    def _classification_obj(self, classification_id):
        c = self._find(self.classifications, classification_id)
        if not c:
            return None
        return {
            "segment": {"name": c["segment"]},
            "genre": {"name": c["genre"]},
            "subGenre": {"name": c["subgenre"]},
        }

    def _venue_obj(self, venue_id):
        v = self._find(self.venues, venue_id)
        if not v:
            return None
        return {
            "id": v["id"],
            "name": v["name"],
            "city": {"name": v["city"]},
            "state": {"stateCode": v["state"]},
            "country": {"countryCode": v["country"]},
            "postalCode": v["postal_code"],
            "address": {"line1": v["address"]},
            "location": {"latitude": v["latitude"], "longitude": v["longitude"]},
        }

    def _attraction_obj(self, attraction_id):
        a = self._find(self.attractions, attraction_id)
        if not a:
            return None
        return {
            "id": a["id"],
            "name": a["name"],
            "type": a["type"],
            "upcomingEvents": {"_total": a["upcoming_events"]},
            "classifications": [{
                "segment": {"name": a["segment"]},
                "genre": {"name": a["genre"]},
            }],
        }

    def _event_obj(self, e):
        cls = self._classification_obj(e["classification_id"])
        venue = self._venue_obj(e["venue_id"])
        attraction = self._attraction_obj(e["attraction_id"])
        embedded = {}
        if venue:
            embedded["venues"] = [venue]
        if attraction:
            embedded["attractions"] = [attraction]
        return {
            "id": e["id"],
            "name": e["name"],
            "dates": {"start": {"dateTime": e["start_datetime"]}, "status": {"code": e["status"]}},
            "classifications": [cls] if cls else [],
            "priceRanges": [{
                "type": "standard",
                "currency": e["currency"],
                "min": e["price_min"],
                "max": e["price_max"],
            }],
            "_embedded": embedded,
        }

    # --- events ------------------------------------------------------------
    def search_events(self, keyword: str | None = None, city: str | None = None,
                      classificationName: str | None = None,
                      startDateTime: str | None = None) -> Dict[str, Any]:
        results = list(self.events)
        if keyword:
            kw = keyword.lower()
            results = [e for e in results if kw in e["name"].lower()]
        if city:
            cl = city.lower()
            venue_ids = {v["id"] for v in self.venues if v["city"].lower() == cl}
            results = [e for e in results if e["venue_id"] in venue_ids]
        if classificationName:
            cn = classificationName.lower()
            cls_ids = {c["id"] for c in self.classifications
                       if cn in (c["segment"].lower(), c["genre"].lower(), c["subgenre"].lower())}
            results = [e for e in results if e["classification_id"] in cls_ids]
        if startDateTime:
            results = [e for e in results if e["start_datetime"] >= startDateTime]
        events = [self._event_obj(e) for e in results]
        return {"status": "ok", "output": self._page(events, "events")}

    def get_event(self, event_id: str) -> Dict[str, Any]:
        e = self._find(self.events, event_id)
        if not e:
            return {"status": "failed", "output": f"Event {event_id} not found"}
        return {"status": "ok", "output": self._event_obj(e)}

    # --- venues ------------------------------------------------------------
    def search_venues(self, keyword: str | None = None) -> Dict[str, Any]:
        results = list(self.venues)
        if keyword:
            kw = keyword.lower()
            results = [v for v in results if kw in v["name"].lower() or kw in v["city"].lower()]
        venues = [self._venue_obj(v["id"]) for v in results]
        return {"status": "ok", "output": self._page(venues, "venues")}

    def get_venue(self, venue_id: str) -> Dict[str, Any]:
        v = self._venue_obj(venue_id)
        if not v:
            return {"status": "failed", "output": f"Venue {venue_id} not found"}
        return {"status": "ok", "output": v}

    # --- attractions -------------------------------------------------------
    def search_attractions(self, keyword: str | None = None) -> Dict[str, Any]:
        results = list(self.attractions)
        if keyword:
            kw = keyword.lower()
            results = [a for a in results if kw in a["name"].lower()]
        attractions = [self._attraction_obj(a["id"]) for a in results]
        return {"status": "ok", "output": self._page(attractions, "attractions")}

    def get_attraction(self, attraction_id: str) -> Dict[str, Any]:
        a = self._attraction_obj(attraction_id)
        if not a:
            return {"status": "failed", "output": f"Attraction {attraction_id} not found"}
        return {"status": "ok", "output": a}

    # --- classifications ---------------------------------------------------
    def list_classifications(self) -> Dict[str, Any]:
        out = []
        for c in self.classifications:
            out.append({
                "id": c["id"],
                "segment": {
                    "name": c["segment"],
                    "_embedded": {"genres": [{
                        "name": c["genre"],
                        "_embedded": {"subgenres": [{"name": c["subgenre"]}]},
                    }]},
                },
            })
        return {"status": "ok", "output": self._page(out, "classifications")}


if __name__ == "__main__":
    s = TicketmasterSession(seed=12)
    print(s.search_events())
    print(s.list_classifications())
