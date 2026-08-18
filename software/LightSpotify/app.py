from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightSpotifySession
except ImportError:
    from software.LightSpotify.session import LightSpotifySession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightSpotify")

session_dict: Dict[str, LightSpotifySession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightSpotifySession(os_cfg=os_cfg, seed=seed)
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
        "output": session.spotify_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.get_me()


@mcp.tool
async def list_my_playlists(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.list_my_playlists()


@mcp.tool
async def get_playlist(playlist_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.get_playlist(playlist_id)


@mcp.tool
async def get_playlist_tracks(playlist_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.get_playlist_tracks(playlist_id)


@mcp.tool
async def create_playlist(user_id: str, name: str, session_id: str, description: str = "", public: bool = True, collaborative: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.create_playlist(user_id, name, description, public, collaborative)


@mcp.tool
async def add_tracks(playlist_id: str, uris: List[str], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.add_tracks(playlist_id, uris)


@mcp.tool
async def search(q: str, session_id: str, type: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.search(q, type)


@mcp.tool
async def get_player(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.get_player()


@mcp.tool
async def start_playback(session_id: str, uris: List[str] | None = None, context_uri: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.spotify_session.start_playback(uris, context_uri)
