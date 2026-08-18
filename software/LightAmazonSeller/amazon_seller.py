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


def _csv_list(v, sep="|"):
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return list(v)
    return [x.strip() for x in str(v).split(sep) if x.strip()]


class AmazonSellerSession:
    """Deterministic sandbox for the Amazon Selling Partner API mock, ported from
    the FastAPI service. Mutations persist within the session."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "amazon_seller.yaml") as f:
                info = yaml.safe_load(f)

            self.catalog: List[Dict[str, Any]] = self._coerce_catalog_items(info.get("catalog_items", []))
            self.orders: List[Dict[str, Any]] = self._coerce_orders(info.get("orders", []))
            self.order_items: List[Dict[str, Any]] = self._coerce_order_items(info.get("order_items", []))
            self.inventory: List[Dict[str, Any]] = self._coerce_inventory(info.get("inventory", []))
            self.returns: List[Dict[str, Any]] = self._coerce_returns(info.get("returns", []))
            self.reports: List[Dict[str, Any]] = self._coerce_reports(info.get("reports", []))
            self.pricing: List[Dict[str, Any]] = self._coerce_pricing(info.get("pricing", []))
            self.seller: Dict[str, Any] = dict(info.get("seller_account", {}))
            self.buying_notes: Dict[str, Any] = dict(info.get("buying_notes_fw26", {}))

            self._next_report_id = 11
            self._next_return_id = 6
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAmazonSeller')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"orders": self.orders, "catalog": self.catalog, "inventory": self.inventory}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _coerce_catalog_items(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "price": _to_float(r.get("price")),
                "quantity": _to_int(r.get("quantity")),
                "itemWeight": _opt_float(r.get("itemWeight")),
                "itemLength": _opt_float(r.get("itemLength")),
                "itemWidth": _opt_float(r.get("itemWidth")),
                "itemHeight": _opt_float(r.get("itemHeight")),
                "bulletPoints": _csv_list(r.get("bulletPoints"), sep="|"),
            })
        return out

    def _coerce_orders(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "OrderTotal_Amount": _to_float(r.get("OrderTotal_Amount")),
                "NumberOfItemsShipped": _to_int(r.get("NumberOfItemsShipped")),
                "NumberOfItemsUnshipped": _to_int(r.get("NumberOfItemsUnshipped")),
                "IsPrime": _to_bool(r.get("IsPrime")),
                "IsBusinessOrder": _to_bool(r.get("IsBusinessOrder")),
                "IsSoldByAB": _to_bool(r.get("IsSoldByAB")),
            })
        return out

    def _coerce_order_items(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "QuantityOrdered": _to_int(r.get("QuantityOrdered")),
                "QuantityShipped": _to_int(r.get("QuantityShipped")),
                "ItemPrice_Amount": _to_float(r.get("ItemPrice_Amount")),
                "ItemTax_Amount": _to_float(r.get("ItemTax_Amount")),
                "PromotionDiscount_Amount": _to_float(r.get("PromotionDiscount_Amount")),
                "IsGift": _to_bool(r.get("IsGift")),
            })
        return out

    def _coerce_inventory(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "totalQuantity": _to_int(r.get("totalQuantity")),
                "inStockSupplyQuantity": _to_int(r.get("inStockSupplyQuantity")),
                "inboundWorkingQuantity": _to_int(r.get("inboundWorkingQuantity")),
                "inboundShippedQuantity": _to_int(r.get("inboundShippedQuantity")),
                "inboundReceivingQuantity": _to_int(r.get("inboundReceivingQuantity")),
                "reservedQuantity": _to_int(r.get("reservedQuantity")),
                "unfulfillableQuantity": _to_int(r.get("unfulfillableQuantity")),
            })
        return out

    def _coerce_returns(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "returnQuantity": _to_int(r.get("returnQuantity")),
                "refundAmount": _to_float(r.get("refundAmount")),
            })
        return out

    def _coerce_reports(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "processingEndTime": (str(r.get("processingEndTime", "")) or None),
                "reportDocumentId": (str(r.get("reportDocumentId", "")) or None),
            })
        return out

    def _coerce_pricing(self, rows):
        out = []
        for r in rows:
            out.append({
                **r,
                "competitivePrice_Amount": _to_float(r.get("competitivePrice_Amount")),
                "listingPrice_Amount": _to_float(r.get("listingPrice_Amount")),
                "landedPrice_Amount": _to_float(r.get("landedPrice_Amount")),
                "shipping_Amount": _to_float(r.get("shipping_Amount")),
                "numberOfOffers": _to_int(r.get("numberOfOffers")),
                "buyBoxPrice_Amount": _to_float(r.get("buyBoxPrice_Amount")),
                "buyBoxWinner": _to_bool(r.get("buyBoxWinner")),
            })
        return out

    # --- Seller Account ----------------------------------------------------
    def get_seller_account(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"type": "seller_account", "seller": self.seller}}

    def get_buying_notes(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"type": "buying_notes", "buyingNotes": self.buying_notes}}

    def get_account_health(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"type": "account_health", "accountHealth": self.seller["accountHealth"]}}

    def get_performance_notifications(self, severity: str | None = None) -> Dict[str, Any]:
        results = list(self.seller["performanceNotifications"])
        if severity:
            results = [n for n in results if n["severity"].upper() == severity.upper()]
        return {"status": "ok", "output": {"type": "notifications", "count": len(results), "results": results}}

    # --- Catalog Items / Listings -----------------------------------------
    def _format_catalog_item(self, item):
        return {
            "asin": item["asin"],
            "attributes": {
                "item_name": [{"value": item["title"], "marketplace_id": "ATVPDKIKX0DER"}],
                "brand": [{"value": item["brand"], "marketplace_id": "ATVPDKIKX0DER"}],
                "bullet_point": [{"value": bp, "marketplace_id": "ATVPDKIKX0DER"} for bp in (item["bulletPoints"] or [])],
                "list_price": [{"currency": item["currency"], "value": item["price"], "marketplace_id": "ATVPDKIKX0DER"}],
                "item_weight": [{"unit": item["itemWeightUnit"], "value": item["itemWeight"], "marketplace_id": "ATVPDKIKX0DER"}] if item["itemWeight"] else [],
                "item_dimensions": [{
                    "length": {"unit": item["itemDimensionsUnit"], "value": item["itemLength"]},
                    "width": {"unit": item["itemDimensionsUnit"], "value": item["itemWidth"]},
                    "height": {"unit": item["itemDimensionsUnit"], "value": item["itemHeight"]},
                    "marketplace_id": "ATVPDKIKX0DER",
                }] if item["itemLength"] else [],
                "condition_type": [{"value": item["condition"], "marketplace_id": "ATVPDKIKX0DER"}],
                "product_type": [{"value": item["productType"], "marketplace_id": "ATVPDKIKX0DER"}],
            },
            "images": [{"marketplaceId": "ATVPDKIKX0DER", "images": [{"variant": "MAIN", "link": item["mainImageUrl"], "height": 1000, "width": 1000}]}],
            "salesRanks": [{"marketplaceId": "ATVPDKIKX0DER", "classificationRanks": [{"classificationId": "172282", "title": "Electronics", "rank": 5420}]}],
            "summaries": [{
                "marketplaceId": "ATVPDKIKX0DER",
                "brandName": item["brand"],
                "itemName": item["title"],
                "productType": item["productType"],
                "itemClassification": "BASE_PRODUCT",
            }],
        }

    def search_catalog_items(self, keywords: str | None = None, identifiers: str | None = None,
                             identifiers_type: str | None = None, page_size: int = 10,
                             status: str | None = None) -> Dict[str, Any]:
        results = list(self.catalog)
        if status:
            results = [r for r in results if r["status"].upper() == status.upper()]
        if identifiers:
            id_list = [i.strip() for i in identifiers.split(",")]
            if identifiers_type and identifiers_type.upper() == "ASIN":
                results = [r for r in results if r["asin"] in id_list]
            elif identifiers_type and identifiers_type.upper() == "SKU":
                results = [r for r in results if r["sku"] in id_list]
            else:
                results = [r for r in results if r["asin"] in id_list or r["sku"] in id_list]
        elif keywords:
            kw = keywords.lower()
            results = [r for r in results if kw in r["title"].lower() or kw in r["description"].lower()]

        total = len(results)
        page_results = results[:page_size]
        return {"status": "ok", "output": {
            "type": "catalog_items",
            "numberOfResults": total,
            "pagination": {"nextToken": None, "previousToken": None},
            "items": [self._format_catalog_item(item) for item in page_results],
        }}

    def get_catalog_item(self, asin: str) -> Dict[str, Any]:
        for item in self.catalog:
            if item["asin"] == asin:
                return {"status": "ok", "output": {"type": "catalog_item", "item": self._format_catalog_item(item)}}
        return {"status": "failed", "output": f"Item with ASIN {asin} not found"}

    def get_listing_item(self, seller_id: str, sku: str) -> Dict[str, Any]:
        item = self._find_listing(seller_id, sku)
        if item:
            return {"status": "ok", "output": {"type": "listing_item", "listing": self._listing_view(item)}}
        return {"status": "failed", "output": f"Listing with SKU {sku} not found for seller {seller_id}"}

    def _find_listing(self, seller_id, sku):
        for item in self.catalog:
            if item["sku"] == sku and item["sellerId"] == seller_id:
                return item
        return None

    def _listing_view(self, item):
        return {
            "sku": item["sku"],
            "asin": item["asin"],
            "sellerId": item["sellerId"],
            "productType": item["productType"],
            "status": item["status"],
            "fulfillmentChannel": item["fulfillmentChannel"],
            "createdDate": item["createdDate"],
            "lastUpdatedDate": item["lastUpdatedDate"],
            "attributes": {
                "item_name": [{"value": item["title"], "marketplace_id": "ATVPDKIKX0DER"}],
                "description": [{"value": item["description"], "marketplace_id": "ATVPDKIKX0DER"}],
                "brand": [{"value": item["brand"], "marketplace_id": "ATVPDKIKX0DER"}],
                "bullet_point": [{"value": bp, "marketplace_id": "ATVPDKIKX0DER"} for bp in (item["bulletPoints"] or [])],
                "list_price": [{"currency": item["currency"], "value": item["price"], "marketplace_id": "ATVPDKIKX0DER"}],
                "quantity": [{"value": item["quantity"], "marketplace_id": "ATVPDKIKX0DER"}],
                "fulfillment_channel": [{"value": item["fulfillmentChannel"], "marketplace_id": "ATVPDKIKX0DER"}],
                "condition_type": [{"value": item["condition"], "marketplace_id": "ATVPDKIKX0DER"}],
                "main_image": [{"link": item["mainImageUrl"], "marketplace_id": "ATVPDKIKX0DER"}],
            },
            "issues": [],
        }

    def create_listing_item(self, seller_id: str, sku: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self._find_listing(seller_id, sku):
            return {"status": "failed", "output": f"Listing with SKU {sku} already exists"}
        now = self._now()
        new_item = {
            "sku": sku,
            "asin": data.get("asin") or f"B0NEW{len(self.catalog):05d}",
            "sellerId": seller_id,
            "title": data.get("title", "") or "",
            "description": data.get("description", "") or "",
            "brand": data.get("brand", "") or "",
            "bulletPoints": data.get("bulletPoints") or [],
            "price": float(data.get("price", 0) or 0),
            "currency": "USD",
            "quantity": int(data.get("quantity", 0) or 0),
            "fulfillmentChannel": data.get("fulfillmentChannel") or "MFN",
            "status": "ACTIVE",
            "condition": data.get("condition") or "NEW",
            "productType": data.get("productType", "") or "",
            "itemWeight": data.get("itemWeight"),
            "itemWeightUnit": data.get("itemWeightUnit") or "pounds",
            "itemLength": data.get("itemLength"),
            "itemWidth": data.get("itemWidth"),
            "itemHeight": data.get("itemHeight"),
            "itemDimensionsUnit": data.get("itemDimensionsUnit") or "inches",
            "mainImageUrl": data.get("mainImageUrl", "") or "",
            "category": data.get("category", "") or "",
            "createdDate": now,
            "lastUpdatedDate": now,
        }
        self.catalog.append(new_item)
        return {"status": "ok", "output": {"type": "listing_item", "status": "ACCEPTED", "sku": sku, "issues": []}}

    def update_listing_item(self, seller_id: str, sku: str, data: Dict[str, Any]) -> Dict[str, Any]:
        item = self._find_listing(seller_id, sku)
        if item:
            updatable = {
                "title", "description", "brand", "bulletPoints", "price",
                "quantity", "fulfillmentChannel", "status", "condition",
                "productType", "mainImageUrl", "category",
            }
            for k, v in data.items():
                if k in updatable:
                    if k == "price" and v is not None:
                        item[k] = float(v)
                    elif k == "quantity" and v is not None:
                        item[k] = int(v)
                    else:
                        item[k] = v
            item["lastUpdatedDate"] = self._now()
            return {"status": "ok", "output": {"type": "listing_item", "status": "ACCEPTED", "sku": sku, "issues": []}}
        return {"status": "failed", "output": f"Listing with SKU {sku} not found for seller {seller_id}"}

    def delete_listing_item(self, seller_id: str, sku: str) -> Dict[str, Any]:
        for i, item in enumerate(self.catalog):
            if item["sku"] == sku and item["sellerId"] == seller_id:
                self.catalog.pop(i)
                return {"status": "ok", "output": {"type": "listing_item", "status": "ACCEPTED", "sku": sku, "deleted": True}}
        return {"status": "failed", "output": f"Listing with SKU {sku} not found for seller {seller_id}"}

    # --- Orders ------------------------------------------------------------
    def _format_order(self, order):
        return {
            "AmazonOrderId": order["AmazonOrderId"],
            "PurchaseDate": order["PurchaseDate"],
            "LastUpdateDate": order["LastUpdateDate"],
            "OrderStatus": order["OrderStatus"],
            "FulfillmentChannel": order["FulfillmentChannel"],
            "SalesChannel": order["SalesChannel"],
            "ShipServiceLevel": order["ShipServiceLevel"],
            "OrderTotal": {
                "CurrencyCode": order["OrderTotal_CurrencyCode"],
                "Amount": str(order["OrderTotal_Amount"]),
            },
            "NumberOfItemsShipped": order["NumberOfItemsShipped"],
            "NumberOfItemsUnshipped": order["NumberOfItemsUnshipped"],
            "PaymentMethod": order["PaymentMethod"],
            "MarketplaceId": order["MarketplaceId"],
            "ShipmentServiceLevelCategory": order["ShipmentServiceLevelCategory"],
            "OrderType": order["OrderType"],
            "EarliestShipDate": order["EarliestShipDate"],
            "LatestShipDate": order["LatestShipDate"],
            "IsPrime": order["IsPrime"],
            "IsBusinessOrder": order["IsBusinessOrder"],
            "IsSoldByAB": order["IsSoldByAB"],
            "ShippingAddress": {
                "Name": order["ShippingAddress_Name"],
                "AddressLine1": order["ShippingAddress_AddressLine1"],
                "City": order["ShippingAddress_City"],
                "StateOrRegion": order["ShippingAddress_StateOrRegion"],
                "PostalCode": order["ShippingAddress_PostalCode"],
                "CountryCode": order["ShippingAddress_CountryCode"],
            },
            "BuyerInfo": {
                "BuyerEmail": order["BuyerEmail"],
                "BuyerName": order["BuyerName"],
            },
        }

    def get_orders(self, created_after: str | None = None, created_before: str | None = None,
                   order_statuses: str | None = None, fulfillment_channels: str | None = None,
                   max_results: int = 100) -> Dict[str, Any]:
        results = list(self.orders)
        if created_after:
            results = [r for r in results if r["PurchaseDate"] >= created_after]
        if created_before:
            results = [r for r in results if r["PurchaseDate"] <= created_before]
        if order_statuses:
            statuses = [s.strip() for s in order_statuses.split(",")]
            results = [r for r in results if r["OrderStatus"] in statuses]
        if fulfillment_channels:
            channels = [c.strip() for c in fulfillment_channels.split(",")]
            results = [r for r in results if r["FulfillmentChannel"] in channels]
        results = sorted(results, key=lambda x: x["PurchaseDate"], reverse=True)
        total = len(results)
        page_results = results[:max_results]
        return {"status": "ok", "output": {
            "type": "orders",
            "count": len(page_results),
            "total": total,
            "offset": 0,
            "limit": max_results,
            "payload": {"Orders": [self._format_order(o) for o in page_results]},
        }}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        for o in self.orders:
            if o["AmazonOrderId"] == order_id:
                return {"status": "ok", "output": {"type": "order", "payload": self._format_order(o)}}
        return {"status": "failed", "output": f"Order {order_id} not found"}

    def get_order_items(self, order_id: str) -> Dict[str, Any]:
        items = [oi for oi in self.order_items if oi["AmazonOrderId"] == order_id]
        if not items:
            if not any(o["AmazonOrderId"] == order_id for o in self.orders):
                return {"status": "failed", "output": f"Order {order_id} not found"}
        formatted = []
        for oi in items:
            formatted.append({
                "OrderItemId": oi["OrderItemId"],
                "ASIN": oi["ASIN"],
                "SellerSKU": oi["SellerSKU"],
                "Title": oi["Title"],
                "QuantityOrdered": oi["QuantityOrdered"],
                "QuantityShipped": oi["QuantityShipped"],
                "ItemPrice": {"CurrencyCode": oi["ItemPrice_CurrencyCode"], "Amount": str(oi["ItemPrice_Amount"])},
                "ItemTax": {"CurrencyCode": oi["ItemPrice_CurrencyCode"], "Amount": str(oi["ItemTax_Amount"])},
                "PromotionDiscount": {"CurrencyCode": oi["ItemPrice_CurrencyCode"], "Amount": str(oi["PromotionDiscount_Amount"])},
                "IsGift": oi["IsGift"],
                "ConditionId": oi["Condition"],
            })
        return {"status": "ok", "output": {
            "type": "order_items",
            "payload": {"AmazonOrderId": order_id, "OrderItems": formatted},
        }}

    def confirm_shipment(self, order_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        for o in self.orders:
            if o["AmazonOrderId"] == order_id:
                if o["OrderStatus"] not in ("Unshipped", "PartiallyShipped"):
                    return {"status": "failed", "output": f"Order {order_id} cannot be shipped (status: {o['OrderStatus']})"}
                o["OrderStatus"] = "Shipped"
                o["LastUpdateDate"] = self._now()
                shipped = o["NumberOfItemsShipped"] + o["NumberOfItemsUnshipped"]
                o["NumberOfItemsShipped"] = shipped
                o["NumberOfItemsUnshipped"] = 0
                for oi in self.order_items:
                    if oi["AmazonOrderId"] == order_id:
                        oi["QuantityShipped"] = oi["QuantityOrdered"]
                return {"status": "ok", "output": {"type": "shipment_confirmation", "status": "SUCCESS", "orderId": order_id}}
        return {"status": "failed", "output": f"Order {order_id} not found"}

    # --- Inventory ---------------------------------------------------------
    def get_inventory_summaries(self, seller_skus: str | None = None,
                                granularity_type: str = "Marketplace",
                                marketplace_id: str = "ATVPDKIKX0DER") -> Dict[str, Any]:
        results = list(self.inventory)
        if seller_skus:
            sku_list = [s.strip() for s in seller_skus.split(",")]
            results = [r for r in results if r["sellerSku"] in sku_list]
        formatted = []
        for inv in results:
            formatted.append({
                "asin": inv["asin"],
                "fnSku": inv["fnSku"],
                "sellerSku": inv["sellerSku"],
                "productName": inv["productName"],
                "condition": inv["condition"],
                "granularity": {"granularityType": granularity_type, "granularityId": marketplace_id},
                "inventoryDetails": {
                    "fulfillableQuantity": inv["inStockSupplyQuantity"],
                    "inboundWorkingQuantity": inv["inboundWorkingQuantity"],
                    "inboundShippedQuantity": inv["inboundShippedQuantity"],
                    "inboundReceivingQuantity": inv["inboundReceivingQuantity"],
                    "totalQuantity": inv["totalQuantity"],
                    "reservedQuantity": inv["reservedQuantity"],
                    "unfulfillableQuantity": inv["unfulfillableQuantity"],
                },
                "lastUpdatedTime": inv["lastUpdatedTime"],
            })
        return {"status": "ok", "output": {
            "type": "inventory_summaries",
            "payload": {
                "granularity": {"granularityType": granularity_type, "granularityId": marketplace_id},
                "inventorySummaries": formatted,
            },
            "pagination": {"nextToken": None},
        }}

    def update_inventory(self, seller_sku: str, quantity: int) -> Dict[str, Any]:
        for inv in self.inventory:
            if inv["sellerSku"] == seller_sku:
                inv["totalQuantity"] = int(quantity)
                inv["inStockSupplyQuantity"] = int(quantity)
                inv["lastUpdatedTime"] = self._now()
                return {"status": "ok", "output": {"type": "inventory_update", "status": "SUCCESS", "sellerSku": seller_sku}}
        return {"status": "failed", "output": f"Inventory for SKU {seller_sku} not found"}

    # --- Reports -----------------------------------------------------------
    def _report_view(self, r):
        return {
            "reportId": r["reportId"],
            "reportType": r["reportType"],
            "processingStatus": r["reportStatus"],
            "dataStartTime": r["dataStartTime"],
            "dataEndTime": r["dataEndTime"],
            "createdTime": r["createdTime"],
            "processingEndTime": r["processingEndTime"],
            "reportDocumentId": r["reportDocumentId"],
        }

    def get_reports(self, report_types: str | None = None, processing_statuses: str | None = None) -> Dict[str, Any]:
        results = list(self.reports)
        if report_types:
            type_list = [t.strip() for t in report_types.split(",")]
            results = [r for r in results if r["reportType"] in type_list]
        if processing_statuses:
            status_list = [s.strip() for s in processing_statuses.split(",")]
            results = [r for r in results if r["reportStatus"] in status_list]
        results = sorted(results, key=lambda x: x["createdTime"], reverse=True)
        return {"status": "ok", "output": {
            "type": "reports",
            "payload": {"reports": [self._report_view(r) for r in results]},
        }}

    def get_report(self, report_id: str) -> Dict[str, Any]:
        for r in self.reports:
            if r["reportId"] == report_id:
                return {"status": "ok", "output": {"type": "report", "payload": self._report_view(r)}}
        return {"status": "failed", "output": f"Report {report_id} not found"}

    def create_report(self, report_type: str, data_start_time: str, data_end_time: str) -> Dict[str, Any]:
        now = self._now()
        report = {
            "reportId": f"REP-{self._next_report_id:03d}",
            "reportType": report_type,
            "reportStatus": "IN_QUEUE",
            "dataStartTime": data_start_time,
            "dataEndTime": data_end_time,
            "createdTime": now,
            "processingEndTime": None,
            "reportDocumentId": None,
        }
        self.reports.append(report)
        self._next_report_id += 1
        return {"status": "ok", "output": {"type": "report_created", "payload": {"reportId": report["reportId"]}}}

    # --- Product Pricing ---------------------------------------------------
    def get_competitive_pricing(self, asin: str | None = None, sku: str | None = None) -> Dict[str, Any]:
        results = list(self.pricing)
        if asin:
            results = [r for r in results if r["asin"] == asin]
        elif sku:
            results = [r for r in results if r["sellerSku"] == sku]
        if not results:
            identifier = asin or sku
            return {"status": "failed", "output": f"Pricing not found for {identifier}"}
        formatted = []
        for p in results:
            formatted.append({
                "ASIN": p["asin"],
                "Product": {
                    "CompetitivePricing": {
                        "CompetitivePrices": [{
                            "CompetitivePriceId": "1",
                            "Price": {
                                "ListingPrice": {"CurrencyCode": p["competitivePrice_CurrencyCode"], "Amount": str(p["competitivePrice_Amount"])},
                                "LandedPrice": {"CurrencyCode": p["competitivePrice_CurrencyCode"], "Amount": str(p["landedPrice_Amount"])},
                                "Shipping": {"CurrencyCode": p["competitivePrice_CurrencyCode"], "Amount": str(p["shipping_Amount"])},
                            },
                            "condition": p["competitivePrice_Condition"],
                            "belongsToRequester": p["buyBoxWinner"],
                        }],
                        "NumberOfOfferListings": [{"condition": "New", "Count": p["numberOfOffers"]}],
                    },
                    "Offers": [{
                        "BuyBoxPrices": [{
                            "condition": "New",
                            "LandedPrice": {"CurrencyCode": p["buyBoxPrice_CurrencyCode"], "Amount": str(p["buyBoxPrice_Amount"])},
                            "ListingPrice": {"CurrencyCode": p["buyBoxPrice_CurrencyCode"], "Amount": str(p["buyBoxPrice_Amount"])},
                            "Shipping": {"CurrencyCode": p["buyBoxPrice_CurrencyCode"], "Amount": "0.00"},
                        }],
                        "NumberOfOffers": [{"condition": "New", "fulfillmentChannel": "Amazon", "Count": p["numberOfOffers"]}],
                    }],
                },
            })
        return {"status": "ok", "output": {
            "type": "competitive_pricing",
            "payload": formatted if len(formatted) > 1 else formatted[0],
        }}

    def get_item_offers(self, asin: str) -> Dict[str, Any]:
        pricing = [p for p in self.pricing if p["asin"] == asin]
        if not pricing:
            return {"status": "failed", "output": f"Offers not found for ASIN {asin}"}
        p = pricing[0]
        return {"status": "ok", "output": {
            "type": "item_offers",
            "payload": {
                "ASIN": asin,
                "status": "Success",
                "ItemCondition": "New",
                "Summary": {
                    "LowestPrices": [{
                        "condition": "New",
                        "fulfillmentChannel": "Amazon",
                        "LandedPrice": {"CurrencyCode": "USD", "Amount": str(p["competitivePrice_Amount"])},
                        "ListingPrice": {"CurrencyCode": "USD", "Amount": str(p["competitivePrice_Amount"])},
                        "Shipping": {"CurrencyCode": "USD", "Amount": str(p["shipping_Amount"])},
                    }],
                    "BuyBoxPrices": [{
                        "condition": "New",
                        "LandedPrice": {"CurrencyCode": "USD", "Amount": str(p["buyBoxPrice_Amount"])},
                        "ListingPrice": {"CurrencyCode": "USD", "Amount": str(p["buyBoxPrice_Amount"])},
                        "Shipping": {"CurrencyCode": "USD", "Amount": "0.00"},
                    }],
                    "NumberOfOffers": [{"condition": "New", "fulfillmentChannel": "Amazon", "Count": p["numberOfOffers"]}],
                    "BuyBoxEligibleOffers": [{"condition": "New", "fulfillmentChannel": "Amazon", "Count": p["numberOfOffers"]}],
                },
                "Offers": [{
                    "SellerFeedbackRating": {"SellerPositiveFeedbackRating": 96.5, "FeedbackCount": 1247},
                    "ListingPrice": {"CurrencyCode": "USD", "Amount": str(p["listingPrice_Amount"])},
                    "Shipping": {"CurrencyCode": "USD", "Amount": str(p["shipping_Amount"])},
                    "IsBuyBoxWinner": p["buyBoxWinner"],
                    "IsFulfilledByAmazon": True,
                }],
            },
        }}

    # --- Returns -----------------------------------------------------------
    def get_returns(self, status: str | None = None, order_id: str | None = None) -> Dict[str, Any]:
        results = list(self.returns)
        if status:
            results = [r for r in results if r["returnStatus"].upper() == status.upper()]
        if order_id:
            results = [r for r in results if r["AmazonOrderId"] == order_id]
        results = sorted(results, key=lambda x: x["returnDate"], reverse=True)
        return {"status": "ok", "output": {
            "type": "returns",
            "count": len(results),
            "total": len(results),
            "offset": 0,
            "limit": 100,
            "results": results,
        }}

    def get_return(self, return_id: str) -> Dict[str, Any]:
        for r in self.returns:
            if r["returnId"] == return_id:
                return {"status": "ok", "output": {"type": "return", "return": r}}
        return {"status": "failed", "output": f"Return {return_id} not found"}

    def authorize_return(self, return_id: str) -> Dict[str, Any]:
        for r in self.returns:
            if r["returnId"] == return_id:
                if r["returnStatus"] != "Authorized":
                    return {"status": "failed", "output": f"Return {return_id} is not in Authorized status"}
                r["returnStatus"] = "Completed"
                r["resolution"] = "REFUND"
                return {"status": "ok", "output": {"type": "return_authorization", "status": "SUCCESS", "returnId": return_id}}
        return {"status": "failed", "output": f"Return {return_id} not found"}

    def close_return(self, return_id: str) -> Dict[str, Any]:
        for r in self.returns:
            if r["returnId"] == return_id:
                r["returnStatus"] = "Closed"
                r["resolution"] = "CLOSED"
                return {"status": "ok", "output": {"type": "return_close", "status": "SUCCESS", "returnId": return_id}}
        return {"status": "failed", "output": f"Return {return_id} not found"}


if __name__ == "__main__":
    s = AmazonSellerSession(seed=12)
    print(s.get_seller_account())
    print(s.get_orders())
