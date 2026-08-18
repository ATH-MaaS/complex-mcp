from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightInstagramSession
except ImportError:
    from software.LightInstagram.session import LightInstagramSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightInstagram")

session_dict: Dict[str, LightInstagramSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightInstagramSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.instagram_session.get_session_dict(),
    }


@mcp.tool
async def search_hashtags(q: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.search_hashtags(q)


@mcp.tool
async def get_hashtag(hashtag_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_hashtag(hashtag_id)


@mcp.tool
async def get_hashtag_recent_media(hashtag_id: str, user_id: str, session_id: str, limit: int = 25):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_hashtag_recent_media(hashtag_id, user_id, limit)


@mcp.tool
async def get_media_children(media_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_media_children(media_id)


@mcp.tool
async def list_media_comments(media_id: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.list_media_comments(media_id, limit, offset)


@mcp.tool
async def get_media_insights(media_id: str, session_id: str, metric: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_media_insights(media_id, metric)


@mcp.tool
async def create_comment(media_id: str, message: str, session_id: str, parent_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.create_comment(media_id, message, parent_id)


@mcp.tool
async def delete_comment(media_id: str, comment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.delete_comment(media_id, comment_id)


@mcp.tool
async def hide_comment(media_id: str, comment_id: str, session_id: str, hide: bool = True):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.hide_comment(media_id, comment_id, hide)


@mcp.tool
async def get_media(media_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_media(media_id)


@mcp.tool
async def delete_media(media_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.delete_media(media_id)


@mcp.tool
async def get_comment_replies(comment_id: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_comment_replies(comment_id, limit, offset)


@mcp.tool
async def get_comment(comment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_comment(comment_id)


@mcp.tool
async def get_story(story_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_story(story_id)


@mcp.tool
async def get_media_container_status(container_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_media_container_status(container_id)


@mcp.tool
async def search_users(q: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.search_users(q)


@mcp.tool
async def list_user_media(user_id: str, session_id: str, media_type: str | None = None, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.list_user_media(user_id, media_type, limit, offset)


@mcp.tool
async def list_user_stories(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.list_user_stories(user_id)


@mcp.tool
async def get_user_insights(user_id: str, session_id: str, metric: str | None = None, period: str = "day"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_user_insights(user_id, metric, period)


@mcp.tool
async def list_user_mentions(user_id: str, session_id: str, limit: int = 25, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.list_user_mentions(user_id, limit, offset)


@mcp.tool
async def create_media_container(user_id: str, session_id: str, image_url: str | None = None, video_url: str | None = None, caption: str | None = None, media_type: str = "IMAGE", children: List[str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.create_media_container(user_id, image_url, video_url, caption, media_type, children)


@mcp.tool
async def publish_media_container(user_id: str, creation_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.publish_media_container(user_id, creation_id)


@mcp.tool
async def update_user(user_id: str, session_id: str, biography: str | None = None, website: str | None = None, name: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.update_user(user_id, biography, website, name)


@mcp.tool
async def get_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.instagram_session.get_user(user_id)
