from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightYouTubeSession
except ImportError:
    from software.LightYouTube.session import LightYouTubeSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightYouTube")

session_dict: Dict[str, LightYouTubeSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightYouTubeSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.youtube_session.get_session_dict(),
    }


@mcp.tool
async def get_channel(session_id: str, channel_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.get_channel(channel_id)


@mcp.tool
async def list_videos(session_id: str, video_id: str | None = None, channel_id: str | None = None, max_results: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_videos(video_id, channel_id, max_results, offset)


@mcp.tool
async def update_video(video_id: str, session_id: str, snippet: Dict[str, Any] | None = None, status: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.update_video(video_id, snippet, status)


@mcp.tool
async def delete_video(video_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.delete_video(video_id)


@mcp.tool
async def list_playlists(session_id: str, playlist_id: str | None = None, channel_id: str | None = None, max_results: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_playlists(playlist_id, channel_id, max_results, offset)


@mcp.tool
async def create_playlist(snippet: Dict[str, Any], session_id: str, status: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.create_playlist(snippet, status)


@mcp.tool
async def update_playlist(playlist_id: str, session_id: str, snippet: Dict[str, Any] | None = None, status: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.update_playlist(playlist_id, snippet, status)


@mcp.tool
async def delete_playlist(playlist_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.delete_playlist(playlist_id)


@mcp.tool
async def list_playlist_items(playlist_id: str, session_id: str, max_results: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_playlist_items(playlist_id, max_results, offset)


@mcp.tool
async def insert_playlist_item(snippet: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.insert_playlist_item(snippet)


@mcp.tool
async def update_playlist_item(playlist_item_id: str, session_id: str, snippet: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.update_playlist_item(playlist_item_id, snippet)


@mcp.tool
async def delete_playlist_item(playlist_item_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.delete_playlist_item(playlist_item_id)


@mcp.tool
async def list_comment_threads(session_id: str, video_id: str | None = None, channel_id: str | None = None, max_results: int = 20, offset: int = 0, moderation_status: str = "published"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_comment_threads(video_id, channel_id, max_results, offset, moderation_status)


@mcp.tool
async def insert_comment_thread(snippet: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.insert_comment_thread(snippet)


@mcp.tool
async def list_comments(parent_id: str, session_id: str, max_results: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_comments(parent_id, max_results, offset)


@mcp.tool
async def insert_comment(snippet: Dict[str, Any], session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.insert_comment(snippet)


@mcp.tool
async def update_comment(comment_id: str, session_id: str, snippet: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.update_comment(comment_id, snippet)


@mcp.tool
async def delete_comment(comment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.delete_comment(comment_id)


@mcp.tool
async def set_moderation_status(id: str, moderation_status: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.set_moderation_status(id, moderation_status)


@mcp.tool
async def search_videos(session_id: str, channel_id: str | None = None, q: str | None = None, order: str = "relevance", max_results: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.search_videos(channel_id, q, order, max_results, offset)


@mcp.tool
async def list_video_categories(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_video_categories()


@mcp.tool
async def list_captions(video_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_captions(video_id)


@mcp.tool
async def list_channel_sections(channel_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.list_channel_sections(channel_id)


@mcp.tool
async def get_channel_analytics(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.get_channel_analytics()


@mcp.tool
async def get_video_analytics(video_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.youtube_session.get_video_analytics(video_id)
