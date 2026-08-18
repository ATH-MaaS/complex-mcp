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


def _strict_int(v) -> int:
    return int(str(v).strip())


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _opt_str(v, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _opt_csv_list(v, sep: str = "|") -> List[str]:
    if v is None or str(v).strip() == "":
        return []
    return [part for part in str(v).split(sep)]


class InstagramSession:
    """Deterministic sandbox for the Instagram Graph API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "instagram.yaml") as f:
                info = yaml.safe_load(f)

            self.media: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "caption": _opt_str(r.get("caption"), default="") or None,
                    "media_type": r["media_type"],
                    "media_url": r["media_url"],
                    "permalink": r["permalink"],
                    "thumbnail_url": _opt_str(r.get("thumbnail_url"), default="") or None,
                    "timestamp": r["timestamp"],
                    "like_count": _strict_int(r["like_count"]),
                    "comments_count": _strict_int(r["comments_count"]),
                    "is_comment_enabled": _to_bool(r["is_comment_enabled"]),
                }
                for r in info.get("media", [])
            ]
            self.comments: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "media_id": r["media_id"],
                    "user_id": r["user_id"],
                    "username": r["username"],
                    "text": r["text"],
                    "timestamp": r["timestamp"],
                    "like_count": _strict_int(r["like_count"]),
                    "hidden": _to_bool(r["hidden"]),
                    "parent_id": _opt_str(r.get("parent_id"), default="") or None,
                }
                for r in info.get("comments", [])
            ]
            self.stories: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "media_type": r["media_type"],
                    "media_url": r["media_url"],
                    "timestamp": r["timestamp"],
                    "expiring_at": r["expiring_at"],
                    "caption": _opt_str(r.get("caption"), default="") or None,
                    "link": _opt_str(r.get("link"), default="") or None,
                    "poll_question": _opt_str(r.get("poll_question"), default="") or None,
                    "poll_options": (_opt_csv_list(r.get("poll_options"), sep="|") or None),
                }
                for r in info.get("stories", [])
            ]
            self.media_insights: List[Dict[str, Any]] = [
                {
                    "media_id": r["media_id"],
                    "impressions": _strict_int(r["impressions"]),
                    "reach": _strict_int(r["reach"]),
                    "engagement": _strict_int(r["engagement"]),
                    "saves": _strict_int(r["saves"]),
                    "shares": _strict_int(r["shares"]),
                    "profile_visits": _strict_int(r["profile_visits"]),
                    "follows": _strict_int(r["follows"]),
                }
                for r in info.get("media_insights", [])
            ]
            self.carousel_children: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "media_id": r["media_id"],
                    "media_type": r["media_type"],
                    "media_url": r["media_url"],
                    "timestamp": r["timestamp"],
                }
                for r in info.get("carousel_children", [])
            ]
            self.hashtags: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "media_count": _strict_int(r["media_count"]),
                }
                for r in info.get("hashtags", [])
            ]
            self.mentions: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "media_id": r["media_id"],
                    "mentioned_by_user_id": r["mentioned_by_user_id"],
                    "mentioned_by_username": r["mentioned_by_username"],
                    "media_url": r["media_url"],
                    "timestamp": r["timestamp"],
                    "caption": _opt_str(r.get("caption"), default="") or None,
                }
                for r in info.get("mentions", [])
            ]
            self.users: List[Dict[str, Any]] = list(info.get("user", []))

            # In-memory content-publishing containers (mock).
            self.media_containers: List[Dict[str, Any]] = []

            # Auto-incrementing ids matching the source id shapes.
            self._next_comment_id = 17800001051
            self._next_media_id = 17900001029
            self._next_container_id = 17920001001
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightInstagram')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {
            "media": self.media,
            "comments": self.comments,
            "stories": self.stories,
            "users": self.users,
        }

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _users_dict(self) -> Dict[str, Any]:
        return {u["id"]: u for u in self.users}

    def _primary_user(self) -> Dict[str, Any]:
        return self.users[0] if self.users else {}

    def _err(self, message: str) -> Dict[str, Any]:
        return {"status": "failed", "output": message}

    # --- User / Account ----------------------------------------------------
    def get_user(self, user_id: str) -> Dict[str, Any]:
        user = self._users_dict().get(user_id)
        if not user:
            return self._err(f"User {user_id} not found")
        return {"status": "ok", "output": user}

    def update_user(self, user_id: str, biography: str | None = None,
                    website: str | None = None, name: str | None = None) -> Dict[str, Any]:
        data = {k: v for k, v in {"biography": biography, "website": website, "name": name}.items() if v is not None}
        if not data:
            return self._err("No updatable fields provided")
        user = self._users_dict().get(user_id)
        if not user:
            return self._err(f"User {user_id} not found")
        updatable = {"biography", "website", "name"}
        for k, v in data.items():
            if k in updatable:
                user[k] = v
        return {"status": "ok", "output": user}

    def search_users(self, q: str) -> Dict[str, Any]:
        if not q or not q.strip():
            return self._err("Query parameter 'q' is required")
        q_lower = q.strip().lower()
        results = []
        for u in self.users:
            if q_lower in u.get("username", "").lower() or q_lower in u.get("name", "").lower():
                results.append(dict(u))
        return {"status": "ok", "output": results}

    # --- Media -------------------------------------------------------------
    def list_user_media(self, user_id: str, media_type: str | None = None,
                        limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        results = [m for m in self.media if m["user_id"] == user_id]
        if media_type:
            results = [m for m in results if m["media_type"] == media_type.upper()]
        results = sorted(results, key=lambda x: x["timestamp"], reverse=True)

        total = len(results)
        page_results = results[offset: offset + limit]

        paging: Dict[str, Any] = {}
        if offset + limit < total:
            paging["cursors"] = {"after": page_results[-1]["id"] if page_results else None}
            paging["next"] = f"https://graph.instagram.mock/{user_id}/media?limit={limit}&after={paging['cursors']['after']}"
        if offset > 0:
            paging.setdefault("cursors", {})["before"] = page_results[0]["id"] if page_results else None

        return {"status": "ok", "output": {"data": page_results, "paging": paging}}

    def get_media(self, media_id: str) -> Dict[str, Any]:
        for m in self.media:
            if m["id"] == media_id:
                return {"status": "ok", "output": m}
        return self._err(f"Media {media_id} not found")

    def delete_media(self, media_id: str) -> Dict[str, Any]:
        for i, m in enumerate(self.media):
            if m["id"] == media_id:
                del self.media[i]
                return {"status": "ok", "output": {"success": True}}
        return self._err(f"Media {media_id} not found")

    # --- Carousel Children -------------------------------------------------
    def get_media_children(self, media_id: str) -> Dict[str, Any]:
        media = None
        for m in self.media:
            if m["id"] == media_id:
                media = m
                break
        if not media:
            return self._err(f"Media {media_id} not found")
        if media["media_type"] != "CAROUSEL_ALBUM":
            return self._err(f"Media {media_id} is not a carousel album")

        children = [c for c in self.carousel_children if c["media_id"] == media_id]
        return {"status": "ok", "output": {"data": children}}

    # --- Comments ----------------------------------------------------------
    def list_media_comments(self, media_id: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if not any(m["id"] == media_id for m in self.media):
            return self._err(f"Media {media_id} not found")

        results = [c for c in self.comments if c["media_id"] == media_id and not c["hidden"]]
        results = sorted(results, key=lambda x: x["timestamp"], reverse=True)

        total = len(results)
        page_results = results[offset: offset + limit]

        paging: Dict[str, Any] = {}
        if offset + limit < total:
            paging["cursors"] = {"after": page_results[-1]["id"] if page_results else None}
        if offset > 0:
            paging.setdefault("cursors", {})["before"] = page_results[0]["id"] if page_results else None

        return {"status": "ok", "output": {"data": page_results, "paging": paging}}

    def get_comment(self, comment_id: str) -> Dict[str, Any]:
        for c in self.comments:
            if c["id"] == comment_id:
                return {"status": "ok", "output": c}
        return self._err(f"Comment {comment_id} not found")

    def get_comment_replies(self, comment_id: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == comment_id for c in self.comments):
            return self._err(f"Comment {comment_id} not found")

        results = [c for c in self.comments if c["parent_id"] == comment_id]
        results = sorted(results, key=lambda x: x["timestamp"])

        total = len(results)
        page_results = results[offset: offset + limit]

        paging: Dict[str, Any] = {}
        if offset + limit < total:
            paging["cursors"] = {"after": page_results[-1]["id"] if page_results else None}

        return {"status": "ok", "output": {"data": page_results, "paging": paging}}

    def create_comment(self, media_id: str, message: str, parent_id: str | None = None) -> Dict[str, Any]:
        if not any(m["id"] == media_id for m in self.media):
            return self._err(f"Media {media_id} not found")

        if parent_id and not any(c["id"] == parent_id for c in self.comments):
            return self._err(f"Parent comment {parent_id} not found")

        comment = {
            "id": str(self._next_comment_id),
            "media_id": media_id,
            "user_id": self._primary_user()["id"],
            "username": self._primary_user()["username"],
            "text": message,
            "timestamp": self._now(),
            "like_count": 0,
            "hidden": False,
            "parent_id": parent_id,
        }
        self.comments.append(comment)
        self._next_comment_id += 1

        for m in self.media:
            if m["id"] == media_id:
                m["comments_count"] = m["comments_count"] + 1
                break

        return {"status": "ok", "output": comment}

    def delete_comment(self, media_id: str, comment_id: str) -> Dict[str, Any]:
        if not any(m["id"] == media_id for m in self.media):
            return self._err(f"Media {media_id} not found")

        for i, c in enumerate(self.comments):
            if c["id"] == comment_id and c["media_id"] == media_id:
                del self.comments[i]
                for m in self.media:
                    if m["id"] == media_id:
                        m["comments_count"] = m["comments_count"] - 1
                        break
                return {"status": "ok", "output": {"success": True}}
        return self._err(f"Comment {comment_id} not found")

    def hide_comment(self, media_id: str, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        if not any(m["id"] == media_id for m in self.media):
            return self._err(f"Media {media_id} not found")

        for c in self.comments:
            if c["id"] == comment_id and c["media_id"] == media_id:
                c["hidden"] = hide
                return {"status": "ok", "output": {"success": True}}
        return self._err(f"Comment {comment_id} not found")

    # --- Stories -----------------------------------------------------------
    def list_user_stories(self, user_id: str) -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        results = [s for s in self.stories if s["user_id"] == user_id]
        results = sorted(results, key=lambda x: x["timestamp"], reverse=True)

        return {"status": "ok", "output": {"data": results}}

    def get_story(self, story_id: str) -> Dict[str, Any]:
        for s in self.stories:
            if s["id"] == story_id:
                return {"status": "ok", "output": s}
        return self._err(f"Story {story_id} not found")

    # --- Insights / Analytics ----------------------------------------------
    def get_user_insights(self, user_id: str, metric: str | None = None, period: str = "day") -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        total_impressions = sum(i["impressions"] for i in self.media_insights)
        total_reach = sum(i["reach"] for i in self.media_insights)
        total_engagement = sum(i["engagement"] for i in self.media_insights)
        total_profile_visits = sum(i["profile_visits"] for i in self.media_insights)
        total_follows = sum(i["follows"] for i in self.media_insights)

        all_metrics = [
            {
                "name": "impressions",
                "period": period,
                "values": [{"value": total_impressions, "end_time": self._now()}],
                "title": "Impressions",
                "description": "Total number of times your posts have been seen",
            },
            {
                "name": "reach",
                "period": period,
                "values": [{"value": total_reach, "end_time": self._now()}],
                "title": "Reach",
                "description": "Total number of unique accounts that have seen your posts",
            },
            {
                "name": "follower_count",
                "period": period,
                "values": [{"value": self._primary_user()["followers_count"], "end_time": self._now()}],
                "title": "Follower Count",
                "description": "Total number of followers",
            },
            {
                "name": "profile_views",
                "period": period,
                "values": [{"value": total_profile_visits, "end_time": self._now()}],
                "title": "Profile Views",
                "description": "Total number of profile views",
            },
            {
                "name": "website_clicks",
                "period": period,
                "values": [{"value": int(total_profile_visits * 0.12), "end_time": self._now()}],
                "title": "Website Clicks",
                "description": "Total number of taps on the website link",
            },
        ]

        if metric:
            metrics = metric.split(",")
            all_metrics = [m for m in all_metrics if m["name"] in metrics]
            if not all_metrics:
                return self._err(f"Invalid metric: {metric}")

        return {"status": "ok", "output": {"data": all_metrics}}

    def get_media_insights(self, media_id: str, metric: str | None = None) -> Dict[str, Any]:
        if not any(m["id"] == media_id for m in self.media):
            return self._err(f"Media {media_id} not found")

        insight = None
        for i in self.media_insights:
            if i["media_id"] == media_id:
                insight = i
                break

        if not insight:
            return self._err(f"No insights available for media {media_id}")

        all_metrics = [
            {"name": "impressions", "period": "lifetime", "values": [{"value": insight["impressions"]}], "title": "Impressions"},
            {"name": "reach", "period": "lifetime", "values": [{"value": insight["reach"]}], "title": "Reach"},
            {"name": "engagement", "period": "lifetime", "values": [{"value": insight["engagement"]}], "title": "Engagement"},
            {"name": "saved", "period": "lifetime", "values": [{"value": insight["saves"]}], "title": "Saves"},
            {"name": "shares", "period": "lifetime", "values": [{"value": insight["shares"]}], "title": "Shares"},
            {"name": "profile_visits", "period": "lifetime", "values": [{"value": insight["profile_visits"]}], "title": "Profile Visits"},
            {"name": "follows", "period": "lifetime", "values": [{"value": insight["follows"]}], "title": "Follows"},
        ]

        if metric:
            metrics = metric.split(",")
            all_metrics = [m for m in all_metrics if m["name"] in metrics]
            if not all_metrics:
                return self._err(f"Invalid metric: {metric}")

        return {"status": "ok", "output": {"data": all_metrics}}

    # --- Hashtags ----------------------------------------------------------
    def search_hashtags(self, q: str) -> Dict[str, Any]:
        if not q:
            return self._err("Query parameter is required")

        q_lower = q.lower().replace("#", "")
        results = [h for h in self.hashtags if q_lower in h["name"].lower()]

        return {"status": "ok", "output": {"data": results}}

    def get_hashtag(self, hashtag_id: str) -> Dict[str, Any]:
        for h in self.hashtags:
            if h["id"] == hashtag_id:
                return {"status": "ok", "output": h}
        return self._err(f"Hashtag {hashtag_id} not found")

    def get_hashtag_recent_media(self, hashtag_id: str, user_id: str, limit: int = 25) -> Dict[str, Any]:
        hashtag = None
        for h in self.hashtags:
            if h["id"] == hashtag_id:
                hashtag = h
                break
        if not hashtag:
            return self._err(f"Hashtag {hashtag_id} not found")

        tag_name = hashtag["name"]
        results = []
        for m in self.media:
            if m["user_id"] == user_id and m["caption"]:
                if f"#{tag_name}" in m["caption"].lower():
                    results.append(m)

        results = sorted(results, key=lambda x: x["timestamp"], reverse=True)[:limit]

        return {"status": "ok", "output": {"data": results}}

    # --- Mentions ----------------------------------------------------------
    def list_user_mentions(self, user_id: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        results = sorted(self.mentions, key=lambda x: x["timestamp"], reverse=True)

        total = len(results)
        page_results = results[offset: offset + limit]

        paging: Dict[str, Any] = {}
        if offset + limit < total:
            paging["cursors"] = {"after": page_results[-1]["id"] if page_results else None}

        return {"status": "ok", "output": {"data": page_results, "paging": paging}}

    # --- Content Publishing (Mock) -----------------------------------------
    def create_media_container(self, user_id: str, image_url: str | None = None,
                               video_url: str | None = None, caption: str | None = None,
                               media_type: str = "IMAGE", children: List[str] | None = None) -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        if media_type == "CAROUSEL_ALBUM" and not children:
            return self._err("Carousel albums require children containers")

        container = {
            "id": str(self._next_container_id),
            "status": "FINISHED",
            "media_type": media_type,
            "image_url": image_url,
            "video_url": video_url,
            "caption": caption,
            "children": children,
            "created_at": self._now(),
        }
        self.media_containers.append(container)
        self._next_container_id += 1

        return {"status": "ok", "output": {"id": container["id"]}}

    def publish_media_container(self, user_id: str, creation_id: str) -> Dict[str, Any]:
        if user_id not in self._users_dict():
            return self._err(f"User {user_id} not found")

        container = None
        for c in self.media_containers:
            if c["id"] == creation_id:
                container = c
                break
        if not container:
            return self._err(f"Container {creation_id} not found")

        if container["status"] != "FINISHED":
            return self._err(f"Container {creation_id} is not ready for publishing")

        now = self._now()
        media = {
            "id": str(self._next_media_id),
            "user_id": user_id,
            "caption": container["caption"],
            "media_type": container["media_type"],
            "media_url": container["image_url"] or container["video_url"] or "",
            "permalink": f"https://instagram.mock/p/new_{self._next_media_id}/",
            "thumbnail_url": None,
            "timestamp": now,
            "like_count": 0,
            "comments_count": 0,
            "is_comment_enabled": True,
        }
        self.media.append(media)
        self._next_media_id += 1

        primary = self._primary_user()
        for u in self.users:
            if u["id"] == primary["id"]:
                u["media_count"] = u["media_count"] + 1
                break

        self.media_containers.remove(container)

        return {"status": "ok", "output": {"id": media["id"]}}

    def get_media_container_status(self, container_id: str) -> Dict[str, Any]:
        for c in self.media_containers:
            if c["id"] == container_id:
                return {"status": "ok", "output": {
                    "id": c["id"],
                    "status": c["status"],
                    "status_code": "PUBLISHED" if c["status"] == "FINISHED" else "IN_PROGRESS",
                }}
        return self._err(f"Container {container_id} not found")


if __name__ == "__main__":
    s = InstagramSession(seed=12)
    print(s.search_hashtags("coffee"))
    print(s.get_user("17841400123456789"))
