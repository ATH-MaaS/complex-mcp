from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightAmazonSellerSession
except ImportError:
    from software.LightAmazonSeller.session import LightAmazonSellerSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("amazon-seller")

session_dict: Dict[str, LightAmazonSellerSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightAmazonSellerSession(os_cfg=os_cfg, seed=seed)
	session_dict[session.session_id] = session
	logger.info(f"A new user logged in! [{session.session_id}]")
	return {
		"status": "ok",
		"session_id": session.session_id,
		"session_info": {
			"status": "ok",
			"output": {}
        }
    }


@mcp.tool
async def logout(session_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	del session_dict[session_id]
	logger.info(f"A user logged out! [{session_id}]")
	return {
        "status": "ok",
        "output": session.amazon_seller_session.get_session_dict(),
    }


@mcp.tool
async def get_seller_account(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_seller_account()


@mcp.tool
async def get_account_health(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_account_health()


@mcp.tool
async def get_buying_notes(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_buying_notes()


@mcp.tool
async def get_performance_notifications(session_id: str, severity: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_performance_notifications(severity)


@mcp.tool
async def search_catalog_items(session_id: str, keywords: str | None = None, identifiers: str | None = None, identifiers_type: str | None = None, page_size: int = 10, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.search_catalog_items(keywords, identifiers, identifiers_type, page_size, status)


@mcp.tool
async def get_catalog_item(asin: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_catalog_item(asin)


@mcp.tool
async def get_listing_item(seller_id: str, sku: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_listing_item(seller_id, sku)


@mcp.tool
async def create_listing_item(seller_id: str, sku: str, data: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.create_listing_item(seller_id, sku, data)


@mcp.tool
async def update_listing_item(seller_id: str, sku: str, data: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.update_listing_item(seller_id, sku, data)


@mcp.tool
async def delete_listing_item(seller_id: str, sku: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.delete_listing_item(seller_id, sku)


@mcp.tool
async def get_orders(session_id: str, created_after: str | None = None, created_before: str | None = None, order_statuses: str | None = None, fulfillment_channels: str | None = None, max_results: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_orders(created_after, created_before, order_statuses, fulfillment_channels, max_results)


@mcp.tool
async def get_order(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_order(order_id)


@mcp.tool
async def get_order_items(order_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_order_items(order_id)


@mcp.tool
async def confirm_shipment(order_id: str, data: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.confirm_shipment(order_id, data)


@mcp.tool
async def get_inventory_summaries(session_id: str, seller_skus: str | None = None, granularity_type: str = "Marketplace", marketplace_id: str = "ATVPDKIKX0DER"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_inventory_summaries(seller_skus, granularity_type, marketplace_id)


@mcp.tool
async def update_inventory(seller_sku: str, quantity: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.update_inventory(seller_sku, quantity)


@mcp.tool
async def get_reports(session_id: str, report_types: str | None = None, processing_statuses: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_reports(report_types, processing_statuses)


@mcp.tool
async def get_report(report_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_report(report_id)


@mcp.tool
async def create_report(report_type: str, data_start_time: str, data_end_time: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.create_report(report_type, data_start_time, data_end_time)


@mcp.tool
async def get_competitive_pricing(session_id: str, asin: str | None = None, sku: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_competitive_pricing(asin, sku)


@mcp.tool
async def get_item_offers(asin: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_item_offers(asin)


@mcp.tool
async def get_returns(session_id: str, status: str | None = None, order_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_returns(status, order_id)


@mcp.tool
async def get_return(return_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.get_return(return_id)


@mcp.tool
async def authorize_return(return_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.authorize_return(return_id)


@mcp.tool
async def close_return(return_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.amazon_seller_session.close_return(return_id)
