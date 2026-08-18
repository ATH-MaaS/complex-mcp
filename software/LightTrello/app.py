from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTrelloSession
except ImportError:
    from software.LightTrello.session import LightTrelloSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTrello")

session_dict: Dict[str, LightTrelloSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTrelloSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.trello_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.get_me()


@mcp.tool
async def list_my_boards(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.list_my_boards()


@mcp.tool
async def get_board(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.get_board(board_id)


@mcp.tool
async def list_board_lists(board_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.list_board_lists(board_id)


@mcp.tool
async def list_cards(list_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.list_cards(list_id)


@mcp.tool
async def get_card(card_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.get_card(card_id)


@mcp.tool
async def create_card(id_list: str, name: str, session_id: str, desc: str = "", due: str | None = None, member_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.create_card(id_list, name, desc, due, member_ids)


@mcp.tool
async def update_card(card_id: str, session_id: str, name: str | None = None, desc: str | None = None, id_list: str | None = None, due: str | None = None, closed: bool | None = None, pos: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.update_card(card_id, name, desc, id_list, due, closed, pos)


@mcp.tool
async def delete_card(card_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.delete_card(card_id)


@mcp.tool
async def list_card_checklists(card_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.list_card_checklists(card_id)


@mcp.tool
async def create_checklist(id_card: str, session_id: str, name: str = "Checklist"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.trello_session.create_checklist(id_card, name)
