from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGoogleDriveSession
except ImportError:
    from software.LightGoogleDrive.session import LightGoogleDriveSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("google-drive")

session_dict: Dict[str, LightGoogleDriveSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGoogleDriveSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.google_drive_session.get_session_dict(),
    }


@mcp.tool
async def get_about(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.get_about()


@mcp.tool
async def list_files(session_id: str, q: str = "", page_size: int = 100, page_token: str | None = None, order_by: str = "modifiedTime desc"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.list_files(q, page_size, page_token, order_by)


@mcp.tool
async def get_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.get_file(file_id)


@mcp.tool
async def download_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.download_file(file_id)


@mcp.tool
async def create_file(name: str, mime_type: str, session_id: str, parent_id: str | None = None, owner_email: str = "amelia@orbit-labs.com", size: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.create_file(name, mime_type, parent_id, owner_email, size)


@mcp.tool
async def update_file(file_id: str, session_id: str, name: str | None = None, parent_id: str | None = None, starred: bool | None = None, trashed: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.update_file(file_id, name, parent_id, starred, trashed)


@mcp.tool
async def trash_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.trash_file(file_id)


@mcp.tool
async def delete_file(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.delete_file(file_id)


@mcp.tool
async def list_permissions(file_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.list_permissions(file_id)


@mcp.tool
async def create_permission(file_id: str, type: str, role: str, session_id: str, email_address: str | None = None, display_name: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.create_permission(file_id, type, role, email_address, display_name)


@mcp.tool
async def delete_permission(file_id: str, permission_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_drive_session.delete_permission(file_id, permission_id)
