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


class DoordashSession:
    """Deterministic sandbox for the DoorDash mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    SERVICE_FEE_PCT = 10.0  # percent of subtotal

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "doordash.yaml") as f:
                info = yaml.safe_load(f)

            self.stores: List[Dict[str, Any]] = [
                {
                    **s,
                    "rating": float(s["rating"]),
                    "review_count": int(s["review_count"]),
                    "delivery_fee": float(s["delivery_fee"]),
                    "eta_minutes": int(s["eta_minutes"]),
                    "latitude": float(s["latitude"]),
                    "longitude": float(s["longitude"]),
                    "is_open": _to_bool(s["is_open"]),
                }
                for s in info.get("stores", [])
            ]
            self.menu_items: List[Dict[str, Any]] = [
                {
                    **i,
                    "price": float(i["price"]),
                    "calories": int(i["calories"]),
                    "popular": _to_bool(i["popular"]),
                    "available": _to_bool(i["available"]),
                }
                for i in info.get("menu_items", [])
            ]
            self.orders: List[Dict[str, Any]] = [
                {
                    **o,
                    "subtotal": float(o["subtotal"]),
                    "delivery_fee": float(o["delivery_fee"]),
                    "service_fee": float(o["service_fee"]),
                    "tip": float(o["tip"]),
                    "total": float(o["total"]),
                }
                for o in info.get("orders", [])
            ]
            self.order_items: List[Dict[str, Any]] = [
                {
                    **r,
                    "quantity": int(r["quantity"]),
                    "unit_price": float(r["unit_price"]),
                    "line_total": float(r["line_total"]),
                }
                for r in info.get("order_items", [])
            ]

            self.carts: Dict[str, Any] = {}
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightDoorDash')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"orders": self.orders}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _get_item(self, item_id):
        return next((i for i in self.menu_items if i["item_id"] == item_id), None)

    def _cart_with_totals(self, cart_id):
        cart = self.carts.get(cart_id)
        if not cart:
            return {"error": f"Cart {cart_id} not found"}
        store = next(s for s in self.stores if s["store_id"] == cart["store_id"])
        subtotal = 0.0
        detailed = []
        for it in cart["items"]:
            item = self._get_item(it["item_id"])
            if not item:
                continue
            line_total = round(item["price"] * it["quantity"], 2)
            subtotal += line_total
            detailed.append({
                "item_id": item["item_id"],
                "name": item["name"],
                "quantity": it["quantity"],
                "unit_price": item["price"],
                "line_total": line_total,
            })
        service_fee = round(subtotal * self.SERVICE_FEE_PCT / 100, 2)
        delivery_fee = store["delivery_fee"]
        return {
            **cart,
            "items": detailed,
            "subtotal": round(subtotal, 2),
            "delivery_fee": delivery_fee,
            "service_fee": service_fee,
            "estimated_total": round(subtotal + delivery_fee + service_fee, 2),
        }

    def _get_order(self, order_id):
        for o in self.orders:
            if o["order_id"] == order_id:
                items = [i for i in self.order_items if i["order_id"] == order_id]
                return {**o, "items": items}
        return {"error": f"Order {order_id} not found"}

    # --- API methods -------------------------------------------------------
    def list_stores(self, latitude: float | None = None, longitude: float | None = None,
                    cuisine: str | None = None, open_only: bool = False) -> Dict[str, Any]:
        results = list(self.stores)
        if cuisine:
            results = [s for s in results if s["cuisine"].lower() == cuisine.lower()]
        if open_only:
            results = [s for s in results if s["is_open"]]
        results.sort(key=lambda s: s["rating"], reverse=True)
        return {"status": "ok", "output": {"count": len(results), "stores": results}}

    def get_store(self, store_id: str) -> Dict[str, Any]:
        for s in self.stores:
            if s["store_id"] == store_id:
                return {"status": "ok", "output": s}
        return {"status": "failed", "output": f"Store {store_id} not found"}

    def get_menu(self, store_id: str) -> Dict[str, Any]:
        if not any(s["store_id"] == store_id for s in self.stores):
            return {"status": "failed", "output": f"Store {store_id} not found"}
        items = [i for i in self.menu_items if i["store_id"] == store_id]
        categories = {}
        for it in items:
            categories.setdefault(it["category"], []).append(it)
        return {"status": "ok", "output": {
            "store_id": store_id,
            "categories": [
                {"name": name, "items": cat_items}
                for name, cat_items in categories.items()
            ],
            "items": items,
        }}

    def create_cart(self, store_id: str) -> Dict[str, Any]:
        store = next((s for s in self.stores if s["store_id"] == store_id), None)
        if not store:
            return {"status": "failed", "output": f"Store {store_id} not found"}
        cart_id = self._new_id("cart")
        self.carts[cart_id] = {
            "cart_id": cart_id,
            "store_id": store_id,
            "items": [],
            "created_at": self._now(),
        }
        return {"status": "ok", "output": self._cart_with_totals(cart_id)}

    def get_cart(self, cart_id: str) -> Dict[str, Any]:
        result = self._cart_with_totals(cart_id)
        if "error" in result:
            return {"status": "failed", "output": result["error"]}
        return {"status": "ok", "output": result}

    def add_cart_item(self, cart_id: str, item_id: str, quantity: int = 1) -> Dict[str, Any]:
        cart = self.carts.get(cart_id)
        if not cart:
            return {"status": "failed", "output": f"Cart {cart_id} not found"}
        item = self._get_item(item_id)
        if not item:
            return {"status": "failed", "output": f"Menu item {item_id} not found"}
        if item["store_id"] != cart["store_id"]:
            return {"status": "failed", "output": "Item belongs to a different store than the cart"}
        if not item["available"]:
            return {"status": "failed", "output": f"Menu item {item_id} is currently unavailable"}
        for it in cart["items"]:
            if it["item_id"] == item_id:
                it["quantity"] += quantity
                return {"status": "ok", "output": self._cart_with_totals(cart_id)}
        cart["items"].append({"item_id": item_id, "quantity": quantity})
        return {"status": "ok", "output": self._cart_with_totals(cart_id)}

    def checkout(self, cart_id: str, customer_name: str = "Guest", tip: float = 0.0) -> Dict[str, Any]:
        cart_full = self._cart_with_totals(cart_id)
        if "error" in cart_full:
            return {"status": "failed", "output": cart_full["error"]}
        if not cart_full["items"]:
            return {"status": "failed", "output": "Cart is empty"}
        order_id = self._new_id("order")
        order = {
            "order_id": order_id,
            "store_id": cart_full["store_id"],
            "customer_name": customer_name,
            "status": "confirmed",
            "subtotal": cart_full["subtotal"],
            "delivery_fee": cart_full["delivery_fee"],
            "service_fee": cart_full["service_fee"],
            "tip": float(tip),
            "total": round(cart_full["estimated_total"] + float(tip), 2),
            "placed_at": self._now(),
            "dasher_name": "",
        }
        self.orders.append(order)
        for it in cart_full["items"]:
            self.order_items.append({
                "order_id": order_id,
                "item_id": it["item_id"],
                "quantity": it["quantity"],
                "unit_price": it["unit_price"],
                "line_total": it["line_total"],
            })
        self.carts.pop(cart_id, None)
        return {"status": "ok", "output": self._get_order(order_id)}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        result = self._get_order(order_id)
        if "error" in result:
            return {"status": "failed", "output": result["error"]}
        return {"status": "ok", "output": result}


if __name__ == "__main__":
    s = DoordashSession(seed=12)
    print(s.list_stores())
    print(s.get_menu("store-sakura"))
