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


def _opt_str(v):
    s = "" if v is None else str(v)
    return s or None


class ZillowSession:
    """Deterministic sandbox for the Zillow API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "zillow.yaml") as f:
                info = yaml.safe_load(f)

            self.properties: List[Dict[str, Any]] = [{
                **r,
                "zpid": _to_int(r.get("zpid")),
                "latitude": _to_float(r.get("latitude")),
                "longitude": _to_float(r.get("longitude")),
                "bedrooms": _to_int(r.get("bedrooms")),
                "bathrooms": _to_float(r.get("bathrooms")),
                "living_area_sqft": _to_int(r.get("living_area_sqft")),
                "lot_size_sqft": _to_int(r.get("lot_size_sqft")),
                "year_built": _to_int(r.get("year_built")),
                "list_price": _to_int(r.get("list_price")),
                "zestimate": _to_int(r.get("zestimate")),
                "rent_zestimate": _to_int(r.get("rent_zestimate")),
                "days_on_zillow": _to_int(r.get("days_on_zillow")),
            } for r in info.get("properties", [])]
            self.price_history: List[Dict[str, Any]] = [{
                **r,
                "zpid": _to_int(r.get("zpid")),
                "price": _to_float(r.get("price")),
                "price_per_sqft": _to_float(r.get("price_per_sqft")),
            } for r in info.get("price_history", [])]
            self.agents: List[Dict[str, Any]] = [{
                **r,
                "active_listings": _to_int(r.get("active_listings")),
                "sold_last_12mo": _to_int(r.get("sold_last_12mo")),
                "rating": _to_float(r.get("rating")),
                "reviews": _to_int(r.get("reviews")),
            } for r in info.get("agents", [])]
            self.saved_searches: List[Dict[str, Any]] = [{
                **r,
                "min_price": _to_int(r.get("min_price")),
                "max_price": _to_int(r.get("max_price")),
                "min_beds": _to_int(r.get("min_beds")),
                "min_baths": _to_float(r.get("min_baths")),
                "city": _opt_str(r.get("city")),
            } for r in info.get("saved_searches", [])]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightZillow')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"saved_searches": self.saved_searches}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()[:10]

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_search_id(self) -> str:
        return f"search-{self.uuid()}"

    # --- Properties --------------------------------------------------------
    def search_properties(self, city: str | None = None, state: str | None = None,
                          zipcode: str | None = None, min_price: int | None = None,
                          max_price: int | None = None, min_beds: int | None = None,
                          min_baths: float | None = None, home_type: str | None = None,
                          status: str = "FOR_SALE", limit: int = 25, offset: int = 0,
                          sort_by: str = "list_price", sort_order: str = "asc") -> Dict[str, Any]:
        results = list(self.properties)
        if status:
            results = [p for p in results if p["status"].upper() == status.upper()]
        if city:
            results = [p for p in results if p["city"].lower() == city.lower()]
        if state:
            results = [p for p in results if p["state"].upper() == state.upper()]
        if zipcode:
            results = [p for p in results if p["zipcode"] == zipcode]
        if min_price is not None:
            results = [p for p in results if p["list_price"] >= min_price]
        if max_price is not None:
            results = [p for p in results if p["list_price"] <= max_price]
        if min_beds is not None:
            results = [p for p in results if p["bedrooms"] >= min_beds]
        if min_baths is not None:
            results = [p for p in results if p["bathrooms"] >= min_baths]
        if home_type:
            results = [p for p in results if p["home_type"].lower() == home_type.lower()]

        sort_key = sort_by if sort_by in {"list_price", "zestimate", "days_on_zillow", "living_area_sqft"} else "list_price"
        reverse = sort_order.lower() == "desc"
        results.sort(key=lambda p: p[sort_key], reverse=reverse)

        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "total": total,
            "count": len(page),
            "offset": offset,
            "limit": limit,
            "results": page,
        }}

    def get_property(self, zpid: int) -> Dict[str, Any]:
        for p in self.properties:
            if p["zpid"] == int(zpid):
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": f"Property {zpid} not found"}

    def get_zestimate(self, zpid: int) -> Dict[str, Any]:
        p = next((x for x in self.properties if x["zpid"] == int(zpid)), None)
        if not p:
            return {"status": "failed", "output": f"Property {zpid} not found"}
        return {"status": "ok", "output": {
            "zpid": p["zpid"],
            "address": p["address"],
            "zestimate": p["zestimate"],
            "rent_zestimate": p["rent_zestimate"],
            "list_price": p["list_price"],
            "delta_pct": round((p["zestimate"] - p["list_price"]) / p["list_price"] * 100, 2),
        }}

    def get_price_history(self, zpid: int) -> Dict[str, Any]:
        zpid = int(zpid)
        if not any(p["zpid"] == zpid for p in self.properties):
            return {"status": "failed", "output": f"Property {zpid} not found"}
        events = [e for e in self.price_history if e["zpid"] == zpid]
        events.sort(key=lambda e: e["event_date"], reverse=True)
        return {"status": "ok", "output": {"zpid": zpid, "count": len(events), "history": events}}

    # --- Agents ------------------------------------------------------------
    def list_agents(self, city: str | None = None, state: str | None = None) -> Dict[str, Any]:
        if not city and not state:
            return {"status": "ok", "output": {"count": len(self.agents), "agents": list(self.agents)}}
        matching_ids = set()
        for p in self.properties:
            if city and p["city"].lower() != city.lower():
                continue
            if state and p["state"].upper() != state.upper():
                continue
            matching_ids.add(p["listing_agent_id"])
        agents = [a for a in self.agents if a["agent_id"] in matching_ids]
        return {"status": "ok", "output": {"count": len(agents), "agents": agents}}

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        for a in self.agents:
            if a["agent_id"] == agent_id:
                listings = [p for p in self.properties
                            if p["listing_agent_id"] == agent_id and p["status"] == "FOR_SALE"]
                return {"status": "ok", "output": {**a, "listings": listings}}
        return {"status": "failed", "output": f"Agent {agent_id} not found"}

    # --- Saved searches ----------------------------------------------------
    def list_saved_searches(self, user_id: str) -> Dict[str, Any]:
        results = [s for s in self.saved_searches if s["user_id"] == user_id]
        return {"status": "ok", "output": {"count": len(results), "results": results}}

    def create_saved_search(self, user_id: str, name: str, city: str | None = None,
                            state: str | None = None, min_price: int = 0, max_price: int = 10000000,
                            min_beds: int = 0, min_baths: float = 0.0, home_type: str = "") -> Dict[str, Any]:
        search = {
            "search_id": self._new_search_id(),
            "user_id": user_id,
            "name": name,
            "city": city or None,
            "state": state or "",
            "min_price": int(min_price),
            "max_price": int(max_price),
            "min_beds": int(min_beds),
            "min_baths": float(min_baths),
            "home_type": home_type or "",
            "created_at": self._now(),
        }
        self.saved_searches.append(search)
        return {"status": "ok", "output": search}

    def delete_saved_search(self, search_id: str) -> Dict[str, Any]:
        for i, s in enumerate(self.saved_searches):
            if s["search_id"] == search_id:
                self.saved_searches.pop(i)
                return {"status": "ok", "output": {"deleted": True, "search_id": search_id}}
        return {"status": "failed", "output": f"Saved search {search_id} not found"}


if __name__ == "__main__":
    s = ZillowSession(seed=12)
    print(s.search_properties())
    print(s.list_agents())
