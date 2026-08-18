from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightKlaviyoSession
except ImportError:
    from software.LightKlaviyo.session import LightKlaviyoSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightKlaviyo")

session_dict: Dict[str, LightKlaviyoSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightKlaviyoSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.klaviyo_session.get_session_dict(),
    }


@mcp.tool
async def list_profiles(session_id: str, email: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.klaviyo_session.list_profiles(email)


@mcp.tool
async def get_profile(profile_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.klaviyo_session.get_profile(profile_id)


@mcp.tool
async def create_profile(email: str, session_id: str, first_name: str = "", last_name: str = "", phone_number: str = "", organization: str = "", title: str = "", city: str = "", region: str = "", country: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.klaviyo_session.create_profile(email, first_name, last_name, phone_number, organization, title, city, region, country)


@mcp.tool
async def list_lists(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.klaviyo_session.list_lists()


@mcp.tool
async def list_campaigns(session_id: str, status: str | None = None, channel: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.klaviyo_session.list_campaigns(status, channel)
