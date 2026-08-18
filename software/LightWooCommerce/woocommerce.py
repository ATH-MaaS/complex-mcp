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
        return int(v)
    except (TypeError, ValueError):
        return default


def _opt_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _opt_csv_list(v, sep=";"):
    if not v:
        return []
    return [x for x in str(v).split(sep) if x]


class WoocommerceSession:
    """Deterministic sandbox for the WooCommerce mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "woocommerce.yaml") as f:
                info = yaml.safe_load(f)

            self.products: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "name": r["name"],
                    "slug": r["slug"],
                    "sku": r["sku"],
                    "type": r["type"],
                    "status": r["status"],
                    "price": _opt_float(r.get("price")),
                    "regular_price": _opt_float(r.get("regular_price")),
                    "sale_price": _opt_float(r.get("sale_price")),
                    "on_sale": _to_bool(r.get("on_sale")),
                    "stock_quantity": _to_int(r.get("stock_quantity")),
                    "stock_status": r["stock_status"],
                    "manage_stock": _to_bool(r.get("manage_stock")),
                    "categories": _opt_csv_list(r.get("categories"), sep=";"),
                    "description": r["description"],
                    "date_created": r["date_created"],
                }
                for r in info.get("products", [])
            ]
            self.customers: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "first_name": r["first_name"],
                    "last_name": r["last_name"],
                    "email": r["email"],
                    "username": r["username"],
                    "role": r["role"],
                    "billing_city": r["billing_city"],
                    "billing_country": r["billing_country"],
                    "is_paying_customer": _to_bool(r.get("is_paying_customer")),
                    "date_created": r["date_created"],
                }
                for r in info.get("customers", [])
            ]
            self.orders: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r.get("id")),
                    "number": r["number"],
                    "customer_id": _to_int(r.get("customer_id")),
                    "status": r["status"],
                    "currency": r["currency"],
                    "total": _opt_float(r.get("total")),
                    "subtotal": _opt_float(r.get("subtotal")),
                    "total_tax": _opt_float(r.get("total_tax")),
                    "payment_method": r["payment_method"],
                    "payment_method_title": r["payment_method_title"],
                    "billing_first_name": r["billing_first_name"],
                    "billing_last_name": r["billing_last_name"],
                    "billing_email": r["billing_email"],
                    "date_created": r["date_created"],
                }
                for r in info.get("orders", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightWooCommerce')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"orders": self.orders}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _serialize_product(self, p):
        return {
            "id": p["id"],
            "name": p["name"],
            "slug": p["slug"],
            "sku": p["sku"],
            "type": p["type"],
            "status": p["status"],
            "price": f"{p['price']:.2f}",
            "regular_price": f"{p['regular_price']:.2f}",
            "sale_price": (f"{p['sale_price']:.2f}" if p["sale_price"] else ""),
            "on_sale": p["on_sale"],
            "stock_quantity": p["stock_quantity"],
            "stock_status": p["stock_status"],
            "manage_stock": p["manage_stock"],
            "categories": [{"name": c, "slug": c.lower().replace(" ", "-")}
                           for c in p["categories"]],
            "description": p["description"],
            "date_created": p["date_created"],
        }

    def _serialize_customer(self, c):
        return {
            "id": c["id"],
            "first_name": c["first_name"],
            "last_name": c["last_name"],
            "email": c["email"],
            "username": c["username"],
            "role": c["role"],
            "billing": {"city": c["billing_city"], "country": c["billing_country"]},
            "is_paying_customer": c["is_paying_customer"],
            "date_created": c["date_created"],
        }

    def _serialize_order(self, o):
        return {
            "id": o["id"],
            "number": o["number"],
            "customer_id": o["customer_id"],
            "status": o["status"],
            "currency": o["currency"],
            "total": f"{o['total']:.2f}",
            "subtotal": f"{o['subtotal']:.2f}",
            "total_tax": f"{o['total_tax']:.2f}",
            "payment_method": o["payment_method"],
            "payment_method_title": o["payment_method_title"],
            "billing": {
                "first_name": o["billing_first_name"],
                "last_name": o["billing_last_name"],
                "email": o["billing_email"],
            },
            "date_created": o["date_created"],
        }

    # --- Products ----------------------------------------------------------
    def list_products(self, search: str | None = None, sku: str | None = None,
                      status: str | None = None, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        items = self.products
        if search:
            items = [p for p in items if search.lower() in p["name"].lower()]
        if sku:
            items = [p for p in items if p["sku"].lower() == sku.lower()]
        if status:
            items = [p for p in items if p["status"] == status]
        start = (page - 1) * per_page
        page_items = items[start:start + per_page]
        return {"status": "ok", "output": [self._serialize_product(p) for p in page_items]}

    def get_product(self, product_id: int) -> Dict[str, Any]:
        p = next((x for x in self.products if x["id"] == int(product_id)), None)
        if not p:
            return {"status": "failed", "output": {
                "error": "woocommerce_rest_product_invalid_id", "status": 404,
                "message": f"Invalid product ID: {product_id}"}}
        return {"status": "ok", "output": self._serialize_product(p)}

    # --- Orders ------------------------------------------------------------
    def list_orders(self, customer: int | None = None, status: str | None = None,
                    page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        items = self.orders
        if customer is not None:
            items = [o for o in items if o["customer_id"] == int(customer)]
        if status:
            items = [o for o in items if o["status"] == status]
        start = (page - 1) * per_page
        page_items = items[start:start + per_page]
        return {"status": "ok", "output": [self._serialize_order(o) for o in page_items]}

    def get_order(self, order_id: int) -> Dict[str, Any]:
        o = next((x for x in self.orders if x["id"] == int(order_id)), None)
        if not o:
            return {"status": "failed", "output": {
                "error": "woocommerce_rest_shop_order_invalid_id", "status": 404,
                "message": f"Invalid order ID: {order_id}"}}
        return {"status": "ok", "output": self._serialize_order(o)}

    def create_order(self, customer_id: int = 0, status: str = "pending", currency: str = "USD",
                     payment_method: str = "bacs", payment_method_title: str = "Direct Bank Transfer",
                     billing: Dict[str, Any] | None = None,
                     line_items: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        billing = billing or {}
        line_items = line_items or []
        next_id = max((o["id"] for o in self.orders), default=400) + 1
        subtotal = 0.0
        for line in line_items:
            prod = next((p for p in self.products
                         if p["id"] == int(line.get("product_id", 0))), None)
            qty = int(line.get("quantity", 1))
            price = prod["price"] if prod else 0.0
            subtotal += price * qty
        tax = round(subtotal * 0.1, 2)
        order = {
            "id": next_id,
            "number": str(next_id),
            "customer_id": int(customer_id),
            "status": status,
            "currency": currency,
            "total": round(subtotal + tax, 2),
            "subtotal": round(subtotal, 2),
            "total_tax": tax,
            "payment_method": payment_method,
            "payment_method_title": payment_method_title,
            "billing_first_name": billing.get("first_name", ""),
            "billing_last_name": billing.get("last_name", ""),
            "billing_email": billing.get("email", ""),
            "date_created": "2026-05-28T00:00:00",
        }
        self.orders.append(order)
        return {"status": "ok", "output": self._serialize_order(order)}

    # --- Customers ---------------------------------------------------------
    def list_customers(self, search: str | None = None, email: str | None = None,
                       page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        items = self.customers
        if email:
            items = [c for c in items if email.lower() in c["email"].lower()]
        if search:
            items = [c for c in items
                     if search.lower() in (c["first_name"] + " " + c["last_name"]).lower()
                     or search.lower() in c["email"].lower()]
        start = (page - 1) * per_page
        page_items = items[start:start + per_page]
        return {"status": "ok", "output": [self._serialize_customer(c) for c in page_items]}


if __name__ == "__main__":
    s = WoocommerceSession(seed=12)
    print(s.list_products())
    print(s.list_customers())
