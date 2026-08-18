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


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _opt_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


class UpsSession:
    """Deterministic sandbox for the UPS mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "ups.yaml") as f:
                info = yaml.safe_load(f)

            self.rates: List[Dict[str, Any]] = [
                {
                    "service_code": r["service_code"],
                    "service_name": r["service_name"],
                    "origin_zip": r["origin_zip"],
                    "dest_zip": r["dest_zip"],
                    "weight_lb": _opt_float(r.get("weight_lb")),
                    "currency": r["currency"],
                    "total_charge": _opt_float(r.get("total_charge")),
                    "transit_days": _to_int(r.get("transit_days")),
                    "delivery_date": r["delivery_date"],
                }
                for r in info.get("rates", [])
            ]
            self.shipments: List[Dict[str, Any]] = [
                {
                    "tracking_number": r["tracking_number"],
                    "service_code": r["service_code"],
                    "service_name": r["service_name"],
                    "ship_date": r["ship_date"],
                    "origin_zip": r["origin_zip"],
                    "dest_zip": r["dest_zip"],
                    "weight_lb": _opt_float(r.get("weight_lb")),
                    "currency": r["currency"],
                    "total_charge": _opt_float(r.get("total_charge")),
                    "label_url": r["label_url"],
                }
                for r in info.get("shipments", [])
            ]
            self.tracking: List[Dict[str, Any]] = [
                {
                    "tracking_number": r["tracking_number"],
                    "status_type": r["status_type"],
                    "status_code": r["status_code"],
                    "status_description": r["status_description"],
                    "service_name": r["service_name"],
                    "ship_date": r["ship_date"],
                    "scheduled_delivery": r["scheduled_delivery"],
                    "latest_activity": r["latest_activity"],
                    "latest_activity_location": r["latest_activity_location"],
                    "latest_activity_time": r["latest_activity_time"],
                }
                for r in info.get("tracking", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightUPS')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"shipments": self.shipments, "tracking": self.tracking}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _today(self) -> str:
        return self._now()[:10]

    def _new_tracking_number(self) -> str:
        base = max(
            (int(s["tracking_number"][-7:]) for s in self.shipments),
            default=3456784,
        )
        return f"1Z999AA101{base + 11:07d}"

    # --- API methods -------------------------------------------------------
    def get_rate(self, origin_zip: str, dest_zip: str, weight_lb: float = 1.0,
                 service_code: str | None = None) -> Dict[str, Any]:
        matches = [
            r for r in self.rates
            if r["origin_zip"] == str(origin_zip) and r["dest_zip"] == str(dest_zip)
        ]
        if service_code:
            matches = [r for r in matches if r["service_code"] == service_code]
        if not matches:
            return {"status": "failed", "output": f"no rates found for {origin_zip} -> {dest_zip}"}
        weight = _to_float(weight_lb) or 1.0
        rated = []
        for r in matches:
            scaled = round(r["total_charge"] * (weight / (r["weight_lb"] or 1.0)), 2) if r["weight_lb"] else r["total_charge"]
            rated.append({
                "Service": {"Code": r["service_code"], "Description": r["service_name"]},
                "TotalCharges": {"CurrencyCode": r["currency"], "MonetaryValue": f"{scaled:.2f}"},
                "GuaranteedDelivery": {
                    "BusinessDaysInTransit": str(r["transit_days"]),
                    "DeliveryByTime": r["delivery_date"],
                },
            })
        return {"status": "ok", "output": {
            "RateResponse": {
                "Response": {"ResponseStatus": {"Code": "1", "Description": "Success"}},
                "RatedShipment": rated,
            }
        }}

    def create_shipment(self, origin_zip: str, dest_zip: str, weight_lb: float = 1.0,
                        service_code: str = "03") -> Dict[str, Any]:
        rate = next(
            (r for r in self.rates
             if r["origin_zip"] == str(origin_zip)
             and r["dest_zip"] == str(dest_zip)
             and r["service_code"] == service_code),
            None,
        )
        total_charge = rate["total_charge"] if rate else 0.0
        currency = rate["currency"] if rate else "USD"
        service_name = rate["service_name"] if rate else "UPS Ground"
        tracking_number = self._new_tracking_number()
        label_url = f"https://ups.example/labels/{tracking_number}.gif"
        shipment = {
            "tracking_number": tracking_number,
            "service_code": service_code,
            "service_name": service_name,
            "ship_date": self._today(),
            "origin_zip": str(origin_zip),
            "dest_zip": str(dest_zip),
            "weight_lb": _to_float(weight_lb),
            "currency": currency,
            "total_charge": total_charge,
            "label_url": label_url,
        }
        self.shipments.append(shipment)
        self.tracking.append({
            "tracking_number": tracking_number,
            "status_type": "M",
            "status_code": "003",
            "status_description": "Label Created",
            "service_name": service_name,
            "ship_date": shipment["ship_date"],
            "scheduled_delivery": self._today(),
            "latest_activity": "Shipper created a label, UPS has not received the package yet.",
            "latest_activity_location": str(origin_zip),
            "latest_activity_time": self._now(),
        })
        return {"status": "ok", "output": {
            "ShipmentResponse": {
                "Response": {"ResponseStatus": {"Code": "1", "Description": "Success"}},
                "ShipmentResults": {
                    "ShipmentIdentificationNumber": tracking_number,
                    "ShipmentCharges": {
                        "TotalCharges": {"CurrencyCode": currency, "MonetaryValue": f"{total_charge:.2f}"},
                    },
                    "PackageResults": [{
                        "TrackingNumber": tracking_number,
                        "ShippingLabel": {"ImageFormat": {"Code": "GIF"}, "GraphicImage": label_url},
                    }],
                },
            }
        }}

    def track(self, tracking_number: str) -> Dict[str, Any]:
        t = next((x for x in self.tracking if x["tracking_number"] == str(tracking_number)), None)
        if not t:
            return {"status": "failed", "output": f"tracking number {tracking_number} not found"}
        return {"status": "ok", "output": {
            "trackResponse": {
                "shipment": [{
                    "package": [{
                        "trackingNumber": t["tracking_number"],
                        "currentStatus": {
                            "type": t["status_type"],
                            "code": t["status_code"],
                            "description": t["status_description"],
                        },
                        "service": {"description": t["service_name"]},
                        "deliveryDate": [{"type": "SDD", "date": t["scheduled_delivery"]}],
                        "activity": [{
                            "status": {
                                "type": t["status_type"],
                                "code": t["status_code"],
                                "description": t["latest_activity"],
                            },
                            "location": {"address": {"city": t["latest_activity_location"]}},
                            "date": t["latest_activity_time"][:10].replace("-", ""),
                            "time": t["latest_activity_time"],
                        }],
                    }],
                }],
            }
        }}


if __name__ == "__main__":
    s = UpsSession(seed=12)
    print(s.get_rate("10001", "90001", 5.0))
    print(s.track("1Z999AA10123456784"))
