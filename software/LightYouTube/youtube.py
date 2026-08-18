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


def _to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _opt_str(v, default=""):
    s = default if v is None else str(v)
    return s


def _opt_csv_list(v, sep=","):
    if not v:
        return []
    return [x for x in str(v).split(sep) if x]


class YoutubeSession:
    """Deterministic sandbox for the YouTube Data API v3 mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "youtube.yaml") as f:
                info = yaml.safe_load(f)

            self.channel: Dict[str, Any] = dict(info.get("channel", {}))
            self._CHANNEL_ID = self.channel["id"]
            self._CHANNEL_TITLE = self.channel["snippet"]["title"]

            self.videos: List[Dict[str, Any]] = self._coerce_videos(info.get("videos", []))
            self.playlists: List[Dict[str, Any]] = self._coerce_playlists(info.get("playlists", []))
            self.playlist_items: List[Dict[str, Any]] = self._coerce_playlist_items(info.get("playlist_items", []))
            self.comments: List[Dict[str, Any]] = self._coerce_comments(info.get("comments", []))
            self.captions: List[Dict[str, Any]] = self._coerce_captions(info.get("captions", []))
            self.video_categories: List[Dict[str, Any]] = list(info.get("video_categories", []))
            self.channel_sections: List[Dict[str, Any]] = list(info.get("channel_sections", []))
            self.analytics: Dict[str, Any] = dict(info.get("analytics", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightYouTube')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"videos": self.videos, "playlists": self.playlists,
                "playlist_items": self.playlist_items, "comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    # --- coercers ----------------------------------------------------------
    def _coerce_videos(self, rows):
        out = []
        for r in rows:
            thumb = r.get("thumbnailUrl") or ""
            out.append({
                "id": r["video_id"],
                "snippet": {
                    "publishedAt": r.get("publishedAt") or "",
                    "channelId": r.get("channelId") or "",
                    "title": r.get("title") or "",
                    "description": r.get("description") or "",
                    "thumbnails": {
                        "default": {"url": thumb.replace("maxresdefault", "default") if thumb else "", "width": 120, "height": 90},
                        "medium": {"url": thumb.replace("maxresdefault", "mqdefault") if thumb else "", "width": 320, "height": 180},
                        "high": {"url": thumb.replace("maxresdefault", "hqdefault") if thumb else "", "width": 480, "height": 360},
                        "maxres": {"url": thumb, "width": 1280, "height": 720},
                    },
                    "channelTitle": self._CHANNEL_TITLE,
                    "tags": [t.strip() for t in _opt_csv_list(r.get("tags"), sep=",")] if r.get("tags") else [],
                    "categoryId": r.get("categoryId") or "",
                    "liveBroadcastContent": r.get("liveBroadcastContent") or "none",
                    "defaultLanguage": r.get("defaultLanguage") or None,
                    "defaultAudioLanguage": r.get("defaultAudioLanguage") or None,
                },
                "contentDetails": {
                    "duration": r.get("duration") or "PT0S",
                    "dimension": r.get("dimension") or "2d",
                    "definition": r.get("definition") or "hd",
                    "caption": "true",
                    "licensedContent": True,
                    "projection": "rectangular",
                },
                "statistics": {
                    "viewCount": r.get("viewCount") or "0",
                    "likeCount": r.get("likeCount") or "0",
                    "dislikeCount": r.get("dislikeCount") or "0",
                    "commentCount": r.get("commentCount") or "0",
                },
                "status": {
                    "uploadStatus": "processed",
                    "privacyStatus": r.get("privacyStatus") or "public",
                    "publishAt": r.get("publishAt") or None,
                    "license": "youtube",
                    "embeddable": (r.get("embeddable") or "true").lower() == "true",
                    "publicStatsViewable": True,
                    "madeForKids": False,
                },
            })
        return out

    def _coerce_playlists(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["playlist_id"],
                "snippet": {
                    "publishedAt": r["publishedAt"],
                    "channelId": r["channelId"],
                    "title": r["title"],
                    "description": r["description"],
                    "thumbnails": {
                        "default": {"url": f"https://i.ytimg.com/vi/playlist_{r['playlist_id']}/default.jpg", "width": 120, "height": 90},
                        "medium": {"url": f"https://i.ytimg.com/vi/playlist_{r['playlist_id']}/mqdefault.jpg", "width": 320, "height": 180},
                        "high": {"url": f"https://i.ytimg.com/vi/playlist_{r['playlist_id']}/hqdefault.jpg", "width": 480, "height": 360},
                    },
                    "channelTitle": self._CHANNEL_TITLE,
                },
                "status": {"privacyStatus": r["privacyStatus"]},
                "contentDetails": {"itemCount": _to_int(r.get("itemCount"))},
            })
        return out

    def _coerce_playlist_items(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["playlist_item_id"],
                "snippet": {
                    "publishedAt": r["publishedAt"],
                    "channelId": r["channelId"],
                    "title": r["title"],
                    "playlistId": r["playlistId"],
                    "position": _to_int(r.get("position")),
                    "resourceId": {"kind": "youtube#video", "videoId": r["videoId"]},
                    "thumbnails": {
                        "default": {"url": f"https://i.ytimg.com/vi/{r['videoId']}/default.jpg", "width": 120, "height": 90},
                        "medium": {"url": f"https://i.ytimg.com/vi/{r['videoId']}/mqdefault.jpg", "width": 320, "height": 180},
                        "high": {"url": f"https://i.ytimg.com/vi/{r['videoId']}/hqdefault.jpg", "width": 480, "height": 360},
                    },
                    "channelTitle": self._CHANNEL_TITLE,
                },
                "contentDetails": {
                    "videoId": r["videoId"],
                    "videoPublishedAt": r["publishedAt"],
                },
            })
        return out

    def _coerce_comments(self, rows):
        out = []
        for r in rows:
            parent = _opt_str(r.get("parentId"), "") or None
            out.append({
                "id": r["comment_id"],
                "videoId": r["videoId"],
                "channelId": _opt_str(r.get("channelId"), "") or None,
                "parentId": parent,
                "snippet": {
                    "authorDisplayName": r["authorDisplayName"],
                    "authorChannelId": {"value": r["authorChannelId"]},
                    "textDisplay": r["textDisplay"],
                    "textOriginal": r["textDisplay"],
                    "likeCount": _to_int(r.get("likeCount")),
                    "publishedAt": r["publishedAt"],
                    "updatedAt": r["updatedAt"],
                    "videoId": r["videoId"],
                    "parentId": parent,
                },
                "moderationStatus": r["moderationStatus"],
            })
        return out

    def _coerce_captions(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["caption_id"],
                "snippet": {
                    "videoId": r["videoId"],
                    "lastUpdated": r["lastUpdated"],
                    "trackKind": r["trackKind"],
                    "language": r["language"],
                    "name": r["name"],
                    "isDraft": str(r["isDraft"]).lower() == "true",
                },
            })
        return out

    # --- table helpers -----------------------------------------------------
    def _video_get(self, vid):
        return next((v for v in self.videos if v["id"] == vid), None)

    def _playlist_get(self, pid):
        return next((p for p in self.playlists if p["id"] == pid), None)

    def _playlist_item_get(self, iid):
        return next((pi for pi in self.playlist_items if pi["id"] == iid), None)

    def _comment_get(self, cid):
        return next((c for c in self.comments if c["id"] == cid), None)

    def _next_id_counter(self, rows, fallback_start):
        max_n = fallback_start - 1
        for r in rows:
            try:
                n = int(str(r["id"]).split("_")[-1])
                if n > max_n:
                    max_n = n
            except (ValueError, IndexError):
                continue
        return max_n + 1

    # --- Channels ----------------------------------------------------------
    def get_channel(self, channel_id: str | None = None) -> Dict[str, Any]:
        channel_id = channel_id or self._CHANNEL_ID
        if channel_id != self.channel["id"]:
            return {"status": "failed", "output": f"Channel {channel_id} not found"}
        return {"status": "ok", "output": {
            "kind": "youtube#channelListResponse",
            "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
            "items": [self.channel],
        }}

    # --- Videos ------------------------------------------------------------
    def list_videos(self, video_id: str | None = None, channel_id: str | None = None,
                    max_results: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.videos)
        if video_id:
            ids = [v.strip() for v in video_id.split(",")]
            results = [v for v in results if v["id"] in ids]
        elif channel_id:
            results = [v for v in results if v["snippet"]["channelId"] == channel_id]
        else:
            results = [v for v in results if v["snippet"]["channelId"] == self._CHANNEL_ID]
        total = len(results)
        page_results = results[offset: offset + max_results]
        return {"status": "ok", "output": {
            "kind": "youtube#videoListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": page_results,
        }}

    def update_video(self, video_id: str, snippet: Dict[str, Any] | None = None,
                     status: Dict[str, Any] | None = None) -> Dict[str, Any]:
        v = self._video_get(video_id)
        if not v:
            return {"status": "failed", "output": f"Video {video_id} not found"}
        snippet_updates = snippet or {}
        for k in ("title", "description", "tags", "categoryId", "defaultLanguage"):
            if k in snippet_updates:
                v["snippet"][k] = snippet_updates[k]
        status_updates = status or {}
        for k in ("privacyStatus", "embeddable", "publishAt"):
            if k in status_updates:
                v["status"][k] = status_updates[k]
        return {"status": "ok", "output": {"kind": "youtube#video", "items": [v]}}

    def delete_video(self, video_id: str) -> Dict[str, Any]:
        v = self._video_get(video_id)
        if not v:
            return {"status": "failed", "output": f"Video {video_id} not found"}
        self.videos.remove(v)
        self.playlist_items = [pi for pi in self.playlist_items
                               if pi["contentDetails"]["videoId"] != video_id]
        return {"status": "ok", "output": {"deleted": True, "videoId": video_id}}

    # --- Playlists ---------------------------------------------------------
    def list_playlists(self, playlist_id: str | None = None, channel_id: str | None = None,
                       max_results: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.playlists)
        if playlist_id:
            ids = [p.strip() for p in playlist_id.split(",")]
            results = [p for p in results if p["id"] in ids]
        elif channel_id:
            results = [p for p in results if p["snippet"]["channelId"] == channel_id]
        else:
            results = [p for p in results if p["snippet"]["channelId"] == self._CHANNEL_ID]
        total = len(results)
        page_results = results[offset: offset + max_results]
        return {"status": "ok", "output": {
            "kind": "youtube#playlistListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": page_results,
        }}

    def create_playlist(self, snippet: Dict[str, Any], status: Dict[str, Any] | None = None) -> Dict[str, Any]:
        snippet = snippet or {}
        if not snippet.get("title"):
            return {"status": "failed", "output": "Missing required field: snippet.title"}
        n = self._next_id_counter(self.playlists, 11)
        now = self._now()
        pid = f"PL_{n:03d}"
        playlist = {
            "id": pid,
            "snippet": {
                "publishedAt": now,
                "channelId": self._CHANNEL_ID,
                "title": snippet["title"],
                "description": snippet.get("description", ""),
                "thumbnails": {
                    "default": {"url": f"https://i.ytimg.com/vi/playlist_{pid}/default.jpg", "width": 120, "height": 90},
                    "medium": {"url": f"https://i.ytimg.com/vi/playlist_{pid}/mqdefault.jpg", "width": 320, "height": 180},
                    "high": {"url": f"https://i.ytimg.com/vi/playlist_{pid}/hqdefault.jpg", "width": 480, "height": 360},
                },
                "channelTitle": self._CHANNEL_TITLE,
            },
            "status": {"privacyStatus": (status or {}).get("privacyStatus", "public")},
            "contentDetails": {"itemCount": 0},
        }
        self.playlists.append(playlist)
        return {"status": "ok", "output": {"kind": "youtube#playlist", "items": [playlist]}}

    def update_playlist(self, playlist_id: str, snippet: Dict[str, Any] | None = None,
                        status: Dict[str, Any] | None = None) -> Dict[str, Any]:
        p = self._playlist_get(playlist_id)
        if not p:
            return {"status": "failed", "output": f"Playlist {playlist_id} not found"}
        snippet_updates = snippet or {}
        for k in ("title", "description"):
            if k in snippet_updates:
                p["snippet"][k] = snippet_updates[k]
        status_updates = status or {}
        if "privacyStatus" in status_updates:
            p["status"]["privacyStatus"] = status_updates["privacyStatus"]
        return {"status": "ok", "output": {"kind": "youtube#playlist", "items": [p]}}

    def delete_playlist(self, playlist_id: str) -> Dict[str, Any]:
        p = self._playlist_get(playlist_id)
        if not p:
            return {"status": "failed", "output": f"Playlist {playlist_id} not found"}
        self.playlists.remove(p)
        self.playlist_items = [pi for pi in self.playlist_items
                               if pi["snippet"]["playlistId"] != playlist_id]
        return {"status": "ok", "output": {"deleted": True, "playlistId": playlist_id}}

    # --- Playlist Items ----------------------------------------------------
    def list_playlist_items(self, playlist_id: str, max_results: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = [pi for pi in self.playlist_items if pi["snippet"]["playlistId"] == playlist_id]
        results = sorted(results, key=lambda x: x["snippet"]["position"])
        total = len(results)
        page_results = results[offset: offset + max_results]
        return {"status": "ok", "output": {
            "kind": "youtube#playlistItemListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": page_results,
        }}

    def insert_playlist_item(self, snippet: Dict[str, Any]) -> Dict[str, Any]:
        snippet = snippet or {}
        playlist_id = snippet.get("playlistId")
        resource_id = snippet.get("resourceId", {})
        video_id = resource_id.get("videoId")
        if not playlist_id or not video_id:
            return {"status": "failed", "output": "Missing required fields: snippet.playlistId and snippet.resourceId.videoId"}
        if not self._playlist_get(playlist_id):
            return {"status": "failed", "output": f"Playlist {playlist_id} not found"}
        existing = [pi for pi in self.playlist_items if pi["snippet"]["playlistId"] == playlist_id]
        position = snippet.get("position", len(existing))
        n = self._next_id_counter(self.playlist_items, 26)
        now = self._now()
        item = {
            "id": f"PLI_{n:03d}",
            "snippet": {
                "publishedAt": now,
                "channelId": self._CHANNEL_ID,
                "title": "",
                "playlistId": playlist_id,
                "position": position,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
                "thumbnails": {
                    "default": {"url": f"https://i.ytimg.com/vi/{video_id}/default.jpg", "width": 120, "height": 90},
                    "medium": {"url": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", "width": 320, "height": 180},
                    "high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "width": 480, "height": 360},
                },
                "channelTitle": self._CHANNEL_TITLE,
            },
            "contentDetails": {"videoId": video_id, "videoPublishedAt": now},
        }
        v = self._video_get(video_id)
        if v:
            item["snippet"]["title"] = v["snippet"]["title"]
            item["contentDetails"]["videoPublishedAt"] = v["snippet"]["publishedAt"]
        self.playlist_items.append(item)
        parent = self._playlist_get(playlist_id)
        if parent:
            parent["contentDetails"]["itemCount"] = parent["contentDetails"].get("itemCount", 0) + 1
        return {"status": "ok", "output": {"kind": "youtube#playlistItem", "items": [item]}}

    def delete_playlist_item(self, playlist_item_id: str) -> Dict[str, Any]:
        pi = self._playlist_item_get(playlist_item_id)
        if not pi:
            return {"status": "failed", "output": f"Playlist item {playlist_item_id} not found"}
        playlist_id = pi["snippet"]["playlistId"]
        self.playlist_items.remove(pi)
        parent = self._playlist_get(playlist_id)
        if parent:
            parent["contentDetails"]["itemCount"] = max(0, parent["contentDetails"].get("itemCount", 0) - 1)
        return {"status": "ok", "output": {"deleted": True, "playlistItemId": playlist_item_id}}

    def update_playlist_item(self, playlist_item_id: str, snippet: Dict[str, Any] | None = None) -> Dict[str, Any]:
        pi = self._playlist_item_get(playlist_item_id)
        if not pi:
            return {"status": "failed", "output": f"Playlist item {playlist_item_id} not found"}
        snippet_updates = snippet or {}
        if "position" in snippet_updates:
            pi["snippet"]["position"] = int(snippet_updates["position"])
        return {"status": "ok", "output": {"kind": "youtube#playlistItem", "items": [pi]}}

    # --- Comment Threads ---------------------------------------------------
    def list_comment_threads(self, video_id: str | None = None, channel_id: str | None = None,
                             max_results: int = 20, offset: int = 0,
                             moderation_status: str = "published") -> Dict[str, Any]:
        all_comments = self.comments
        results = [c for c in all_comments if not c["parentId"]]
        if video_id:
            results = [c for c in results if c["videoId"] == video_id]
        results = [c for c in results if c["moderationStatus"] == moderation_status]
        results = sorted(results, key=lambda x: x["snippet"]["publishedAt"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + max_results]
        threads = []
        for comment in page_results:
            replies = [c for c in all_comments if c["parentId"] == comment["id"]]
            thread = {
                "kind": "youtube#commentThread",
                "id": comment["id"],
                "snippet": {
                    "channelId": self._CHANNEL_ID,
                    "videoId": comment["videoId"],
                    "topLevelComment": {"kind": "youtube#comment", "id": comment["id"], "snippet": comment["snippet"]},
                    "canReply": True,
                    "totalReplyCount": len(replies),
                    "isPublic": True,
                },
            }
            if replies:
                thread["replies"] = {"comments": [
                    {"kind": "youtube#comment", "id": r["id"], "snippet": r["snippet"]} for r in replies]}
            threads.append(thread)
        return {"status": "ok", "output": {
            "kind": "youtube#commentThreadListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": threads,
        }}

    def insert_comment_thread(self, snippet: Dict[str, Any]) -> Dict[str, Any]:
        snippet = snippet or {}
        video_id = snippet.get("videoId")
        text = snippet.get("topLevelComment", {}).get("snippet", {}).get("textOriginal", "")
        if not video_id or not text:
            return {"status": "failed", "output": "Missing required fields: snippet.videoId and snippet.topLevelComment.snippet.textOriginal"}
        n = self._next_id_counter(self.comments, 51)
        now = self._now()
        comment_id = f"cmt_{n:03d}"
        comment = {
            "id": comment_id,
            "videoId": video_id,
            "channelId": self._CHANNEL_ID,
            "parentId": None,
            "snippet": {
                "authorDisplayName": self._CHANNEL_TITLE,
                "authorChannelId": {"value": self._CHANNEL_ID},
                "textDisplay": text,
                "textOriginal": text,
                "likeCount": 0,
                "publishedAt": now,
                "updatedAt": now,
                "videoId": video_id,
                "parentId": None,
            },
            "moderationStatus": "published",
        }
        self.comments.append(comment)
        thread = {
            "kind": "youtube#commentThread",
            "id": comment_id,
            "snippet": {
                "channelId": self._CHANNEL_ID,
                "videoId": video_id,
                "topLevelComment": {"kind": "youtube#comment", "id": comment_id, "snippet": comment["snippet"]},
                "canReply": True,
                "totalReplyCount": 0,
                "isPublic": True,
            },
        }
        return {"status": "ok", "output": {"kind": "youtube#commentThread", "items": [thread]}}

    # --- Comments ----------------------------------------------------------
    def list_comments(self, parent_id: str, max_results: int = 20, offset: int = 0) -> Dict[str, Any]:
        results = [c for c in self.comments if c["parentId"] == parent_id]
        results = sorted(results, key=lambda x: x["snippet"]["publishedAt"])
        total = len(results)
        page_results = results[offset: offset + max_results]
        items = [{"kind": "youtube#comment", "id": c["id"], "snippet": c["snippet"]} for c in page_results]
        return {"status": "ok", "output": {
            "kind": "youtube#commentListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": items,
        }}

    def insert_comment(self, snippet: Dict[str, Any]) -> Dict[str, Any]:
        snippet = snippet or {}
        parent_id = snippet.get("parentId")
        text = snippet.get("textOriginal", "")
        if not parent_id or not text:
            return {"status": "failed", "output": "Missing required fields: snippet.parentId and snippet.textOriginal"}
        parent = self._comment_get(parent_id)
        if not parent:
            return {"status": "failed", "output": f"Parent comment {parent_id} not found"}
        video_id = parent["videoId"]
        n = self._next_id_counter(self.comments, 51)
        now = self._now()
        comment_id = f"cmt_{n:03d}"
        comment = {
            "id": comment_id,
            "videoId": video_id,
            "channelId": self._CHANNEL_ID,
            "parentId": parent_id,
            "snippet": {
                "authorDisplayName": self._CHANNEL_TITLE,
                "authorChannelId": {"value": self._CHANNEL_ID},
                "textDisplay": text,
                "textOriginal": text,
                "likeCount": 0,
                "publishedAt": now,
                "updatedAt": now,
                "videoId": video_id,
                "parentId": parent_id,
            },
            "moderationStatus": "published",
        }
        self.comments.append(comment)
        return {"status": "ok", "output": {
            "kind": "youtube#comment",
            "items": [{"kind": "youtube#comment", "id": comment_id, "snippet": comment["snippet"]}],
        }}

    def update_comment(self, comment_id: str, snippet: Dict[str, Any] | None = None) -> Dict[str, Any]:
        c = self._comment_get(comment_id)
        if not c:
            return {"status": "failed", "output": f"Comment {comment_id} not found"}
        snippet_updates = snippet or {}
        if "textOriginal" in snippet_updates:
            c["snippet"]["textOriginal"] = snippet_updates["textOriginal"]
            c["snippet"]["textDisplay"] = snippet_updates["textOriginal"]
            c["snippet"]["updatedAt"] = self._now()
        return {"status": "ok", "output": {
            "kind": "youtube#comment",
            "items": [{"kind": "youtube#comment", "id": comment_id, "snippet": c["snippet"]}],
        }}

    def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        c = self._comment_get(comment_id)
        if not c:
            return {"status": "failed", "output": f"Comment {comment_id} not found"}
        self.comments.remove(c)
        self.comments = [r for r in self.comments if r["parentId"] != comment_id]
        return {"status": "ok", "output": {"deleted": True, "commentId": comment_id}}

    def set_moderation_status(self, comment_ids, moderation_status: str) -> Dict[str, Any]:
        if isinstance(comment_ids, str):
            comment_ids = [cid.strip() for cid in comment_ids.split(",")]
        updated = []
        for cid in comment_ids:
            c = self._comment_get(cid)
            if c:
                c["moderationStatus"] = moderation_status
                updated.append(cid)
        if not updated:
            return {"status": "failed", "output": "No matching comments found"}
        return {"status": "ok", "output": {"updated": updated, "moderationStatus": moderation_status}}

    # --- Search ------------------------------------------------------------
    def search_videos(self, channel_id: str | None = None, q: str | None = None,
                      order: str = "relevance", max_results: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.videos)
        if channel_id:
            results = [v for v in results if v["snippet"]["channelId"] == channel_id]
        results = [v for v in results if v["status"]["privacyStatus"] in ("public", "unlisted")]
        if q:
            q_lower = q.lower()
            scored = []
            for v in results:
                score = 0
                title = v["snippet"]["title"].lower()
                desc = v["snippet"]["description"].lower()
                tags = [t.lower() for t in v["snippet"].get("tags", [])]
                if q_lower in title:
                    score += 10
                if q_lower in desc:
                    score += 5
                if any(q_lower in tag for tag in tags):
                    score += 3
                if score > 0:
                    scored.append((score, v))
            results = [v for _, v in sorted(scored, key=lambda x: x[0], reverse=True)]
        if order == "date":
            results = sorted(results, key=lambda x: x["snippet"]["publishedAt"], reverse=True)
        elif order == "viewCount":
            results = sorted(results, key=lambda x: int(x["statistics"]["viewCount"]), reverse=True)
        elif order == "rating":
            results = sorted(results, key=lambda x: int(x["statistics"]["likeCount"]), reverse=True)
        total = len(results)
        page_results = results[offset: offset + max_results]
        items = []
        for v in page_results:
            items.append({
                "kind": "youtube#searchResult",
                "id": {"kind": "youtube#video", "videoId": v["id"]},
                "snippet": {
                    "publishedAt": v["snippet"]["publishedAt"],
                    "channelId": v["snippet"]["channelId"],
                    "title": v["snippet"]["title"],
                    "description": v["snippet"]["description"][:200],
                    "thumbnails": v["snippet"]["thumbnails"],
                    "channelTitle": v["snippet"]["channelTitle"],
                    "liveBroadcastContent": v["snippet"]["liveBroadcastContent"],
                },
            })
        return {"status": "ok", "output": {
            "kind": "youtube#searchListResponse",
            "pageInfo": {"totalResults": total, "resultsPerPage": max_results},
            "items": items,
        }}

    # --- Video Categories --------------------------------------------------
    def list_video_categories(self) -> Dict[str, Any]:
        items = [{"kind": "youtube#videoCategory", "id": cat["id"], "snippet": cat["snippet"]}
                 for cat in self.video_categories]
        return {"status": "ok", "output": {"kind": "youtube#videoCategoryListResponse", "items": items}}

    # --- Captions ----------------------------------------------------------
    def list_captions(self, video_id: str) -> Dict[str, Any]:
        results = [c for c in self.captions if c["snippet"]["videoId"] == video_id]
        if not results:
            if not self._video_get(video_id):
                return {"status": "failed", "output": f"Video {video_id} not found"}
        items = [{"kind": "youtube#caption", "id": c["id"], "snippet": c["snippet"]} for c in results]
        return {"status": "ok", "output": {"kind": "youtube#captionListResponse", "items": items}}

    # --- Channel Sections --------------------------------------------------
    def list_channel_sections(self, channel_id: str) -> Dict[str, Any]:
        if channel_id != self._CHANNEL_ID:
            return {"status": "failed", "output": f"Channel {channel_id} not found"}
        items = [{"kind": "youtube#channelSection", "id": s["id"], "snippet": s["snippet"],
                  "contentDetails": s["contentDetails"]} for s in self.channel_sections]
        return {"status": "ok", "output": {"kind": "youtube#channelSectionListResponse", "items": items}}

    # --- Analytics ---------------------------------------------------------
    def get_channel_analytics(self) -> Dict[str, Any]:
        a = self.analytics
        return {"status": "ok", "output": {
            "kind": "youtubeAnalytics#resultTable",
            "channelId": self._CHANNEL_ID,
            "period": a["channel"]["period"],
            "metrics": a["channel"],
        }}

    def get_video_analytics(self, video_id: str) -> Dict[str, Any]:
        a = self.analytics
        for entry in a["videos"]:
            if entry["videoId"] == video_id:
                return {"status": "ok", "output": {
                    "kind": "youtubeAnalytics#resultTable",
                    "videoId": video_id,
                    "metrics": entry,
                }}
        return {"status": "failed", "output": f"Analytics for video {video_id} not found"}


if __name__ == "__main__":
    s = YoutubeSession(seed=12)
    print(s.get_channel())
    print(s.list_video_categories())
