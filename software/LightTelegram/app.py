from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTelegramSession
except ImportError:
    from software.LightTelegram.session import LightTelegramSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTelegram")

session_dict: Dict[str, LightTelegramSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTelegramSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.telegram_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.get_me()


@mcp.tool
async def send_message(chat_id: int, text: str, session_id: str, reply_to_message_id: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.send_message(chat_id, text, reply_to_message_id)


@mcp.tool
async def send_photo(chat_id: int, photo: str, session_id: str, caption: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.send_photo(chat_id, photo, caption)


@mcp.tool
async def edit_message_text(chat_id: int, message_id: int, text: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.edit_message_text(chat_id, message_id, text)


@mcp.tool
async def delete_message(chat_id: int, message_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.delete_message(chat_id, message_id)


@mcp.tool
async def get_chat(chat_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.get_chat(chat_id)


@mcp.tool
async def get_chat_member(chat_id: int, user_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.get_chat_member(chat_id, user_id)


@mcp.tool
async def get_updates(session_id: str, offset: int | None = None, limit: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.telegram_session.get_updates(offset, limit)
