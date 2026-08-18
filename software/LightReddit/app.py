from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightRedditSession
except ImportError:
    from software.LightReddit.session import LightRedditSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightReddit")

session_dict: Dict[str, LightRedditSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightRedditSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.reddit_session.get_session_dict(),
    }


@mcp.tool
async def subreddit_about(subreddit: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.subreddit_about(subreddit)


@mcp.tool
async def subreddit_hot(subreddit: str, session_id: str, limit: int = 25):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.subreddit_hot(subreddit, limit)


@mcp.tool
async def subreddit_new(subreddit: str, session_id: str, limit: int = 25):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.subreddit_new(subreddit, limit)


@mcp.tool
async def post_comments(post_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.post_comments(post_id)


@mcp.tool
async def submit(sr: str, title: str, session_id: str, kind: str = "self", url: str | None = None, text: str | None = None, author: str | None = "devkat"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.submit(sr, title, kind, url, text, author)


@mcp.tool
async def vote(id: str, dir: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.vote(id, dir)


@mcp.tool
async def user_about(username: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.reddit_session.user_about(username)
