from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGmailSession
except ImportError:
    from software.LightGmail.session import LightGmailSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightGmail")

session_dict: Dict[str, LightGmailSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None, fixture: str | None = None):
	session = LightGmailSession(os_cfg=os_cfg, seed=seed, fixture=fixture)
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
        "output": session.gmail_session.get_session_dict(),
    }


@mcp.tool
async def get_profile(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.get_profile()


@mcp.tool
async def list_labels(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.list_labels()


@mcp.tool
async def get_label(label_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.get_label(label_id)


@mcp.tool
async def create_label(name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.create_label(name)


@mcp.tool
async def list_messages(session_id: str, query: str = "", max_results: int = 25, label_ids: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.list_messages(query, max_results, label_ids)


@mcp.tool
async def get_message(message_id: str, session_id: str, fmt: str = "full"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.get_message(message_id, fmt)


@mcp.tool
async def send_message(to_addr: str, subject: str, body: str, session_id: str, cc: str | None = None, thread_id: str | None = None, from_addr: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.send_message(to_addr, subject, body, cc, thread_id, from_addr)


@mcp.tool
async def modify_message(message_id: str, session_id: str, add_labels: List[str] | None = None, remove_labels: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.modify_message(message_id, add_labels, remove_labels)


@mcp.tool
async def trash_message(message_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.trash_message(message_id)


@mcp.tool
async def delete_message(message_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.delete_message(message_id)


@mcp.tool
async def list_threads(session_id: str, query: str = ""):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.list_threads(query)


@mcp.tool
async def get_thread(thread_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.get_thread(thread_id)


@mcp.tool
async def list_drafts(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.list_drafts()


@mcp.tool
async def get_draft(draft_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.get_draft(draft_id)


@mcp.tool
async def create_draft(to_addr: str, subject: str, body: str, session_id: str, cc: str | None = None, thread_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.create_draft(to_addr, subject, body, cc, thread_id)


@mcp.tool
async def send_draft(draft_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gmail_session.send_draft(draft_id)
