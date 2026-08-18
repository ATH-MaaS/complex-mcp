from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTwilioSession
except ImportError:
    from software.LightTwilio.session import LightTwilioSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTwilio")

session_dict: Dict[str, LightTwilioSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTwilioSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.twilio_session.get_session_dict(),
    }


@mcp.tool
async def list_messages(session_id: str, to: str | None = None, from_: str | None = None, status: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.list_messages(to, from_, status, page_size)


@mcp.tool
async def get_message(sid: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.get_message(sid)


@mcp.tool
async def create_message(to: str, from_: str, session_id: str, body: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.create_message(to, from_, body)


@mcp.tool
async def list_calls(session_id: str, to: str | None = None, from_: str | None = None, status: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.list_calls(to, from_, status, page_size)


@mcp.tool
async def create_call(to: str, from_: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.create_call(to, from_)


@mcp.tool
async def list_phone_numbers(session_id: str, phone_number: str | None = None, page_size: int = 50):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.list_phone_numbers(phone_number, page_size)


@mcp.tool
async def lookup(phone_number: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twilio_session.lookup(phone_number)
