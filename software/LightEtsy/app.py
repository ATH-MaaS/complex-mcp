from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightEtsySession
except ImportError:
    from software.LightEtsy.session import LightEtsySession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightEtsy")

session_dict: Dict[str, LightEtsySession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightEtsySession(os_cfg=os_cfg, seed=seed)
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
        "output": session.etsy_session.get_session_dict(),
    }


@mcp.tool
async def get_current_user(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_current_user()


@mcp.tool
async def get_shop(shop_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_shop(shop_id)


@mcp.tool
async def update_shop(shop_id: int, session_id: str, title: str | None = None, announcement: str | None = None, sale_message: str | None = None, is_vacation: bool | None = None, vacation_message: str | None = None, accepts_custom_requests: bool | None = None, policy_welcome: str | None = None, policy_payment: str | None = None, policy_shipping: str | None = None, policy_refunds: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.update_shop(shop_id, title, announcement, sale_message, is_vacation, vacation_message, accepts_custom_requests, policy_welcome, policy_payment, policy_shipping, policy_refunds)


@mcp.tool
async def list_shop_sections(shop_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_shop_sections(shop_id)


@mcp.tool
async def get_shop_section(shop_id: int, section_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_shop_section(shop_id, section_id)


@mcp.tool
async def list_listings(shop_id: int, session_id: str, state: str | None = "active", sort_on: str | None = "created", sort_order: str | None = "desc", limit: int = 25, offset: int = 0, section_id: int | None = None, q: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_listings(shop_id, state, sort_on, sort_order, limit, offset, section_id, q)


@mcp.tool
async def get_listing(listing_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_listing(listing_id)


@mcp.tool
async def create_listing(shop_id: int, title: str, description: str, price: float, quantity: int, who_made: str, when_made: str, taxonomy_id: int, session_id: str, tags: List[str] | None = None, materials: List[str] | None = None, shop_section_id: int | None = None, shipping_profile_id: int | None = None, return_policy_id: int | None = None, processing_min: int | None = None, processing_max: int | None = None, item_weight: float | None = None, item_weight_unit: str | None = None, item_length: float | None = None, item_width: float | None = None, item_height: float | None = None, item_dimensions_unit: str | None = None, is_supply: bool = False, is_customizable: bool = False, is_personalizable: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.create_listing(shop_id, title, description, price, quantity, who_made, when_made, taxonomy_id, tags, materials, shop_section_id, shipping_profile_id, return_policy_id, processing_min, processing_max, item_weight, item_weight_unit, item_length, item_width, item_height, item_dimensions_unit, is_supply, is_customizable, is_personalizable)


@mcp.tool
async def update_listing(listing_id: int, session_id: str, title: str | None = None, description: str | None = None, price: float | None = None, quantity: int | None = None, tags: List[str] | None = None, materials: List[str] | None = None, state: str | None = None, who_made: str | None = None, when_made: str | None = None, taxonomy_id: int | None = None, shop_section_id: int | None = None, shipping_profile_id: int | None = None, return_policy_id: int | None = None, processing_min: int | None = None, processing_max: int | None = None, item_weight: float | None = None, item_weight_unit: str | None = None, item_length: float | None = None, item_width: float | None = None, item_height: float | None = None, item_dimensions_unit: str | None = None, is_supply: bool | None = None, is_customizable: bool | None = None, is_personalizable: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.update_listing(listing_id, title, description, price, quantity, tags, materials, state, who_made, when_made, taxonomy_id, shop_section_id, shipping_profile_id, return_policy_id, processing_min, processing_max, item_weight, item_weight_unit, item_length, item_width, item_height, item_dimensions_unit, is_supply, is_customizable, is_personalizable)


@mcp.tool
async def delete_listing(listing_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.delete_listing(listing_id)


@mcp.tool
async def list_listing_images(listing_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_listing_images(listing_id)


@mcp.tool
async def get_listing_image(listing_id: int, image_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_listing_image(listing_id, image_id)


@mcp.tool
async def delete_listing_image(listing_id: int, image_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.delete_listing_image(listing_id, image_id)


@mcp.tool
async def list_receipts(shop_id: int, session_id: str, status: str | None = None, min_created: str | None = None, max_created: str | None = None, sort_on: str | None = "created", sort_order: str | None = "desc", limit: int = 25, offset: int = 0, was_shipped: bool | None = None, was_paid: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_receipts(shop_id, status, min_created, max_created, sort_on, sort_order, limit, offset, was_shipped, was_paid)


@mcp.tool
async def get_receipt(receipt_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_receipt(receipt_id)


@mcp.tool
async def update_receipt(receipt_id: int, session_id: str, shipping_carrier: str | None = None, tracking_code: str | None = None, was_shipped: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.update_receipt(receipt_id, shipping_carrier, tracking_code, was_shipped)


@mcp.tool
async def list_receipt_transactions(receipt_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_receipt_transactions(receipt_id)


@mcp.tool
async def get_transaction(transaction_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_transaction(transaction_id)


@mcp.tool
async def list_shop_reviews(shop_id: int, session_id: str, listing_id: int | None = None, min_rating: int | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_shop_reviews(shop_id, listing_id, min_rating, limit, offset)


@mcp.tool
async def list_listing_reviews(listing_id: int, session_id: str, min_rating: int | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_listing_reviews(listing_id, min_rating, limit, offset)


@mcp.tool
async def list_shipping_profiles(shop_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_shipping_profiles(shop_id)


@mcp.tool
async def get_shipping_profile(shop_id: int, profile_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_shipping_profile(shop_id, profile_id)


@mcp.tool
async def list_return_policies(shop_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.list_return_policies(shop_id)


@mcp.tool
async def get_return_policy(shop_id: int, policy_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.etsy_session.get_return_policy(shop_id, policy_id)
