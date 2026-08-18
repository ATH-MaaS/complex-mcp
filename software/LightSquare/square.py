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


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _money(amount, currency="USD"):
    return {"amount": _to_int(amount), "currency": currency or "USD"}


class SquareSession:
    """Deterministic sandbox for the Square API v2 mock, ported from the FastAPI service.

    Amounts are integer cents wrapped in Square-style Money objects. State is loaded
    from the corpus at init; subsequent calls read and mutate the in-memory tables.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "square.yaml") as f:
                info = yaml.safe_load(f)

            self.customers: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "given_name": r["given_name"],
                    "family_name": r["family_name"],
                    "email_address": (str(r.get("email_address") or "") or None),
                    "phone_number": (str(r.get("phone_number") or "") or None),
                    "company_name": (str(r.get("company_name") or "") or None),
                    "created_at": r["created_at"],
                }
                for r in info.get("customers", [])
            ]
            self.catalog: List[Dict[str, Any]] = [
                {
                    "type": r["type"],
                    "id": r["id"],
                    "item_data": {
                        "name": r["name"],
                        "description": r["description"],
                        "category": r["category"],
                        "variations": [{
                            "type": "ITEM_VARIATION",
                            "id": r["variation_id"],
                            "item_variation_data": {
                                "name": r["variation_name"],
                                "price_money": _money(r["price_amount"], r["currency"]),
                            },
                        }],
                    },
                }
                for r in info.get("catalog_items", [])
            ]
            self.inventory: List[Dict[str, Any]] = [
                {
                    "catalog_object_id": r["catalog_object_id"],
                    "location_id": r["location_id"],
                    "quantity": str(_to_int(r.get("quantity", 0))),
                    "state": r["state"],
                }
                for r in info.get("inventory", [])
            ]
            self.payments: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "order_id": (str(r.get("order_id") or "") or None),
                    "customer_id": (str(r.get("customer_id") or "") or None),
                    "amount_money": _money(r["amount"], r["currency"]),
                    "status": r["status"],
                    "source_type": r["source_type"],
                    "location_id": r["location_id"],
                    "receipt_number": r["receipt_number"],
                    "created_at": r["created_at"],
                }
                for r in info.get("payments", [])
            ]
            self.orders: List[Dict[str, Any]] = [
                self._coerce_order(r) for r in info.get("orders", [])
            ]
            self.merchant: Dict[str, Any] = info.get("merchant", {})
            self.refunds: List[Dict[str, Any]] = []
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSquare')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"payments": self.payments, "orders": self.orders, "refunds": self.refunds}

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _coerce_order(r):
        line_items = []
        for chunk in [c.strip() for c in str(r.get("line_items") or "").split(";") if c.strip()]:
            parts = chunk.rsplit("x", 1)
            uid = parts[0].strip()
            qty = parts[1].strip() if len(parts) > 1 else "1"
            line_items.append({
                "catalog_object_id": uid,
                "quantity": str(_to_int(qty, 1)),
            })
        return {
            "id": r["id"],
            "customer_id": (str(r.get("customer_id") or "") or None),
            "location_id": r["location_id"],
            "line_items": line_items,
            "total_money": _money(r["total_amount"], r["currency"]),
            "state": r["state"],
            "created_at": r["created_at"],
        }

    def _now(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _new_id(self, prefix) -> str:
        return f"{prefix}_{''.join(self.rng.choices('0123456789ABCDEF', k=18))}"

    @staticmethod
    def _find(store, obj_id):
        return next((x for x in store if x["id"] == obj_id), None)

    # --- merchant ----------------------------------------------------------
    def get_merchant(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"merchant": self.merchant}}

    # --- payments ----------------------------------------------------------
    def list_payments(self, location_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        results = list(self.payments)
        if location_id:
            results = [p for p in results if p["location_id"] == location_id]
        return {"status": "ok", "output": {"payments": results[:limit]}}

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        p = self._find(self.payments, payment_id)
        if not p:
            return {"status": "failed", "output": f"Payment {payment_id} not found"}
        return {"status": "ok", "output": {"payment": p}}

    def create_payment(self, amount: int, currency: str = "USD", source_id: str = "cnon:card-nonce-ok",
                       customer_id: str | None = None, order_id: str | None = None,
                       location_id: str = "LOC_MAIN") -> Dict[str, Any]:
        if amount is None or _to_int(amount) <= 0:
            return {"status": "failed", "output": "amount_money.amount must be a positive integer (cents)"}
        if customer_id and not self._find(self.customers, customer_id):
            return {"status": "failed", "output": f"Customer {customer_id} not found"}
        seq = len(self.payments) + 1
        payment = {
            "id": self._new_id("PAY"),
            "order_id": order_id,
            "customer_id": customer_id,
            "amount_money": _money(amount, currency),
            "status": "COMPLETED",
            "source_type": "CARD",
            "location_id": location_id,
            "receipt_number": f"RCP{seq:03d}",
            "created_at": self._now(),
        }
        self.payments.append(payment)
        return {"status": "ok", "output": {"payment": payment}}

    # --- refunds -----------------------------------------------------------
    def create_refund(self, payment_id: str, amount: int | None = None, currency: str = "USD",
                      reason: str | None = None) -> Dict[str, Any]:
        payment = self._find(self.payments, payment_id)
        if not payment:
            return {"status": "failed", "output": f"Payment {payment_id} not found"}
        paid = payment["amount_money"]["amount"]
        refund_amount = _to_int(amount) if amount is not None else paid
        if refund_amount <= 0 or refund_amount > paid:
            return {"status": "failed", "output": f"Refund amount {refund_amount} exceeds payment amount {paid}"}
        refund = {
            "id": self._new_id("REF"),
            "payment_id": payment_id,
            "amount_money": _money(refund_amount, currency or payment["amount_money"]["currency"]),
            "status": "COMPLETED",
            "reason": reason or "Requested by customer",
            "created_at": self._now(),
        }
        self.refunds.append(refund)
        return {"status": "ok", "output": {"refund": refund}}

    # --- customers ---------------------------------------------------------
    def list_customers(self, limit: int = 50) -> Dict[str, Any]:
        return {"status": "ok", "output": {"customers": list(self.customers)[:limit]}}

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        c = self._find(self.customers, customer_id)
        if not c:
            return {"status": "failed", "output": f"Customer {customer_id} not found"}
        return {"status": "ok", "output": {"customer": c}}

    def create_customer(self, given_name: str | None = None, family_name: str | None = None,
                       email_address: str | None = None, phone_number: str | None = None,
                       company_name: str | None = None) -> Dict[str, Any]:
        customer = {
            "id": self._new_id("CUST"),
            "given_name": given_name or "",
            "family_name": family_name or "",
            "email_address": email_address,
            "phone_number": phone_number,
            "company_name": company_name,
            "created_at": self._now(),
        }
        self.customers.append(customer)
        return {"status": "ok", "output": {"customer": customer}}

    # --- catalog -----------------------------------------------------------
    def list_catalog(self, types: str | None = None) -> Dict[str, Any]:
        objects = list(self.catalog)
        if types:
            wanted = {t.strip().upper() for t in types.split(",")}
            objects = [o for o in objects if o["type"] in wanted]
        return {"status": "ok", "output": {"objects": objects}}

    # --- orders ------------------------------------------------------------
    def get_order(self, order_id: str) -> Dict[str, Any]:
        o = self._find(self.orders, order_id)
        if not o:
            return {"status": "failed", "output": f"Order {order_id} not found"}
        return {"status": "ok", "output": {"order": o}}

    def create_order(self, customer_id: str | None = None, location_id: str = "LOC_MAIN",
                    line_items: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        line_items = line_items or []
        total = 0
        normalized = []
        for li in line_items:
            uid = li.get("catalog_object_id")
            qty = _to_int(li.get("quantity", 1), 1)
            unit_amount = 0
            for item in self.catalog:
                for var in item["item_data"]["variations"]:
                    if var["id"] == uid:
                        unit_amount = var["item_variation_data"]["price_money"]["amount"]
            total += unit_amount * qty
            normalized.append({"catalog_object_id": uid, "quantity": str(qty)})
        order = {
            "id": self._new_id("ORD"),
            "customer_id": customer_id,
            "location_id": location_id,
            "line_items": normalized,
            "total_money": _money(total, "USD"),
            "state": "OPEN",
            "created_at": self._now(),
        }
        self.orders.append(order)
        return {"status": "ok", "output": {"order": order}}

    # --- inventory ---------------------------------------------------------
    def get_inventory(self, catalog_object_id: str) -> Dict[str, Any]:
        counts = [i for i in self.inventory if i["catalog_object_id"] == catalog_object_id]
        if not counts:
            return {"status": "failed", "output": f"No inventory for catalog object {catalog_object_id}"}
        return {"status": "ok", "output": {"counts": counts}}


if __name__ == "__main__":
    s = SquareSession(seed=12)
    print(s.get_merchant())
    print(s.list_customers())
