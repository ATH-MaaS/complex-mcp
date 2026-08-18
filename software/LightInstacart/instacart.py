import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"

_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}


def _strict_float(v) -> float:
    return float(str(v).strip())


def _strict_int(v) -> int:
    return int(str(v).strip())


def _strict_bool(v) -> bool:
    token = str(v).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return False


def _opt_float(v, default=None):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_str(v, default="") -> str:
    if v is None:
        return default
    return str(v)


def _opt_csv_list(v, sep=",") -> List[str]:
    if v is None or str(v).strip() == "":
        return []
    return [part for part in str(v).split(sep)]


class InstacartSession:
    """Deterministic sandbox for the Instacart mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "instacart.yaml") as f:
                info = yaml.safe_load(f)

            self.retailers: List[Dict[str, Any]] = [
                {
                    **r,
                    "min_basket": _strict_float(r["min_basket"]),
                    "delivery_fee": _strict_float(r["delivery_fee"]),
                    "service_fee_pct": _strict_float(r["service_fee_pct"]),
                    "eta_minutes": _strict_int(r["eta_minutes"]),
                    "delivers_to_zips": [z.strip() for z in _opt_csv_list(r.get("delivers_to_zips"), sep=",")],
                }
                for r in info.get("retailers", [])
            ]
            self.products: List[Dict[str, Any]] = [
                {
                    **r,
                    "price": _strict_float(r["price"]),
                    "sale_price": _opt_float(r.get("sale_price"), default=None),
                    "in_stock": _strict_bool(r["in_stock"]),
                }
                for r in info.get("products", [])
            ]
            self.orders: List[Dict[str, Any]] = [
                {
                    **r,
                    "subtotal": _strict_float(r["subtotal"]),
                    "delivery_fee": _strict_float(r["delivery_fee"]),
                    "service_fee": _strict_float(r["service_fee"]),
                    "tip": _strict_float(r["tip"]),
                    "total": _strict_float(r["total"]),
                }
                for r in info.get("orders", [])
            ]
            self.order_items: List[Dict[str, Any]] = [
                {
                    **r,
                    "quantity": _strict_int(r["quantity"]),
                    "unit_price": _strict_float(r["unit_price"]),
                    "line_total": _strict_float(r["line_total"]),
                    "replacement_for": _opt_str(r.get("replacement_for"), default="") or None,
                }
                for r in info.get("order_items", [])
            ]
            self.user: Dict[str, Any] = info.get("user", {})

            self._carts: Dict[str, Dict[str, Any]] = {}
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightInstacart')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {
            "retailers": self.retailers,
            "products": self.products,
            "orders": self.orders,
            "order_items": self.order_items,
            "user": self.user,
        }

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _now_iso(self) -> str:
        return self._now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _get_cart(self, cart_id):
        return self._carts.get(cart_id)

    def _cart_with_totals(self, cart_id):
        cart = self._get_cart(cart_id)
        if not cart:
            return {"error": f"Cart {cart_id} not found"}
        retailer = next(r for r in self.retailers if r["retailer_id"] == cart["retailer_id"])
        subtotal = 0.0
        detailed_items = []
        for it in cart["items"]:
            product = next((p for p in self.products if p["product_id"] == it["product_id"]), None)
            if not product:
                continue
            unit_price = product["sale_price"] or product["price"]
            line_total = round(unit_price * it["quantity"], 2)
            subtotal += line_total
            detailed_items.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "quantity": it["quantity"],
                "unit_price": unit_price,
                "line_total": line_total,
            })
        service_fee = round(subtotal * retailer["service_fee_pct"] / 100, 2)
        delivery_fee = retailer["delivery_fee"]
        return {
            **cart,
            "items": detailed_items,
            "subtotal": round(subtotal, 2),
            "service_fee": service_fee,
            "delivery_fee": delivery_fee,
            "min_basket": retailer["min_basket"],
            "meets_minimum": subtotal >= retailer["min_basket"],
            "estimated_total": round(subtotal + service_fee + delivery_fee, 2),
        }

    # --- API methods -------------------------------------------------------
    def get_user(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.user}

    def list_retailers(self, zip_code: str | None = None) -> Dict[str, Any]:
        if not zip_code:
            return {"status": "ok", "output": list(self.retailers)}
        return {"status": "ok", "output": [r for r in self.retailers if zip_code in r["delivers_to_zips"]]}

    def get_retailer(self, retailer_id: str) -> Dict[str, Any]:
        for r in self.retailers:
            if r["retailer_id"] == retailer_id:
                return {"status": "ok", "output": r}
        return {"status": "failed", "output": f"Retailer {retailer_id} not found"}

    def search_products(self, retailer_id: str | None = None, query: str | None = None,
                        category: str | None = None, in_stock_only: bool = True,
                        limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.products)
        if retailer_id:
            results = [p for p in results if p["retailer_id"] == retailer_id]
        if query:
            q = query.lower()
            results = [p for p in results if q in p["name"].lower() or q in p["brand"].lower()]
        if category:
            results = [p for p in results if p["category"].lower() == category.lower()]
        if in_stock_only:
            results = [p for p in results if p["in_stock"]]
        total = len(results)
        page = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "total": total, "count": len(page), "offset": offset, "limit": limit, "results": page,
        }}

    def get_product(self, product_id: str) -> Dict[str, Any]:
        for p in self.products:
            if p["product_id"] == product_id:
                return {"status": "ok", "output": p}
        return {"status": "failed", "output": f"Product {product_id} not found"}

    def create_cart(self, user_id: str, retailer_id: str) -> Dict[str, Any]:
        if not any(r["retailer_id"] == retailer_id for r in self.retailers):
            return {"status": "failed", "output": f"Retailer {retailer_id} not found"}
        cart_id = self._new_id("cart")
        self._carts[cart_id] = {
            "cart_id": cart_id,
            "user_id": user_id,
            "retailer_id": retailer_id,
            "items": [],
            "created_at": self._now_iso(),
        }
        return {"status": "ok", "output": self._cart_with_totals(cart_id)}

    def get_cart(self, cart_id: str) -> Dict[str, Any]:
        result = self._cart_with_totals(cart_id)
        if "error" in result:
            return {"status": "failed", "output": result["error"]}
        return {"status": "ok", "output": result}

    def add_to_cart(self, cart_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        cart = self._get_cart(cart_id)
        if not cart:
            return {"status": "failed", "output": f"Cart {cart_id} not found"}
        product = next((p for p in self.products if p["product_id"] == product_id), None)
        if not product:
            return {"status": "failed", "output": f"Product {product_id} not found"}
        if product["retailer_id"] != cart["retailer_id"]:
            return {"status": "failed", "output": "Product belongs to a different retailer than the cart"}
        for it in cart["items"]:
            if it["product_id"] == product_id:
                it["quantity"] += quantity
                return {"status": "ok", "output": self._cart_with_totals(cart_id)}
        cart["items"].append({"product_id": product_id, "quantity": quantity})
        return {"status": "ok", "output": self._cart_with_totals(cart_id)}

    def update_cart_item(self, cart_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        cart = self._get_cart(cart_id)
        if not cart:
            return {"status": "failed", "output": f"Cart {cart_id} not found"}
        for it in cart["items"]:
            if it["product_id"] == product_id:
                if quantity <= 0:
                    cart["items"].remove(it)
                else:
                    it["quantity"] = quantity
                return {"status": "ok", "output": self._cart_with_totals(cart_id)}
        return {"status": "failed", "output": f"Product {product_id} not in cart"}

    def checkout(self, cart_id: str, tip: float = 0.0,
                 delivery_window_start: str | None = None,
                 delivery_window_end: str | None = None) -> Dict[str, Any]:
        cart_full = self._cart_with_totals(cart_id)
        if "error" in cart_full:
            return {"status": "failed", "output": cart_full["error"]}
        if not cart_full["meets_minimum"]:
            return {"status": "failed", "output": "Cart does not meet retailer minimum basket"}
        order_id = self._new_id("order")
        now = self._now_iso()
        if not delivery_window_start:
            try:
                base = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                base = datetime.utcnow()
            start = base + timedelta(hours=2)
            delivery_window_start = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            delivery_window_end = (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        order = {
            "order_id": order_id,
            "user_id": cart_full["user_id"],
            "retailer_id": cart_full["retailer_id"],
            "status": "PLACED",
            "subtotal": cart_full["subtotal"],
            "delivery_fee": cart_full["delivery_fee"],
            "service_fee": cart_full["service_fee"],
            "tip": float(tip),
            "total": round(cart_full["estimated_total"] + float(tip), 2),
            "placed_at": now,
            "delivery_window_start": delivery_window_start,
            "delivery_window_end": delivery_window_end,
            "shopper_id": "",
        }
        self.orders.append(order)
        for it in cart_full["items"]:
            self.order_items.append({
                "order_id": order_id,
                "product_id": it["product_id"],
                "quantity": it["quantity"],
                "unit_price": it["unit_price"],
                "line_total": it["line_total"],
                "replacement_for": None,
            })
        self._carts.pop(cart_id, None)
        return {"status": "ok", "output": order}

    def list_orders(self, user_id: str | None = None, status: str | None = None) -> Dict[str, Any]:
        results = list(self.orders)
        if user_id:
            results = [o for o in results if o["user_id"] == user_id]
        if status:
            results = [o for o in results if o["status"].upper() == status.upper()]
        results.sort(key=lambda o: o["placed_at"], reverse=True)
        return {"status": "ok", "output": {"count": len(results), "results": results}}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        for o in self.orders:
            if o["order_id"] == order_id:
                items = [i for i in self.order_items if i["order_id"] == order_id]
                return {"status": "ok", "output": {**o, "items": items}}
        return {"status": "failed", "output": f"Order {order_id} not found"}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        for i, o in enumerate(self.orders):
            if o["order_id"] == order_id:
                if o["status"] in {"DELIVERED", "CANCELLED"}:
                    return {"status": "failed", "output": f"Order {order_id} cannot be cancelled (status: {o['status']})"}
                self.orders[i]["status"] = "CANCELLED"
                return {"status": "ok", "output": self.orders[i]}
        return {"status": "failed", "output": f"Order {order_id} not found"}


if __name__ == "__main__":
    s = InstacartSession(seed=12)
    print(s.get_user())
    print(s.list_retailers())
    print(s.search_products(query="banana"))
