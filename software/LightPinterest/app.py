from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightPinterestSession
except ImportError:
    from software.LightPinterest.session import LightPinterestSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightPinterest")

session_dict: Dict[str, LightPinterestSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightPinterestSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.pinterest_session.get_session_dict(),
    }


@mcp.tool
async def get_user_account(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_user_account()


@mcp.tool
async def get_user_analytics(session_id: str, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_user_analytics(start_date, end_date)


@mcp.tool
async def list_boards(session_id: str, privacy: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_boards(privacy, limit, offset)


@mcp.tool
async def get_board(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_board(board_id)


@mcp.tool
async def create_board(name: str, session_id: str, description: str | None = None, privacy: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.create_board(name, description, privacy)


@mcp.tool
async def update_board(board_id: str, session_id: str, name: str | None = None, description: str | None = None, privacy: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.update_board(board_id, name, description, privacy)


@mcp.tool
async def delete_board(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.delete_board(board_id)


@mcp.tool
async def list_board_pins(board_id: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_board_pins(board_id, limit, offset)


@mcp.tool
async def list_board_sections(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_board_sections(board_id)


@mcp.tool
async def create_board_section(board_id: str, name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.create_board_section(board_id, name)


@mcp.tool
async def list_section_pins(board_id: str, section_id: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_section_pins(board_id, section_id, limit, offset)


@mcp.tool
async def list_pins(session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_pins(limit, offset)


@mcp.tool
async def get_pin(pin_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_pin(pin_id)


@mcp.tool
async def create_pin(board_id: str, title: str, session_id: str, description: str | None = None, link: str | None = None, media_type: str | None = None, board_section_id: str | None = None, dominant_color: str | None = None, alt_text: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.create_pin(board_id, title, description, link, media_type, board_section_id, dominant_color, alt_text)


@mcp.tool
async def update_pin(pin_id: str, session_id: str, title: str | None = None, description: str | None = None, link: str | None = None, board_id: str | None = None, board_section_id: str | None = None, alt_text: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.update_pin(pin_id, title, description, link, board_id, board_section_id, alt_text)


@mcp.tool
async def delete_pin(pin_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.delete_pin(pin_id)


@mcp.tool
async def get_pin_analytics(pin_id: str, session_id: str, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_pin_analytics(pin_id, start_date, end_date)


@mcp.tool
async def search_pins(query: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.search_pins(query, limit, offset)


@mcp.tool
async def get_media_upload_status(media_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_media_upload_status(media_id)


@mcp.tool
async def list_ad_accounts(session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_ad_accounts(limit, offset)


@mcp.tool
async def get_ad_account(ad_account_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.get_ad_account(ad_account_id)


@mcp.tool
async def list_campaigns(ad_account_id: str, session_id: str, status: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.pinterest_session.list_campaigns(ad_account_id, status, limit, offset)
