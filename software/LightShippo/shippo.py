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


def _to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class ShippoSession:
    """Deterministic sandbox for the Shippo mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    _DEFAULT_RATE_TEMPLATES = [
        ("USPS", "usps_priority", "Priority Mail", 9.10, 2),
        ("UPS", "ups_ground", "UPS Ground", 12.45, 3),
        ("FedEx", "fedex_2day", "FedEx 2Day", 19.20, 2),
    ]

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "shippo.yaml") as f:
                info = yaml.safe_load(f)

            self.addresses: List[Dict[str, Any]] = [
                {
                    **a,
                    "is_residential": _to_bool(a.get("is_residential", False)),
                    "validated": _to_bool(a.get("validated", False)),
                }
                for a in info.get("addresses", [])
            ]
            self.parcels: List[Dict[str, Any]] = [
                {
                    **p,
                    "length": _to_float(p.get("length"), 0.0),
                    "width": _to_float(p.get("width"), 0.0),
                    "height": _to_float(p.get("height"), 0.0),
                    "weight": _to_float(p.get("weight"), 0.0),
                    "template": (str(p.get("template", "")) or None),
                }
                for p in info.get("parcels", [])
            ]
            self.shipments: List[Dict[str, Any]] = list(info.get("shipments", []))
            self.rates: List[Dict[str, Any]] = [
                {
                    **r,
                    "amount": _to_float(r.get("amount"), 0.0),
                    "estimated_days": _to_int(r.get("estimated_days"), 0),
                }
                for r in info.get("rates", [])
            ]
            self.transactions: List[Dict[str, Any]] = list(info.get("transactions", []))
            self.tracking: List[Dict[str, Any]] = list(info.get("tracking", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightShippo')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"shipments": self.shipments, "transactions": self.transactions}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _address_obj(self, a):
        return dict(a)

    def _find_address(self, object_id):
        for a in self.addresses:
            if a["object_id"] == object_id:
                return self._address_obj(a)
        return None

    def _parcel_obj(self, p):
        return dict(p)

    def _rate_obj(self, r):
        return {
            "object_id": r["object_id"],
            "shipment": r["shipment"],
            "provider": r["provider"],
            "servicelevel": {"token": r["servicelevel_token"], "name": r["servicelevel_name"]},
            "amount": r["amount"],
            "currency": r["currency"],
            "estimated_days": r["estimated_days"],
        }

    def _shipment_obj(self, s):
        rates = [self._rate_obj(r) for r in self.rates if r["shipment"] == s["object_id"]]
        return {
            "object_id": s["object_id"],
            "status": s["status"],
            "object_created": s["created_time"],
            "address_from": self._find_address(s["address_from"]),
            "address_to": self._find_address(s["address_to"]),
            "parcels": [self._parcel_obj(p) for p in self.parcels if p["object_id"] == s["parcel"]],
            "rates": rates,
        }

    def _gen_tracking_number(self, provider):
        digits = self.rng.randrange(10 ** 18)
        if provider == "USPS":
            return f"9400{digits:018d}"[:22]
        if provider == "UPS":
            return f"1Z999AA1{digits:010d}"[:18]
        return f"{digits:012d}"[:12]

    # --- Addresses ---------------------------------------------------------
    def create_address(self, name: str, company: str = "", street1: str = "", street2: str = "",
                       city: str = "", state: str = "", zip: str = "", country: str = "US",
                       phone: str = "", email: str = "", is_residential: bool = False) -> Dict[str, Any]:
        addr = {
            "object_id": self._new_id("addr"),
            "name": name or "",
            "company": company or "",
            "street1": street1 or "",
            "street2": street2 or "",
            "city": city or "",
            "state": state or "",
            "zip": zip or "",
            "country": country or "US",
            "phone": phone or "",
            "email": email or "",
            "is_residential": bool(is_residential),
            "validated": True,
        }
        self.addresses.append(addr)
        return {"status": "ok", "output": self._address_obj(addr)}

    def get_address(self, object_id: str) -> Dict[str, Any]:
        addr = self._find_address(object_id)
        if addr is None:
            return {"status": "failed", "output": f"address {object_id} not found"}
        return {"status": "ok", "output": addr}

    # --- Shipments + rates -------------------------------------------------
    def create_shipment(self, address_from: str, address_to: str, parcels: str | None = None) -> Dict[str, Any]:
        addr_from = address_from
        addr_to = address_to
        parcel = parcels
        if isinstance(parcel, list):
            parcel = parcel[0] if parcel else None

        if isinstance(addr_from, dict):
            addr_from = self.create_address(**addr_from)["output"]["object_id"]
        if isinstance(addr_to, dict):
            addr_to = self.create_address(**addr_to)["output"]["object_id"]
        if isinstance(parcel, dict):
            parcel = self._create_parcel(parcel)["object_id"]

        if not self._find_address(addr_from):
            return {"status": "failed", "output": f"address_from {addr_from} not found"}
        if not self._find_address(addr_to):
            return {"status": "failed", "output": f"address_to {addr_to} not found"}

        shipment = {
            "object_id": self._new_id("ship"),
            "address_from": addr_from,
            "address_to": addr_to,
            "parcel": parcel or "",
            "status": "SUCCESS",
            "created_time": self._now(),
        }
        self.shipments.append(shipment)
        for provider, token, name, amount, days in self._DEFAULT_RATE_TEMPLATES:
            self.rates.append({
                "object_id": self._new_id("rate"),
                "shipment": shipment["object_id"],
                "provider": provider,
                "servicelevel_token": token,
                "servicelevel_name": name,
                "amount": amount,
                "currency": "USD",
                "estimated_days": days,
            })
        return {"status": "ok", "output": self._shipment_obj(shipment)}

    def _create_parcel(self, payload):
        parcel = {
            "object_id": self._new_id("parcel"),
            "length": float(payload.get("length", 1)),
            "width": float(payload.get("width", 1)),
            "height": float(payload.get("height", 1)),
            "distance_unit": payload.get("distance_unit", "in"),
            "weight": float(payload.get("weight", 1)),
            "mass_unit": payload.get("mass_unit", "lb"),
            "template": payload.get("template") or None,
        }
        self.parcels.append(parcel)
        return self._parcel_obj(parcel)

    def get_shipment(self, object_id: str) -> Dict[str, Any]:
        for s in self.shipments:
            if s["object_id"] == object_id:
                return {"status": "ok", "output": self._shipment_obj(s)}
        return {"status": "failed", "output": f"shipment {object_id} not found"}

    def list_shipment_rates(self, object_id: str) -> Dict[str, Any]:
        if not any(s["object_id"] == object_id for s in self.shipments):
            return {"status": "failed", "output": f"shipment {object_id} not found"}
        rates = [self._rate_obj(r) for r in self.rates if r["shipment"] == object_id]
        return {"status": "ok", "output": {"count": len(rates), "results": rates}}

    # --- Transactions (buy a label) ----------------------------------------
    def create_transaction(self, rate: str, label_file_type: str = "PDF",
                          async_: bool = False) -> Dict[str, Any]:
        rate_id = rate
        rate_row = next((r for r in self.rates if r["object_id"] == rate_id), None)
        if rate_row is None:
            return {"status": "failed", "output": f"rate {rate_id} not found"}
        tracking_number = self._gen_tracking_number(rate_row["provider"])
        txn = {
            "object_id": self._new_id("txn"),
            "rate": rate_id,
            "shipment": rate_row["shipment"],
            "status": "SUCCESS",
            "tracking_number": tracking_number,
            "tracking_status": "PRE_TRANSIT",
            "carrier": rate_row["provider"],
            "label_url": f"https://shippo-delivery.s3.amazonaws.com/labels/{tracking_number}.pdf",
            "created_time": self._now(),
        }
        self.transactions.append(txn)
        self.tracking.append({
            "carrier": rate_row["provider"],
            "tracking_number": tracking_number,
            "status": "PRE_TRANSIT",
            "status_detail": "Shipping label created",
            "location_city": "",
            "location_state": "",
            "status_time": txn["created_time"],
        })
        return {"status": "ok", "output": dict(txn)}

    def get_transaction(self, object_id: str) -> Dict[str, Any]:
        for t in self.transactions:
            if t["object_id"] == object_id:
                return {"status": "ok", "output": dict(t)}
        return {"status": "failed", "output": f"transaction {object_id} not found"}

    # --- Tracking ----------------------------------------------------------
    def get_tracking(self, carrier: str, tracking_number: str) -> Dict[str, Any]:
        history = [t for t in self.tracking
                   if t["carrier"].lower() == carrier.lower()
                   and t["tracking_number"] == tracking_number]
        if not history:
            return {"status": "failed", "output": f"tracking {tracking_number} for {carrier} not found"}
        history = sorted(history, key=lambda t: t["status_time"], reverse=True)
        latest = history[0]
        return {"status": "ok", "output": {
            "carrier": carrier,
            "tracking_number": tracking_number,
            "tracking_status": {
                "status": latest["status"],
                "status_details": latest["status_detail"],
                "location": {"city": latest["location_city"], "state": latest["location_state"]},
                "status_date": latest["status_time"],
            },
            "tracking_history": [{
                "status": h["status"],
                "status_details": h["status_detail"],
                "location": {"city": h["location_city"], "state": h["location_state"]},
                "status_date": h["status_time"],
            } for h in history],
        }}


if __name__ == "__main__":
    s = ShippoSession(seed=12)
    print(s.get_address("addr-sender-01"))
    print(s.get_tracking("USPS", "9400111202555842761023"))
