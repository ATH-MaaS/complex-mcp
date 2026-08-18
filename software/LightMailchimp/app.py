from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMailchimpSession
except ImportError:
    from software.LightMailchimp.session import LightMailchimpSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightMailchimp")

session_dict: Dict[str, LightMailchimpSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMailchimpSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.mailchimp_session.get_session_dict(),
    }


@mcp.tool
async def list_lists(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.list_lists()


@mcp.tool
async def get_list(list_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.get_list(list_id)


@mcp.tool
async def list_members(list_id: str, session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.list_members(list_id, status)


@mcp.tool
async def get_member(list_id: str, subscriber_hash: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.get_member(list_id, subscriber_hash)


@mcp.tool
async def create_member(list_id: str, email_address: str, session_id: str, status: str = "subscribed", full_name: str = "", member_rating: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.create_member(list_id, email_address, status, full_name, member_rating)


@mcp.tool
async def update_member(list_id: str, subscriber_hash: str, session_id: str, status: str | None = None, full_name: str | None = None, member_rating: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.update_member(list_id, subscriber_hash, status, full_name, member_rating)


@mcp.tool
async def list_campaigns(session_id: str, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.list_campaigns(status)


@mcp.tool
async def get_campaign(campaign_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.get_campaign(campaign_id)


@mcp.tool
async def create_campaign(list_id: str, subject_line: str, from_name: str, reply_to: str, session_id: str, title: str = "", type_: str = "regular"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.create_campaign(list_id, subject_line, from_name, reply_to, title, type_)


@mcp.tool
async def send_campaign(campaign_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.send_campaign(campaign_id)


@mcp.tool
async def get_report(campaign_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailchimp_session.get_report(campaign_id)
