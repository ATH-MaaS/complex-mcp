from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightTwitterSession
except ImportError:
    from software.LightTwitter.session import LightTwitterSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightTwitter")

session_dict: Dict[str, LightTwitterSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightTwitterSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.twitter_session.get_session_dict(),
    }


@mcp.tool
async def get_me(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_me()


@mcp.tool
async def get_user(user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_user(user_id)


@mcp.tool
async def get_user_by_username(username: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_user_by_username(username)


@mcp.tool
async def get_user_tweets(user_id: str, session_id: str, max_results: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_user_tweets(user_id, max_results)


@mcp.tool
async def get_followers(user_id: str, session_id: str, max_results: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_followers(user_id, max_results)


@mcp.tool
async def get_following(user_id: str, session_id: str, max_results: int = 100):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_following(user_id, max_results)


@mcp.tool
async def list_tweets(session_id: str, ids: List[str] | None = None, max_results: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.list_tweets(ids, max_results)


@mcp.tool
async def get_tweet(tweet_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.get_tweet(tweet_id)


@mcp.tool
async def create_tweet(text: str, session_id: str, author_id: str | None = None, reply_to_tweet_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.create_tweet(text, author_id, reply_to_tweet_id)


@mcp.tool
async def delete_tweet(tweet_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.delete_tweet(tweet_id)


@mcp.tool
async def search_recent(query: str, session_id: str, max_results: int = 10):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.search_recent(query, max_results)


@mcp.tool
async def like_tweet(user_id: str, tweet_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.like_tweet(user_id, tweet_id)


@mcp.tool
async def retweet(user_id: str, tweet_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.twitter_session.retweet(user_id, tweet_id)
