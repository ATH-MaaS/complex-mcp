from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightMailgunSession
except ImportError:
    from software.LightMailgun.session import LightMailgunSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightMailgun")

session_dict: Dict[str, LightMailgunSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightMailgunSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.mailgun_session.get_session_dict(),
    }


@mcp.tool
async def send_message(domain: str, sender: str, to: str, session_id: str, subject: str = "", text: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailgun_session.send_message(domain, sender, to, subject, text)


@mcp.tool
async def get_events(domain: str, session_id: str, event: str | None = None, recipient: str | None = None, limit: int = 300):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailgun_session.get_events(domain, event, recipient, limit)


@mcp.tool
async def get_stats_total(domain: str, session_id: str, event: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailgun_session.get_stats_total(domain, event)


@mcp.tool
async def list_members(address: str, session_id: str, subscribed: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.mailgun_session.list_members(address, subscribed)
