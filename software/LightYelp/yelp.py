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


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_PRICE_LEVEL = {"$": 1, "$$": 2, "$$$": 3, "$$$$": 4}


class YelpSession:
    """Deterministic sandbox for the Yelp Fusion API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "yelp.yaml") as f:
                info = yaml.safe_load(f)

            self.businesses: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "alias": r["id"],
                    "name": r["name"],
                    "rating": _to_float(r.get("rating")),
                    "price": r["price"],
                    "review_count": _to_int(r.get("review_count")),
                    "is_closed": _to_bool(r.get("is_closed")),
                    "phone": r["phone"],
                    "image_url": r["image_url"],
                    "categories": [{"alias": r["category"], "title": r["category_title"]}],
                    "coordinates": {"latitude": _to_float(r.get("latitude")), "longitude": _to_float(r.get("longitude"))},
                    "location": {
                        "address1": r["address"],
                        "city": r["city"],
                        "state": r["state"],
                        "display_address": [r["address"], f"{r['city']}, {r['state']}"],
                    },
                }
                for r in info.get("businesses", [])
            ]
            self.reviews: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "business_id": r["business_id"],
                    "rating": _to_int(r.get("rating")),
                    "text": r["text"],
                    "time_created": r["time_created"],
                    "user": {"name": r["user_name"]},
                }
                for r in info.get("reviews", [])
            ]
            self.categories: List[Dict[str, Any]] = [
                {"alias": r["alias"], "title": r["title"], "parent_aliases": [r["parent"]]}
                for r in info.get("categories", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightYelp')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"businesses": self.businesses}

    def _now(self) -> str:
        return self.os.now()

    # --- Businesses --------------------------------------------------------
    def search_businesses(self, term: str | None = None, location: str | None = None,
                          categories: str | None = None, price: str | None = None,
                          sort_by: str = "best_match", limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        results = list(self.businesses)
        if term:
            t = term.lower()
            results = [b for b in results
                       if t in b["name"].lower()
                       or any(t in c["title"].lower() or t in c["alias"].lower() for c in b["categories"])]
        if location:
            loc = location.lower()
            results = [b for b in results
                       if loc in b["location"]["city"].lower()
                       or loc in b["location"]["state"].lower()
                       or loc in b["location"]["address1"].lower()]
        if categories:
            wanted = {c.strip().lower() for c in categories.split(",") if c.strip()}
            results = [b for b in results
                       if any(c["alias"].lower() in wanted for c in b["categories"])]
        if price:
            wanted_levels = set()
            for p in price.split(","):
                p = p.strip()
                if p.isdigit():
                    wanted_levels.add(int(p))
                elif p in _PRICE_LEVEL:
                    wanted_levels.add(_PRICE_LEVEL[p])
            results = [b for b in results if _PRICE_LEVEL.get(b["price"], 0) in wanted_levels]

        if sort_by == "rating":
            results.sort(key=lambda b: b["rating"], reverse=True)
        elif sort_by == "review_count":
            results.sort(key=lambda b: b["review_count"], reverse=True)

        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "total": total, "businesses": page,
            "region": {"center": {"latitude": 37.7749, "longitude": -122.4194}}}}

    def get_business(self, business_id: str) -> Dict[str, Any]:
        for b in self.businesses:
            if b["id"] == business_id or b["alias"] == business_id:
                return {"status": "ok", "output": b}
        return {"status": "failed", "output": f"Business {business_id} not found"}

    def get_business_reviews(self, business_id: str) -> Dict[str, Any]:
        if not any(b["id"] == business_id or b["alias"] == business_id for b in self.businesses):
            return {"status": "failed", "output": f"Business {business_id} not found"}
        reviews = [r for r in self.reviews if r["business_id"] == business_id]
        return {"status": "ok", "output": {
            "total": len(reviews), "reviews": reviews, "possible_languages": ["en"]}}

    # --- Categories --------------------------------------------------------
    def list_categories(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"categories": list(self.categories)}}


if __name__ == "__main__":
    s = YelpSession(seed=12)
    print(s.search_businesses())
    print(s.list_categories())
