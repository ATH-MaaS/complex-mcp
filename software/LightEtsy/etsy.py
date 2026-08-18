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


def _opt_int(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _opt_float(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _opt_str_or_none(v):
    if v is None:
        return None
    s = str(v)
    return s or None


def _csv_list(v):
    if v is None or str(v).strip() == "":
        return []
    return [part for part in str(v).split(",")]


class EtsySession:
    """Deterministic sandbox for the Etsy Open API v3 mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "etsy.yaml") as f:
                info = yaml.safe_load(f)

            self.shop: Dict[str, Any] = dict(info.get("shop", {}))

            self.listings: List[Dict[str, Any]] = [
                {
                    **l,
                    "listing_id": int(l["listing_id"]),
                    "shop_id": int(l["shop_id"]),
                    "price": float(l["price"]),
                    "quantity": int(l["quantity"]),
                    "taxonomy_id": int(l["taxonomy_id"]),
                    "tags": [t.strip() for t in _csv_list(l.get("tags"))],
                    "materials": [m.strip() for m in _csv_list(l.get("materials"))],
                    "shop_section_id": _opt_int(l.get("shop_section_id")),
                    "processing_min": _opt_int(l.get("processing_min")),
                    "processing_max": _opt_int(l.get("processing_max")),
                    "item_weight": _opt_float(l.get("item_weight")),
                    "item_length": _opt_float(l.get("item_length")),
                    "item_width": _opt_float(l.get("item_width")),
                    "item_height": _opt_float(l.get("item_height")),
                    "views": int(l["views"]),
                    "num_favorers": int(l["num_favorers"]),
                    "shipping_profile_id": _opt_int(l.get("shipping_profile_id")),
                    "return_policy_id": _opt_int(l.get("return_policy_id")),
                    "is_supply": _to_bool(l["is_supply"]),
                    "is_customizable": _to_bool(l["is_customizable"]),
                    "is_personalizable": _to_bool(l["is_personalizable"]),
                }
                for l in info.get("listings", [])
            ]

            self.listing_images: List[Dict[str, Any]] = [
                {
                    **i,
                    "listing_image_id": int(i["listing_image_id"]),
                    "listing_id": int(i["listing_id"]),
                    "shop_id": int(i["shop_id"]),
                    "rank": int(i["rank"]),
                }
                for i in info.get("listing_images", [])
            ]

            self.receipts: List[Dict[str, Any]] = [
                {
                    **r,
                    "receipt_id": int(r["receipt_id"]),
                    "shop_id": int(r["shop_id"]),
                    "buyer_user_id": int(r["buyer_user_id"]),
                    "grandtotal": float(r["grandtotal"]),
                    "subtotal": float(r["subtotal"]),
                    "total_shipping_cost": float(r["total_shipping_cost"]),
                    "total_tax_cost": float(r["total_tax_cost"]),
                    "discount_amt": float(r["discount_amt"]),
                    "is_gift": _to_bool(r["is_gift"]),
                    "gift_message": _opt_str_or_none(r.get("gift_message", "")) or None,
                    "shipped_timestamp": _opt_str_or_none(r.get("shipped_timestamp", "")) or None,
                    "estimated_delivery": _opt_str_or_none(r.get("estimated_delivery", "")) or None,
                    "shipping_carrier": _opt_str_or_none(r.get("shipping_carrier", "")) or None,
                    "tracking_code": _opt_str_or_none(r.get("tracking_code", "")) or None,
                }
                for r in info.get("receipts", [])
            ]

            self.transactions: List[Dict[str, Any]] = [
                {
                    **t,
                    "transaction_id": int(t["transaction_id"]),
                    "receipt_id": int(t["receipt_id"]),
                    "listing_id": int(t["listing_id"]),
                    "shop_id": int(t["shop_id"]),
                    "buyer_user_id": int(t["buyer_user_id"]),
                    "quantity": int(t["quantity"]),
                    "price": float(t["price"]),
                    "shipping_cost": float(t["shipping_cost"]),
                    "is_digital": _to_bool(t["is_digital"]),
                }
                for t in info.get("transactions", [])
            ]

            self.reviews: List[Dict[str, Any]] = [
                {
                    **r,
                    "review_id": int(r["review_id"]),
                    "shop_id": int(r["shop_id"]),
                    "listing_id": int(r["listing_id"]),
                    "buyer_user_id": int(r["buyer_user_id"]),
                    "rating": int(r["rating"]),
                    "image_url": _opt_str_or_none(r.get("image_url", "")) or None,
                }
                for r in info.get("reviews", [])
            ]

            self.shop_sections: List[Dict[str, Any]] = [
                {
                    **s,
                    "shop_section_id": int(s["shop_section_id"]),
                    "shop_id": int(s["shop_id"]),
                    "rank": int(s["rank"]),
                    "active_listing_count": int(s["active_listing_count"]),
                }
                for s in info.get("shop_sections", [])
            ]

            self.shipping_profiles: List[Dict[str, Any]] = [
                {
                    **p,
                    "shipping_profile_id": int(p["shipping_profile_id"]),
                    "shop_id": int(p["shop_id"]),
                    "processing_min": int(p["processing_min"]),
                    "processing_max": int(p["processing_max"]),
                    "min_delivery_days": int(p["min_delivery_days"]),
                    "max_delivery_days": int(p["max_delivery_days"]),
                    "cost": float(p["cost"]),
                    "secondary_cost": float(p["secondary_cost"]),
                }
                for p in info.get("shipping_profiles", [])
            ]

            self.return_policies: List[Dict[str, Any]] = [
                {
                    **p,
                    "return_policy_id": int(p["return_policy_id"]),
                    "shop_id": int(p["shop_id"]),
                    "accepts_returns": _to_bool(p["accepts_returns"]),
                    "accepts_exchanges": _to_bool(p["accepts_exchanges"]),
                    "return_deadline": int(p["return_deadline"]),
                }
                for p in info.get("return_policies", [])
            ]

            self._next_listing_id = max((l["listing_id"] for l in self.listings), default=0) + 1
            self._next_receipt_id = max((r["receipt_id"] for r in self.receipts), default=0) + 1
            self._next_image_id = max((i["listing_image_id"] for i in self.listing_images), default=0) + 1
            self._next_review_id = max((r["review_id"] for r in self.reviews), default=0) + 1
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightEtsy')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"listings": self.listings, "receipts": self.receipts}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _attach_transactions(self, receipt: dict) -> dict:
        txns = [t for t in self.transactions if t["receipt_id"] == receipt["receipt_id"]]
        return {**receipt, "transactions": txns}

    # --- User --------------------------------------------------------------
    def get_current_user(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "user_id": self.shop["user_id"],
            "login_name": self.shop["login_name"],
            "primary_email": None,
            "create_timestamp": self.shop["create_date"],
            "shop_id": self.shop["shop_id"],
        }}

    # --- Shop --------------------------------------------------------------
    def get_shop(self, shop_id: int) -> Dict[str, Any]:
        if shop_id != self.shop["shop_id"]:
            return {"status": "failed", "output": f"Shop {shop_id} not found"}
        return {"status": "ok", "output": {"type": "shop", "shop": self.shop}}

    def update_shop(self, shop_id: int, title: str | None = None, announcement: str | None = None,
                    sale_message: str | None = None, is_vacation: bool | None = None,
                    vacation_message: str | None = None, accepts_custom_requests: bool | None = None,
                    policy_welcome: str | None = None, policy_payment: str | None = None,
                    policy_shipping: str | None = None, policy_refunds: str | None = None) -> Dict[str, Any]:
        if shop_id != self.shop["shop_id"]:
            return {"status": "failed", "output": f"Shop {shop_id} not found"}
        data = {
            "title": title, "announcement": announcement, "sale_message": sale_message,
            "is_vacation": is_vacation, "vacation_message": vacation_message,
            "accepts_custom_requests": accepts_custom_requests, "policy_welcome": policy_welcome,
            "policy_payment": policy_payment, "policy_shipping": policy_shipping,
            "policy_refunds": policy_refunds,
        }
        data = {k: v for k, v in data.items() if v is not None}
        updatable = {"title", "announcement", "sale_message", "is_vacation",
                     "vacation_message", "accepts_custom_requests",
                     "policy_welcome", "policy_payment", "policy_shipping", "policy_refunds"}
        for k, v in data.items():
            if k in updatable:
                self.shop[k] = v
        self.shop["update_date"] = self._now()
        return {"status": "ok", "output": {"type": "shop", "shop": self.shop}}

    # --- Shop Sections -----------------------------------------------------
    def list_shop_sections(self, shop_id: int) -> Dict[str, Any]:
        sections = [s for s in self.shop_sections if s["shop_id"] == shop_id]
        if not sections and shop_id != self.shop["shop_id"]:
            return {"status": "failed", "output": f"Shop {shop_id} not found"}
        return {"status": "ok", "output": {"type": "shop_sections", "count": len(sections), "results": sections}}

    def get_shop_section(self, shop_id: int, section_id: int) -> Dict[str, Any]:
        for s in self.shop_sections:
            if s["shop_id"] == shop_id and s["shop_section_id"] == section_id:
                return {"status": "ok", "output": {"type": "shop_section", "shop_section": s}}
        return {"status": "failed", "output": f"Shop section {section_id} not found"}

    # --- Listings ----------------------------------------------------------
    def list_listings(self, shop_id: int, state: str | None = "active", sort_on: str | None = "created",
                      sort_order: str | None = "desc", limit: int = 25, offset: int = 0,
                      section_id: int | None = None, q: str | None = None) -> Dict[str, Any]:
        results = [l for l in self.listings if l["shop_id"] == shop_id]

        if state:
            results = [l for l in results if l["state"].lower() == state.lower()]
        if section_id:
            results = [l for l in results if l["shop_section_id"] == section_id]
        if q:
            q_l = q.lower()
            results = [l for l in results if q_l in l["title"].lower() or q_l in l["description"].lower()]

        sort_key_map = {
            "created": "created_timestamp",
            "price": "price",
            "updated": "updated_timestamp",
            "score": "views",
        }
        key = sort_key_map.get(sort_on, "created_timestamp")
        reverse = sort_order.lower() == "desc"
        results = sorted(results, key=lambda x: x[key], reverse=reverse)

        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "listings",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_listing(self, listing_id: int) -> Dict[str, Any]:
        for l in self.listings:
            if l["listing_id"] == listing_id:
                return {"status": "ok", "output": {"type": "listing", "listing": l}}
        return {"status": "failed", "output": f"Listing {listing_id} not found"}

    def create_listing(self, shop_id: int, title: str, description: str, price: float, quantity: int,
                       who_made: str, when_made: str, taxonomy_id: int, tags: List[str] | None = None,
                       materials: List[str] | None = None, shop_section_id: int | None = None,
                       shipping_profile_id: int | None = None, return_policy_id: int | None = None,
                       processing_min: int | None = None, processing_max: int | None = None,
                       item_weight: float | None = None, item_weight_unit: str | None = None,
                       item_length: float | None = None, item_width: float | None = None,
                       item_height: float | None = None, item_dimensions_unit: str | None = None,
                       is_supply: bool = False, is_customizable: bool = False,
                       is_personalizable: bool = False) -> Dict[str, Any]:
        data = {
            "title": title, "description": description, "price": price, "quantity": quantity,
            "who_made": who_made, "when_made": when_made, "taxonomy_id": taxonomy_id,
            "tags": tags, "materials": materials, "shop_section_id": shop_section_id,
            "shipping_profile_id": shipping_profile_id, "return_policy_id": return_policy_id,
            "processing_min": processing_min, "processing_max": processing_max,
            "item_weight": item_weight, "item_weight_unit": item_weight_unit,
            "item_length": item_length, "item_width": item_width, "item_height": item_height,
            "item_dimensions_unit": item_dimensions_unit, "is_supply": is_supply,
            "is_customizable": is_customizable, "is_personalizable": is_personalizable,
        }
        required = ["title", "description", "price", "quantity", "who_made", "when_made", "taxonomy_id"]
        for f in required:
            if f not in data or data[f] is None:
                return {"status": "failed", "output": f"Missing required field: {f}"}

        now = self._now()
        listing = {
            "listing_id": self._next_listing_id,
            "shop_id": shop_id,
            "title": data["title"],
            "description": data["description"],
            "price": float(data["price"]),
            "currency_code": "USD",
            "quantity": int(data["quantity"]),
            "taxonomy_id": int(data["taxonomy_id"]),
            "tags": data.get("tags") if data.get("tags") is not None else [],
            "materials": data.get("materials") if data.get("materials") is not None else [],
            "who_made": data["who_made"],
            "when_made": data["when_made"],
            "state": "draft",
            "shop_section_id": data.get("shop_section_id"),
            "processing_min": data.get("processing_min"),
            "processing_max": data.get("processing_max"),
            "item_weight": data.get("item_weight"),
            "item_weight_unit": data.get("item_weight_unit") if data.get("item_weight_unit") is not None else "oz",
            "item_length": data.get("item_length"),
            "item_width": data.get("item_width"),
            "item_height": data.get("item_height"),
            "item_dimensions_unit": data.get("item_dimensions_unit") if data.get("item_dimensions_unit") is not None else "in",
            "views": 0,
            "num_favorers": 0,
            "shipping_profile_id": data.get("shipping_profile_id"),
            "return_policy_id": data.get("return_policy_id"),
            "is_supply": data.get("is_supply", False),
            "is_customizable": data.get("is_customizable", False),
            "is_personalizable": data.get("is_personalizable", False),
            "created_timestamp": now,
            "updated_timestamp": now,
            "ending_timestamp": None,
        }
        self.listings.append(listing)
        self._next_listing_id += 1
        return {"status": "ok", "output": {"type": "listing", "listing": listing}}

    def update_listing(self, listing_id: int, title: str | None = None, description: str | None = None,
                       price: float | None = None, quantity: int | None = None,
                       tags: List[str] | None = None, materials: List[str] | None = None,
                       state: str | None = None, who_made: str | None = None, when_made: str | None = None,
                       taxonomy_id: int | None = None, shop_section_id: int | None = None,
                       shipping_profile_id: int | None = None, return_policy_id: int | None = None,
                       processing_min: int | None = None, processing_max: int | None = None,
                       item_weight: float | None = None, item_weight_unit: str | None = None,
                       item_length: float | None = None, item_width: float | None = None,
                       item_height: float | None = None, item_dimensions_unit: str | None = None,
                       is_supply: bool | None = None, is_customizable: bool | None = None,
                       is_personalizable: bool | None = None) -> Dict[str, Any]:
        data = {
            "title": title, "description": description, "price": price, "quantity": quantity,
            "tags": tags, "materials": materials, "state": state, "who_made": who_made,
            "when_made": when_made, "taxonomy_id": taxonomy_id, "shop_section_id": shop_section_id,
            "shipping_profile_id": shipping_profile_id, "return_policy_id": return_policy_id,
            "processing_min": processing_min, "processing_max": processing_max,
            "item_weight": item_weight, "item_weight_unit": item_weight_unit,
            "item_length": item_length, "item_width": item_width, "item_height": item_height,
            "item_dimensions_unit": item_dimensions_unit, "is_supply": is_supply,
            "is_customizable": is_customizable, "is_personalizable": is_personalizable,
        }
        data = {k: v for k, v in data.items() if v is not None}
        for i, listing in enumerate(self.listings):
            if listing["listing_id"] == listing_id:
                updatable = {
                    "title", "description", "price", "quantity", "tags", "materials",
                    "state", "who_made", "when_made", "taxonomy_id", "shop_section_id",
                    "processing_min", "processing_max", "item_weight", "item_weight_unit",
                    "item_length", "item_width", "item_height", "item_dimensions_unit",
                    "shipping_profile_id", "return_policy_id", "is_supply",
                    "is_customizable", "is_personalizable",
                }
                for k, v in data.items():
                    if k in updatable:
                        if k == "price" and v is not None:
                            self.listings[i][k] = float(v)
                        elif k == "quantity" and v is not None:
                            self.listings[i][k] = int(v)
                        elif k == "taxonomy_id" and v is not None:
                            self.listings[i][k] = int(v)
                        else:
                            self.listings[i][k] = v
                self.listings[i]["updated_timestamp"] = self._now()
                return {"status": "ok", "output": {"type": "listing", "listing": self.listings[i]}}
        return {"status": "failed", "output": f"Listing {listing_id} not found"}

    def delete_listing(self, listing_id: int) -> Dict[str, Any]:
        for i, listing in enumerate(self.listings):
            if listing["listing_id"] == listing_id:
                self.listings.pop(i)
                return {"status": "ok", "output": {"type": "listing", "deleted": True, "listing_id": listing_id}}
        return {"status": "failed", "output": f"Listing {listing_id} not found"}

    # --- Listing Images ----------------------------------------------------
    def list_listing_images(self, listing_id: int) -> Dict[str, Any]:
        images = [img for img in self.listing_images if img["listing_id"] == listing_id]
        if not images:
            if not any(l["listing_id"] == listing_id for l in self.listings):
                return {"status": "failed", "output": f"Listing {listing_id} not found"}
        return {"status": "ok", "output": {"type": "listing_images", "count": len(images), "results": images}}

    def get_listing_image(self, listing_id: int, image_id: int) -> Dict[str, Any]:
        for img in self.listing_images:
            if img["listing_id"] == listing_id and img["listing_image_id"] == image_id:
                return {"status": "ok", "output": {"type": "listing_image", "listing_image": img}}
        return {"status": "failed", "output": f"Image {image_id} not found for listing {listing_id}"}

    def delete_listing_image(self, listing_id: int, image_id: int) -> Dict[str, Any]:
        for i, img in enumerate(self.listing_images):
            if img["listing_id"] == listing_id and img["listing_image_id"] == image_id:
                self.listing_images.pop(i)
                return {"status": "ok", "output": {"type": "listing_image", "deleted": True, "listing_image_id": image_id}}
        return {"status": "failed", "output": f"Image {image_id} not found for listing {listing_id}"}

    # --- Receipts (Orders) -------------------------------------------------
    def list_receipts(self, shop_id: int, status: str | None = None, min_created: str | None = None,
                      max_created: str | None = None, sort_on: str | None = "created",
                      sort_order: str | None = "desc", limit: int = 25, offset: int = 0,
                      was_shipped: bool | None = None, was_paid: bool | None = None) -> Dict[str, Any]:
        results = [r for r in self.receipts if r["shop_id"] == shop_id]

        if status:
            results = [r for r in results if r["status"].lower() == status.lower()]
        if min_created:
            results = [r for r in results if r["created_timestamp"] >= min_created]
        if max_created:
            results = [r for r in results if r["created_timestamp"] <= max_created]
        if was_shipped is True:
            results = [r for r in results if r["shipped_timestamp"]]
        elif was_shipped is False:
            results = [r for r in results if not r["shipped_timestamp"]]
        if was_paid is True:
            results = [r for r in results if r["status"] in ("paid", "completed", "shipped")]
        elif was_paid is False:
            results = [r for r in results if r["status"] == "open"]

        sort_key_map = {
            "created": "created_timestamp",
            "updated": "updated_timestamp",
        }
        key = sort_key_map.get(sort_on, "created_timestamp")
        reverse = sort_order.lower() == "desc"
        results = sorted(results, key=lambda x: x.get(key, ""), reverse=reverse)

        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "receipts",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": [self._attach_transactions(r) for r in page_results],
        }}

    def get_receipt(self, receipt_id: int) -> Dict[str, Any]:
        for r in self.receipts:
            if r["receipt_id"] == receipt_id:
                return {"status": "ok", "output": {"type": "receipt", "receipt": self._attach_transactions(r)}}
        return {"status": "failed", "output": f"Receipt {receipt_id} not found"}

    def update_receipt(self, receipt_id: int, shipping_carrier: str | None = None,
                       tracking_code: str | None = None, was_shipped: bool | None = None) -> Dict[str, Any]:
        data = {"shipping_carrier": shipping_carrier, "tracking_code": tracking_code, "was_shipped": was_shipped}
        data = {k: v for k, v in data.items() if v is not None}
        for i, r in enumerate(self.receipts):
            if r["receipt_id"] == receipt_id:
                updatable = {"shipping_carrier", "tracking_code", "status"}
                for k, v in data.items():
                    if k in updatable:
                        self.receipts[i][k] = v
                if data.get("was_shipped") or data.get("tracking_code"):
                    if not self.receipts[i]["shipped_timestamp"]:
                        self.receipts[i]["shipped_timestamp"] = self._now()
                    if self.receipts[i]["status"] == "paid":
                        self.receipts[i]["status"] = "shipped"
                self.receipts[i]["updated_timestamp"] = self._now()
                return {"status": "ok", "output": {"type": "receipt", "receipt": self._attach_transactions(self.receipts[i])}}
        return {"status": "failed", "output": f"Receipt {receipt_id} not found"}

    # --- Transactions ------------------------------------------------------
    def list_receipt_transactions(self, receipt_id: int) -> Dict[str, Any]:
        txns = [t for t in self.transactions if t["receipt_id"] == receipt_id]
        if not txns:
            if not any(r["receipt_id"] == receipt_id for r in self.receipts):
                return {"status": "failed", "output": f"Receipt {receipt_id} not found"}
        return {"status": "ok", "output": {"type": "transactions", "count": len(txns), "results": txns}}

    def get_transaction(self, transaction_id: int) -> Dict[str, Any]:
        for t in self.transactions:
            if t["transaction_id"] == transaction_id:
                return {"status": "ok", "output": {"type": "transaction", "transaction": t}}
        return {"status": "failed", "output": f"Transaction {transaction_id} not found"}

    # --- Reviews -----------------------------------------------------------
    def _list_reviews(self, shop_id: int | None = None, listing_id: int | None = None,
                      min_rating: int | None = None, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.reviews)
        if shop_id:
            results = [r for r in results if r["shop_id"] == shop_id]
        if listing_id:
            results = [r for r in results if r["listing_id"] == listing_id]
        if min_rating:
            results = [r for r in results if r["rating"] >= min_rating]

        results = sorted(results, key=lambda x: x["created_timestamp"], reverse=True)

        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "reviews",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def list_shop_reviews(self, shop_id: int, listing_id: int | None = None,
                          min_rating: int | None = None, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        return self._list_reviews(shop_id=shop_id, listing_id=listing_id, min_rating=min_rating,
                                  limit=limit, offset=offset)

    def list_listing_reviews(self, listing_id: int, min_rating: int | None = None,
                             limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        return self._list_reviews(listing_id=listing_id, min_rating=min_rating, limit=limit, offset=offset)

    # --- Shipping Profiles -------------------------------------------------
    def list_shipping_profiles(self, shop_id: int) -> Dict[str, Any]:
        profiles = [p for p in self.shipping_profiles if p["shop_id"] == shop_id]
        return {"status": "ok", "output": {"type": "shipping_profiles", "count": len(profiles), "results": profiles}}

    def get_shipping_profile(self, shop_id: int, profile_id: int) -> Dict[str, Any]:
        for p in self.shipping_profiles:
            if p["shop_id"] == shop_id and p["shipping_profile_id"] == profile_id:
                return {"status": "ok", "output": {"type": "shipping_profile", "shipping_profile": p}}
        return {"status": "failed", "output": f"Shipping profile {profile_id} not found"}

    # --- Return Policies ---------------------------------------------------
    def list_return_policies(self, shop_id: int) -> Dict[str, Any]:
        policies = [p for p in self.return_policies if p["shop_id"] == shop_id]
        return {"status": "ok", "output": {"type": "return_policies", "count": len(policies), "results": policies}}

    def get_return_policy(self, shop_id: int, policy_id: int) -> Dict[str, Any]:
        for p in self.return_policies:
            if p["shop_id"] == shop_id and p["return_policy_id"] == policy_id:
                return {"status": "ok", "output": {"type": "return_policy", "return_policy": p}}
        return {"status": "failed", "output": f"Return policy {policy_id} not found"}


if __name__ == "__main__":
    s = EtsySession(seed=12)
    print(s.get_current_user())
    print(s.list_listings(shop_id=29457183))
