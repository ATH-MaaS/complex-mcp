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


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _opt_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class BigcommerceSession:
    """Deterministic sandbox for the BigCommerce mock, ported from the FastAPI service.

    Mirrors a subset of the Catalog (v3), Orders (v2) and Customers (v3) APIs.
    v3 list responses are wrapped in {"data": [...], "meta": {...}}; v2 responses
    are bare arrays/objects. Mutations persist within the session.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "bigcommerce.yaml") as f:
                info = yaml.safe_load(f)

            self.products: List[Dict[str, Any]] = self._coerce_products(info.get("products", []))
            self.customers: List[Dict[str, Any]] = self._coerce_customers(info.get("customers", []))
            self.orders: List[Dict[str, Any]] = self._coerce_orders(info.get("orders", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightBigCommerce')
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
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _coerce_products(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": _to_int(r.get("id"), default=0),
                "name": r["name"],
                "sku": r["sku"],
                "type": r["type"],
                "price": _opt_float(r.get("price")),
                "sale_price": _opt_float(r.get("sale_price")),
                "cost_price": _opt_float(r.get("cost_price")),
                "weight": _opt_float(r.get("weight")),
                "inventory_level": _to_int(r.get("inventory_level"), default=0),
                "inventory_tracking": r["inventory_tracking"],
                "is_visible": _to_bool(r.get("is_visible")),
                "brand_id": _to_int(r.get("brand_id"), default=0),
                "categories": [int(c) for c in str(r.get("categories", "")).split(";") if c],
                "description": r["description"],
                "date_created": r["date_created"],
            })
        return out

    def _coerce_customers(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": _to_int(r.get("id"), default=0),
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "email": r["email"],
                "company": r["company"],
                "phone": r["phone"],
                "customer_group_id": _to_int(r.get("customer_group_id"), default=0),
                "date_created": r["date_created"],
            })
        return out

    def _coerce_orders(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": _to_int(r.get("id"), default=0),
                "customer_id": _to_int(r.get("customer_id"), default=0),
                "status_id": _to_int(r.get("status_id"), default=0),
                "status": r["status"],
                "total_inc_tax": _opt_float(r.get("total_inc_tax")),
                "subtotal_inc_tax": _opt_float(r.get("subtotal_inc_tax")),
                "currency_code": r["currency_code"],
                "payment_method": r["payment_method"],
                "items_total": _to_int(r.get("items_total"), default=0),
                "date_created": r["date_created"],
                "billing_first_name": r["billing_first_name"],
                "billing_last_name": r["billing_last_name"],
                "billing_email": r["billing_email"],
            })
        return out

    # --- serializers -------------------------------------------------------
    def _serialize_product(self, p):
        return {
            "id": p["id"],
            "name": p["name"],
            "sku": p["sku"],
            "type": p["type"],
            "price": p["price"],
            "sale_price": p["sale_price"],
            "cost_price": p["cost_price"],
            "weight": p["weight"],
            "inventory_level": p["inventory_level"],
            "inventory_tracking": p["inventory_tracking"],
            "is_visible": p["is_visible"],
            "brand_id": p["brand_id"],
            "categories": p["categories"],
            "description": p["description"],
            "date_created": p["date_created"],
        }

    def _serialize_customer(self, c):
        return {
            "id": c["id"],
            "first_name": c["first_name"],
            "last_name": c["last_name"],
            "email": c["email"],
            "company": c["company"],
            "phone": c["phone"],
            "customer_group_id": c["customer_group_id"],
            "date_created": c["date_created"],
        }

    def _serialize_order(self, o):
        return {
            "id": o["id"],
            "customer_id": o["customer_id"],
            "status_id": o["status_id"],
            "status": o["status"],
            "total_inc_tax": f"{o['total_inc_tax']:.2f}",
            "subtotal_inc_tax": f"{o['subtotal_inc_tax']:.2f}",
            "currency_code": o["currency_code"],
            "payment_method": o["payment_method"],
            "items_total": o["items_total"],
            "date_created": o["date_created"],
            "billing_address": {
                "first_name": o["billing_first_name"],
                "last_name": o["billing_last_name"],
                "email": o["billing_email"],
            },
        }

    def _meta(self, total, count, page, limit):
        total_pages = (total + limit - 1) // limit if limit else 1
        return {
            "pagination": {
                "total": total,
                "count": count,
                "per_page": limit,
                "current_page": page,
                "total_pages": total_pages,
            }
        }

    # --- Catalog / Products (v3) ------------------------------------------
    def list_products(self, name: str | None = None, sku: str | None = None,
                      is_visible: bool | None = None, page: int = 1, limit: int = 50) -> Dict[str, Any]:
        items = self.products
        if name:
            items = [p for p in items if name.lower() in p["name"].lower()]
        if sku:
            items = [p for p in items if p["sku"].lower() == sku.lower()]
        if is_visible is not None:
            items = [p for p in items if p["is_visible"] == is_visible]
        total = len(items)
        start = (page - 1) * limit
        page_items = items[start:start + limit]
        return {"status": "ok", "output": {
            "data": [self._serialize_product(p) for p in page_items],
            "meta": self._meta(total, len(page_items), page, limit),
        }}

    def get_product(self, product_id: int) -> Dict[str, Any]:
        p = next((x for x in self.products if x["id"] == int(product_id)), None)
        if not p:
            return {"status": "failed", "output": f"Product {product_id} not found"}
        return {"status": "ok", "output": {"data": self._serialize_product(p), "meta": {}}}

    # --- Orders (v2) -------------------------------------------------------
    def list_orders(self, customer_id: int | None = None, status_id: int | None = None,
                    page: int = 1, limit: int = 50) -> Dict[str, Any]:
        items = self.orders
        if customer_id is not None:
            items = [o for o in items if o["customer_id"] == int(customer_id)]
        if status_id is not None:
            items = [o for o in items if o["status_id"] == int(status_id)]
        start = (page - 1) * limit
        page_items = items[start:start + limit]
        return {"status": "ok", "output": [self._serialize_order(o) for o in page_items]}

    def get_order(self, order_id: int) -> Dict[str, Any]:
        o = next((x for x in self.orders if x["id"] == int(order_id)), None)
        if not o:
            return {"status": "failed", "output": f"Order {order_id} not found"}
        return {"status": "ok", "output": self._serialize_order(o)}

    def create_order(self, customer_id: int = 0, status_id: int = 1, payment_method: str = "manual",
                     currency_code: str = "USD", billing_address: Dict[str, Any] | None = None,
                     products: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        billing_address = billing_address or {}
        products = products or []
        next_id = max((o["id"] for o in self.orders), default=2000) + 1
        subtotal = 0.0
        items_total = 0
        for line in products:
            prod = next((p for p in self.products
                         if p["id"] == int(line.get("product_id", 0))), None)
            qty = int(line.get("quantity", 1))
            price = prod["price"] if prod else _to_float(line.get("price_inc_tax", 0))
            subtotal += price * qty
            items_total += qty
        status_map = {1: "Pending", 2: "Shipped", 10: "Completed", 11: "Awaiting Fulfillment"}
        order = {
            "id": next_id,
            "customer_id": int(customer_id),
            "status_id": int(status_id),
            "status": status_map.get(int(status_id), "Pending"),
            "total_inc_tax": round(subtotal, 2),
            "subtotal_inc_tax": round(subtotal, 2),
            "currency_code": currency_code,
            "payment_method": payment_method,
            "items_total": items_total,
            "date_created": "2026-05-28T00:00:00Z",
            "billing_first_name": billing_address.get("first_name", ""),
            "billing_last_name": billing_address.get("last_name", ""),
            "billing_email": billing_address.get("email", ""),
        }
        self.orders.append(order)
        return {"status": "ok", "output": self._serialize_order(order)}

    # --- Customers (v3) ----------------------------------------------------
    def list_customers(self, email: str | None = None, company: str | None = None,
                       page: int = 1, limit: int = 50) -> Dict[str, Any]:
        items = self.customers
        if email:
            items = [c for c in items if email.lower() in c["email"].lower()]
        if company:
            items = [c for c in items if company.lower() in c["company"].lower()]
        total = len(items)
        start = (page - 1) * limit
        page_items = items[start:start + limit]
        return {"status": "ok", "output": {
            "data": [self._serialize_customer(c) for c in page_items],
            "meta": self._meta(total, len(page_items), page, limit),
        }}


if __name__ == "__main__":
    s = BigcommerceSession(seed=12)
    print(s.list_products())
    print(s.list_orders())
