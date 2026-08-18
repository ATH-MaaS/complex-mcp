from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightNASASession
except ImportError:
    from software.LightNASA.session import LightNASASession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightNASA")

session_dict: Dict[str, LightNASASession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightNASASession(os_cfg=os_cfg, seed=seed)
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
        "output": session.nasa_session.get_session_dict(),
    }


@mcp.tool
async def get_apod(session_id: str, date: str | None = None, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_apod(date, start_date, end_date)


@mcp.tool
async def get_rover_photos(rover: str, session_id: str, sol: int | None = None, camera: str | None = None, earth_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_rover_photos(rover, sol, camera, earth_date)


@mcp.tool
async def get_rover_manifest(rover: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_rover_manifest(rover)


@mcp.tool
async def get_neo_feed(session_id: str, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_neo_feed(start_date, end_date)


@mcp.tool
async def get_neo(neo_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_neo(neo_id)


@mcp.tool
async def get_epic_natural(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.nasa_session.get_epic_natural()
