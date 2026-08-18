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


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class FedexSession:
    """Deterministic sandbox for the FedEx mock, ported from the FastAPI service.

    Mirrors a subset of the FedEx Web Services REST APIs: rate quotes,
    shipment (label) creation, and tracking. State is loaded from the corpus at
    init; subsequent calls read and mutate the in-memory tables.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "fedex.yaml") as f:
                info = yaml.safe_load(f)

            self.rates: List[Dict[str, Any]] = [
                {
                    "service_type": r["service_type"],
                    "service_name": r["service_name"],
                    "origin_zip": r["origin_zip"],
                    "dest_zip": r["dest_zip"],
                    "weight_lb": _to_float(r.get("weight_lb")) if r.get("weight_lb") not in (None, "") else None,
                    "currency": r["currency"],
                    "net_charge": _to_float(r.get("net_charge")) if r.get("net_charge") not in (None, "") else None,
                    "transit_days": int(str(r["transit_days"]).strip()),
                    "delivery_day": r["delivery_day"],
                }
                for r in info.get("rates", [])
            ]
            self.shipments: List[Dict[str, Any]] = [
                {
                    "tracking_number": r["tracking_number"],
                    "service_type": r["service_type"],
                    "service_name": r["service_name"],
                    "ship_date": r["ship_date"],
                    "origin_zip": r["origin_zip"],
                    "dest_zip": r["dest_zip"],
                    "weight_lb": _to_float(r.get("weight_lb")) if r.get("weight_lb") not in (None, "") else None,
                    "currency": r["currency"],
                    "net_charge": _to_float(r.get("net_charge")) if r.get("net_charge") not in (None, "") else None,
                    "label_url": r["label_url"],
                }
                for r in info.get("shipments", [])
            ]
            self.tracking: List[Dict[str, Any]] = list(info.get("tracking", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightFedEx')
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

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _new_tracking_number(self) -> str:
        base = max((int(s["tracking_number"]) for s in self.shipments), default=794612035840)
        return str(base + 11)

    # --- API methods -------------------------------------------------------
    def get_rate_quote(self, origin_zip: str, dest_zip: str, weight_lb: float = 1.0,
                       service_type: str | None = None) -> Dict[str, Any]:
        matches = [
            r for r in self.rates
            if r["origin_zip"] == str(origin_zip) and r["dest_zip"] == str(dest_zip)
        ]
        if service_type:
            matches = [r for r in matches if r["service_type"] == service_type]
        if not matches:
            return {"status": "failed", "output": f"no rates found for {origin_zip} -> {dest_zip}"}
        weight = _to_float(weight_lb) or 1.0
        details = []
        for r in matches:
            base = r["net_charge"]
            scaled = round(base * (weight / (r["weight_lb"] or 1.0)), 2) if r["weight_lb"] else base
            details.append({
                "serviceType": r["service_type"],
                "serviceName": r["service_name"],
                "packagingType": "YOUR_PACKAGING",
                "commit": {
                    "dateDetail": {"dayCxsFormat": r["delivery_day"]},
                    "transitDays": r["transit_days"],
                },
                "ratedShipmentDetails": [{
                    "rateType": "ACCOUNT",
                    "totalNetCharge": scaled,
                    "currency": r["currency"],
                }],
            })
        return {"status": "ok", "output": {"rateReplyDetails": details, "quoteDate": self._today()}}

    def create_shipment(self, origin_zip: str, dest_zip: str, weight_lb: float = 1.0,
                        service_type: str = "FEDEX_GROUND") -> Dict[str, Any]:
        rate = next(
            (r for r in self.rates
             if r["origin_zip"] == str(origin_zip)
             and r["dest_zip"] == str(dest_zip)
             and r["service_type"] == service_type),
            None,
        )
        net_charge = rate["net_charge"] if rate else 0.0
        currency = rate["currency"] if rate else "USD"
        service_name = rate["service_name"] if rate else service_type.replace("_", " ").title()
        tracking_number = self._new_tracking_number()
        label_url = f"https://fedex.example/labels/{tracking_number}.pdf"
        shipment = {
            "tracking_number": tracking_number,
            "service_type": service_type,
            "service_name": service_name,
            "ship_date": self._today(),
            "origin_zip": str(origin_zip),
            "dest_zip": str(dest_zip),
            "weight_lb": _to_float(weight_lb),
            "currency": currency,
            "net_charge": net_charge,
            "label_url": label_url,
        }
        self.shipments.append(shipment)
        self.tracking.append({
            "tracking_number": tracking_number,
            "status_code": "PU",
            "status_description": "Picked up",
            "carrier_code": "FDXG" if "GROUND" in service_type else "FDXE",
            "service_name": service_name,
            "ship_date": shipment["ship_date"],
            "estimated_delivery": self._today(),
            "latest_event": "Shipment information sent to FedEx",
            "latest_event_location": str(origin_zip),
            "latest_event_time": self._now(),
        })
        return {
            "status": "ok",
            "output": {
                "transactionShipments": [{
                    "serviceType": service_type,
                    "serviceName": service_name,
                    "shipDatestamp": shipment["ship_date"],
                    "masterTrackingNumber": tracking_number,
                    "pieceResponses": [{
                        "trackingNumber": tracking_number,
                        "netChargeAmount": net_charge,
                        "currency": currency,
                        "packageDocuments": [{
                            "contentType": "LABEL",
                            "docType": "PDF",
                            "url": label_url,
                        }],
                    }],
                }],
            },
        }

    def track(self, tracking_number: str) -> Dict[str, Any]:
        t = next((x for x in self.tracking if x["tracking_number"] == str(tracking_number)), None)
        if not t:
            return {"status": "failed", "output": f"tracking number {tracking_number} not found"}
        return {
            "status": "ok",
            "output": {
                "completeTrackResults": [{
                    "trackingNumber": t["tracking_number"],
                    "trackResults": [{
                        "trackingNumberInfo": {
                            "trackingNumber": t["tracking_number"],
                            "carrierCode": t["carrier_code"],
                        },
                        "latestStatusDetail": {
                            "code": t["status_code"],
                            "description": t["status_description"],
                            "scanLocation": {"city": t["latest_event_location"]},
                        },
                        "serviceDetail": {"description": t["service_name"]},
                        "dateAndTimes": [
                            {"type": "SHIP", "dateTime": t["ship_date"]},
                            {"type": "ESTIMATED_DELIVERY", "dateTime": t["estimated_delivery"]},
                        ],
                        "scanEvents": [{
                            "date": t["latest_event_time"],
                            "eventDescription": t["latest_event"],
                            "scanLocation": {"city": t["latest_event_location"]},
                        }],
                    }],
                }],
            },
        }


if __name__ == "__main__":
    s = FedexSession(seed=12)
    print(s.get_rate_quote("38116", "10001", 5.0))
    print(s.track("794612035840"))
