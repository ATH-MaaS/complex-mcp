from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightOutlookSession
except ImportError:
    from software.LightOutlook.session import LightOutlookSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightOutlook")

session_dict: Dict[str, LightOutlookSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightOutlookSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.outlook_session.get_session_dict(),
    }


@mcp.tool
async def list_messages(session_id: str, is_read: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.outlook_session.list_messages(is_read)


@mcp.tool
async def get_message(message_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.outlook_session.get_message(message_id)


@mcp.tool
async def send_mail(to_recipients: List[str], session_id: str, subject: str | None = None, content: str | None = None, content_type: str = "HTML"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.outlook_session.send_mail(subject, content, to_recipients, content_type)


@mcp.tool
async def list_events(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.outlook_session.list_events()


@mcp.tool
async def list_contacts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.outlook_session.list_contacts()
