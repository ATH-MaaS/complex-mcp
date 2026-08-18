from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightWordPressSession
except ImportError:
    from software.LightWordPress.session import LightWordPressSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightWordPress")

session_dict: Dict[str, LightWordPressSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightWordPressSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.wordpress_session.get_session_dict(),
    }


@mcp.tool
async def list_posts(session_id: str, status: str | None = None, author: int | None = None, search: str | None = None, categories: int | None = None, per_page: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_posts(status, author, search, categories, per_page)


@mcp.tool
async def create_post(title: str, session_id: str, content: str = "", status: str = "draft", author: int = 1, excerpt: str = "", categories: List[int] | None = None, tags: List[int] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.create_post(title, content, status, author, excerpt, categories, tags)


@mcp.tool
async def get_post(post_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.get_post(post_id)


@mcp.tool
async def update_post(post_id: int, session_id: str, title: str | None = None, content: str | None = None, status: str | None = None, excerpt: str | None = None, categories: List[int] | None = None, tags: List[int] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.update_post(post_id, title, content, status, excerpt, categories, tags)


@mcp.tool
async def delete_post(post_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.delete_post(post_id)


@mcp.tool
async def list_pages(session_id: str, status: str = "publish", per_page: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_pages(status, per_page)


@mcp.tool
async def list_categories(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_categories()


@mcp.tool
async def list_tags(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_tags()


@mcp.tool
async def list_comments(session_id: str, post: int | None = None, status: str = "approved"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_comments(post, status)


@mcp.tool
async def create_comment(post: int, author_name: str, author_email: str, content: str, session_id: str, parent: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.create_comment(post, author_name, author_email, content, parent)


@mcp.tool
async def list_media(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_media()


@mcp.tool
async def list_users(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.wordpress_session.list_users()
