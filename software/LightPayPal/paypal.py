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


class PaypalSession:
    """Deterministic sandbox for the PayPal mock, ported from the FastAPI service.

    Implements a subset of the PayPal REST API (Orders v2, Payments v2,
    Invoicing v2, Payouts v1). Amounts are Money objects with string values.
    State is loaded from the corpus at init; subsequent calls read and mutate
    the in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "paypal.yaml") as f:
                info = yaml.safe_load(f)

            self.orders: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "intent": r["intent"],
                    "status": r["status"],
                    "purchase_units": [{
                        "amount": self._money(r["amount_value"], r["currency_code"]),
                        "payee": {"email_address": r["payee_email"]},
                        "description": r["description"],
                    }],
                    "create_time": r["create_time"],
                }
                for r in info.get("orders", [])
            ]
            self.captures: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "order_id": r["order_id"],
                    "status": r["status"],
                    "amount": self._money(r["amount_value"], r["currency_code"]),
                    "final_capture": _to_bool(r.get("final_capture", False)),
                    "create_time": r["create_time"],
                }
                for r in info.get("captures", [])
            ]
            self.invoices: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "detail": {
                        "invoice_number": r["invoice_number"],
                        "currency_code": r["currency_code"],
                        "note": r["note"],
                    },
                    "status": r["status"],
                    "primary_recipients": [{"billing_info": {"email_address": r["recipient_email"]}}],
                    "amount": self._money(r["amount_value"], r["currency_code"]),
                    "due_date": r["due_date"],
                }
                for r in info.get("invoices", [])
            ]
            self.payouts: List[Dict[str, Any]] = [
                {
                    "batch_header": {
                        "payout_batch_id": r["payout_batch_id"],
                        "batch_status": r["status"],
                        "sender_batch_header": {"sender_batch_id": r["sender_batch_id"]},
                        "amount": self._money(r["amount_value"], r["currency_code"]),
                    },
                    "recipient_email": r["recipient_email"],
                    "create_time": r["create_time"],
                    "payout_batch_id": r["payout_batch_id"],
                }
                for r in info.get("payouts", [])
            ]
            self.refunds: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "capture_id": r["capture_id"],
                    "status": r["status"],
                    "amount": self._money(r["amount_value"], r["currency_code"]),
                    "note_to_payer": r["note_to_payer"],
                    "create_time": r["create_time"],
                }
                for r in info.get("refunds", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPayPal')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"orders": self.orders, "captures": self.captures,
                "invoices": self.invoices, "payouts": self.payouts,
                "refunds": self.refunds}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789ABCDEF"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _money(self, value, currency="USD"):
        try:
            value = f"{float(value):.2f}"
        except (TypeError, ValueError):
            value = "0.00"
        return {"currency_code": currency or "USD", "value": value}

    def _new_order_id(self):
        return f"ORDER-{self.uuid()[:17].upper()}"

    def _new_id(self, prefix):
        return f"{prefix}_{self.uuid()[:16].upper()}"

    def _find(self, store, obj_id):
        return next((x for x in store if x["id"] == obj_id), None)

    # --- Checkout Orders ---------------------------------------------------
    def create_order(self, amount_value: str = "0.00", currency_code: str = "USD",
                     payee_email: str = "merchant@orbit-labs.com", description: str = "",
                     intent: str = "CAPTURE") -> Dict[str, Any]:
        order = {
            "id": self._new_order_id(),
            "intent": intent or "CAPTURE",
            "status": "CREATED",
            "purchase_units": [{
                "amount": self._money(amount_value, currency_code),
                "payee": {"email_address": payee_email},
                "description": description,
            }],
            "create_time": self._now(),
        }
        self.orders.append(order)
        return {"status": "ok", "output": order}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        o = self._find(self.orders, order_id)
        if o:
            return {"status": "ok", "output": o}
        return {"status": "failed", "output": f"Order {order_id} not found"}

    def capture_order(self, order_id: str) -> Dict[str, Any]:
        order = self._find(self.orders, order_id)
        if not order:
            return {"status": "failed", "output": f"Order {order_id} not found"}
        if order["status"] == "COMPLETED":
            return {"status": "failed", "output": f"Order {order_id} has already been captured"}
        if order["status"] == "VOIDED":
            return {"status": "failed", "output": f"Order {order_id} is voided and cannot be captured"}
        amount = order["purchase_units"][0]["amount"]
        capture = {
            "id": self._new_id("CAP"),
            "order_id": order_id,
            "status": "COMPLETED",
            "amount": amount,
            "final_capture": True,
            "create_time": self._now(),
        }
        self.captures.append(capture)
        order["status"] = "COMPLETED"
        return {"status": "ok", "output": {
            "id": order_id,
            "status": "COMPLETED",
            "purchase_units": [{
                "payments": {"captures": [capture]},
            }],
        }}

    # --- Refunds -----------------------------------------------------------
    def create_refund(self, capture_id: str, amount_value: str | None = None,
                      currency_code: str = "USD", note_to_payer: str | None = None) -> Dict[str, Any]:
        capture = self._find(self.captures, capture_id)
        if not capture:
            return {"status": "failed", "output": f"Capture {capture_id} not found"}
        if amount_value is None:
            amount = capture["amount"]
        else:
            amount = self._money(amount_value, currency_code or capture["amount"]["currency_code"])
        refund = {
            "id": self._new_id("REF"),
            "capture_id": capture_id,
            "status": "COMPLETED",
            "amount": amount,
            "note_to_payer": note_to_payer or "",
            "create_time": self._now(),
        }
        self.refunds.append(refund)
        return {"status": "ok", "output": refund}

    def get_refund(self, refund_id: str) -> Dict[str, Any]:
        r = self._find(self.refunds, refund_id)
        if r:
            return {"status": "ok", "output": r}
        return {"status": "failed", "output": f"Refund {refund_id} not found"}

    # --- Invoices ----------------------------------------------------------
    def list_invoices(self, status: str | None = None, page_size: int = 20) -> Dict[str, Any]:
        results = list(self.invoices)
        if status:
            results = [i for i in results if i["status"] == status.upper()]
        return {"status": "ok", "output": {
            "total_items": len(results),
            "total_pages": 1,
            "items": results[:page_size],
        }}

    def create_invoice(self, invoice_number: str | None = None, recipient_email: str | None = None,
                       amount_value: str = "0.00", currency_code: str = "USD",
                       due_date: str | None = None, note: str | None = None) -> Dict[str, Any]:
        seq = len(self.invoices) + 1
        invoice = {
            "id": self._new_id("INV2"),
            "detail": {
                "invoice_number": invoice_number or f"INV-{seq:04d}",
                "currency_code": currency_code or "USD",
                "note": note or "",
            },
            "status": "DRAFT",
            "primary_recipients": [{"billing_info": {"email_address": recipient_email or ""}}],
            "amount": self._money(amount_value, currency_code),
            "due_date": due_date,
        }
        self.invoices.append(invoice)
        return {"status": "ok", "output": invoice}

    # --- Payouts -----------------------------------------------------------
    def create_payout(self, amount_value: str = "0.00", currency_code: str = "USD",
                      recipient_email: str | None = None, sender_batch_id: str | None = None,
                      note: str | None = None) -> Dict[str, Any]:
        payout = {
            "batch_header": {
                "payout_batch_id": f"PAYOUT-{self.uuid()[:12].upper()}",
                "batch_status": "PENDING",
                "sender_batch_header": {
                    "sender_batch_id": sender_batch_id or f"Batch_{self.uuid()[:8]}",
                    "email_subject": note or "You have a payout",
                },
                "amount": self._money(amount_value, currency_code),
            },
            "recipient_email": recipient_email or "",
            "create_time": self._now(),
        }
        self.payouts.append(payout)
        return {"status": "ok", "output": payout}


if __name__ == "__main__":
    s = PaypalSession(seed=12)
    print(s.list_invoices())
    print(s.get_order("ORDER-5O190127TN364715T"))
