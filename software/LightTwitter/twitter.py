import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    return int(str(v).strip())


class TwitterSession:
    """Deterministic sandbox for the Twitter/X API v2 mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "twitter.yaml") as f:
                info = yaml.safe_load(f)

            _metric_cols = ("followers_count", "following_count", "tweet_count")
            self.users: List[Dict[str, Any]] = []
            for r in info.get("users", []):
                base = {k: v for k, v in r.items() if k not in _metric_cols}
                self.users.append({
                    **base,
                    "verified": _to_bool(r["verified"]),
                    "protected": _to_bool(r["protected"]),
                    "public_metrics": {
                        "followers_count": _to_int(r["followers_count"]),
                        "following_count": _to_int(r["following_count"]),
                        "tweet_count": _to_int(r["tweet_count"]),
                    },
                })

            self.tweets: List[Dict[str, Any]] = [
                {
                    "id": t["id"],
                    "author_id": t["author_id"],
                    "text": t["text"],
                    "created_at": t["created_at"],
                    "lang": t["lang"],
                    "reply_to_tweet_id": (str(t.get("reply_to_tweet_id") or "") or None),
                    "public_metrics": {
                        "like_count": _to_int(t["like_count"]),
                        "retweet_count": _to_int(t["retweet_count"]),
                        "reply_count": _to_int(t["reply_count"]),
                        "quote_count": _to_int(t["quote_count"]),
                    },
                }
                for t in info.get("tweets", [])
            ]
            self.follows: List[Dict[str, Any]] = list(info.get("follows", []))
            self.likes: List[Dict[str, Any]] = list(info.get("likes", []))
            self.retweets: List[Dict[str, Any]] = list(info.get("retweets", []))

            self._me_id = self.users[0]["id"] if self.users else None
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTwitter')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"tweets": self.tweets, "likes": self.likes, "retweets": self.retweets}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=18))

    def _new_id(self) -> str:
        return self.uuid()

    def _public_user(self, u):
        return dict(u)

    # --- Users -------------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == self._me_id:
                return {"status": "ok", "output": self._public_user(u)}
        return {"status": "ok", "output": self._public_user(self.users[0])}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == user_id:
                return {"status": "ok", "output": self._public_user(u)}
        return {"status": "failed", "output": f"User {user_id} not found"}

    def get_user_by_username(self, username: str) -> Dict[str, Any]:
        for u in self.users:
            if u["username"].lower() == username.lower():
                return {"status": "ok", "output": self._public_user(u)}
        return {"status": "failed", "output": f"User @{username} not found"}

    def get_user_tweets(self, user_id: str, max_results: int = 10) -> Dict[str, Any]:
        if not any(u["id"] == user_id for u in self.users):
            return {"status": "failed", "output": f"User {user_id} not found"}
        tweets = [t for t in self.tweets if t["author_id"] == user_id]
        tweets.sort(key=lambda t: t["created_at"], reverse=True)
        sliced = tweets[:max_results]
        return {"status": "ok", "output": {"data": sliced, "meta": {"result_count": len(sliced)}}}

    def get_followers(self, user_id: str, max_results: int = 100) -> Dict[str, Any]:
        if not any(u["id"] == user_id for u in self.users):
            return {"status": "failed", "output": f"User {user_id} not found"}
        follower_ids = [f["follower_id"] for f in self.follows if f["following_id"] == user_id]
        followers = [self._public_user(u) for u in self.users if u["id"] in follower_ids]
        sliced = followers[:max_results]
        return {"status": "ok", "output": {"data": sliced, "meta": {"result_count": len(sliced)}}}

    def get_following(self, user_id: str, max_results: int = 100) -> Dict[str, Any]:
        if not any(u["id"] == user_id for u in self.users):
            return {"status": "failed", "output": f"User {user_id} not found"}
        following_ids = [f["following_id"] for f in self.follows if f["follower_id"] == user_id]
        following = [self._public_user(u) for u in self.users if u["id"] in following_ids]
        sliced = following[:max_results]
        return {"status": "ok", "output": {"data": sliced, "meta": {"result_count": len(sliced)}}}

    # --- Tweets ------------------------------------------------------------
    def list_tweets(self, ids: List[str] | None = None, max_results: int = 10) -> Dict[str, Any]:
        if ids:
            wanted = {i.strip() for i in ids}
            tweets = [t for t in self.tweets if t["id"] in wanted]
        else:
            tweets = sorted(self.tweets, key=lambda t: t["created_at"], reverse=True)[:max_results]
        return {"status": "ok", "output": {"data": tweets, "meta": {"result_count": len(tweets)}}}

    def get_tweet(self, tweet_id: str) -> Dict[str, Any]:
        for t in self.tweets:
            if t["id"] == tweet_id:
                return {"status": "ok", "output": t}
        return {"status": "failed", "output": f"Tweet {tweet_id} not found"}

    def create_tweet(self, text: str, author_id: str | None = None,
                     reply_to_tweet_id: str | None = None) -> Dict[str, Any]:
        author_id = author_id or self._me_id
        if not any(u["id"] == author_id for u in self.users):
            return {"status": "failed", "output": f"User {author_id} not found"}
        if reply_to_tweet_id and not any(t["id"] == reply_to_tweet_id for t in self.tweets):
            return {"status": "failed", "output": f"Tweet {reply_to_tweet_id} not found"}
        tweet = {
            "id": self._new_id(),
            "author_id": author_id,
            "text": text,
            "created_at": self._now(),
            "lang": "en",
            "reply_to_tweet_id": reply_to_tweet_id,
            "public_metrics": {
                "like_count": 0,
                "retweet_count": 0,
                "reply_count": 0,
                "quote_count": 0,
            },
        }
        self.tweets.append(tweet)
        if reply_to_tweet_id:
            for t in self.tweets:
                if t["id"] == reply_to_tweet_id:
                    t["public_metrics"]["reply_count"] += 1
        return {"status": "ok", "output": tweet}

    def delete_tweet(self, tweet_id: str) -> Dict[str, Any]:
        for i, t in enumerate(self.tweets):
            if t["id"] == tweet_id:
                self.tweets.pop(i)
                return {"status": "ok", "output": {"deleted": True}}
        return {"status": "failed", "output": f"Tweet {tweet_id} not found"}

    def search_recent(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        q = (query or "").lower()
        matches = [t for t in self.tweets if q in t["text"].lower()]
        matches.sort(key=lambda t: t["created_at"], reverse=True)
        sliced = matches[:max_results]
        return {"status": "ok", "output": {"data": sliced, "meta": {"result_count": len(sliced), "query": query}}}

    # --- Likes / Retweets --------------------------------------------------
    def like_tweet(self, user_id: str, tweet_id: str) -> Dict[str, Any]:
        if not any(u["id"] == user_id for u in self.users):
            return {"status": "failed", "output": f"User {user_id} not found"}
        target = next((t for t in self.tweets if t["id"] == tweet_id), None)
        if not target:
            return {"status": "failed", "output": f"Tweet {tweet_id} not found"}
        if not any(l["user_id"] == user_id and l["tweet_id"] == tweet_id for l in self.likes):
            self.likes.append({"user_id": user_id, "tweet_id": tweet_id})
            target["public_metrics"]["like_count"] += 1
        return {"status": "ok", "output": {"liked": True}}

    def retweet(self, user_id: str, tweet_id: str) -> Dict[str, Any]:
        if not any(u["id"] == user_id for u in self.users):
            return {"status": "failed", "output": f"User {user_id} not found"}
        target = next((t for t in self.tweets if t["id"] == tweet_id), None)
        if not target:
            return {"status": "failed", "output": f"Tweet {tweet_id} not found"}
        if not any(r["user_id"] == user_id and r["tweet_id"] == tweet_id for r in self.retweets):
            self.retweets.append({"user_id": user_id, "tweet_id": tweet_id})
            target["public_metrics"]["retweet_count"] += 1
        return {"status": "ok", "output": {"retweeted": True}}


if __name__ == "__main__":
    s = TwitterSession(seed=12)
    print(s.get_me())
    print(s.list_tweets())
