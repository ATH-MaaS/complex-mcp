from typing import Dict, List, Optional
from pathlib import Path
import random, sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


SEED_VIDEOS = [
    ("Intro to Rust in 20 Minutes",   "Fast overview of Rust basics.",       "DevDaily",    1200,  "tech",      53000,  4100,  -12),
    ("Live: Coding a Discord Bot",    "Building a bot end to end.",          "DevDaily",    3600,  "tech",      12000,  980,   -6),
    ("Lo-fi Beats for Focus",         "Two hours of lo-fi study music.",     "MoodTunes",   7200,  "music",     210000, 15000, -30),
    ("Synthwave Drive",               "New synthwave single.",               "MoodTunes",   240,   "music",     44000,  3300,  -3),
    ("Elden Ring Speedrun WR",        "New any% world record run.",          "PixelPlays",  4200,  "gaming",    89000,  7200,  -9),
    ("Beginner Chess Traps",          "Five traps to punish weak openings.", "PixelPlays",  900,   "gaming",    17000,  1400,  -2),
    ("Sourdough at Home",             "Simple sourdough recipe.",            "HomeCookery", 620,   "education", 8600,   740,   -20),
    ("Weeknight Ramen",               "20-minute ramen from pantry stock.",  "HomeCookery", 480,   "education", 5400,   410,   -1),
]

SEED_PLAYLISTS = [
    ("Watch Later", [1, 3]),
    ("Study Focus", [3, 4, 7]),
]

SEED_HISTORY = [
    (1, -5, 900),
    (3, -4, 3600),
    (5, -3, 4200),
    (8, -1, 480),
]

SEED_SUBSCRIPTIONS = ["DevDaily", "MoodTunes", "PixelPlays"]


@dataclass
class Video:
    vid: str
    title: str
    description: str
    channel: str
    duration_seconds: int
    category: str
    views: int
    likes: int
    published_at: str


@dataclass
class Playlist:
    plid: str
    name: str
    video_ids: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class WatchHistory:
    whid: str
    vid: str
    watched_at: str
    progress_seconds: int


@dataclass
class Subscription:
    subid: str
    channel: str


class VideoSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"],
            ) if os_cfg else DummyOSConnector()
            self._today = datetime(2026, 1, 5)
            self.videos: Dict[str, Video] = {}
            self.playlists: Dict[str, Playlist] = {}
            self.history: Dict[str, WatchHistory] = {}
            self.subscriptions: Dict[str, Subscription] = {}
            self._video_index: List[str] = []
            self._seed_videos()
            self._seed_playlists()
            self._seed_history()
            self._seed_subscriptions()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightVideo')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_videos(self) -> None:
        for title, desc, channel, dur, cat, views, likes, day_off in SEED_VIDEOS:
            pub = (self._today + timedelta(days=day_off)).isoformat(timespec="minutes")
            v = Video(
                vid=self.uuid(),
                title=title,
                description=desc,
                channel=channel,
                duration_seconds=dur,
                category=cat,
                views=views,
                likes=likes,
                published_at=pub,
            )
            self.videos[v.vid] = v
            self._video_index.append(v.vid)

    def _seed_playlists(self) -> None:
        for name, idxs in SEED_PLAYLISTS:
            vids = [self._video_index[i - 1] for i in idxs]
            p = Playlist(
                plid=self.uuid(),
                name=name,
                video_ids=list(vids),
                created_at=self._now(),
            )
            self.playlists[p.plid] = p

    def _seed_history(self) -> None:
        for idx, day_off, prog in SEED_HISTORY:
            vid = self._video_index[idx - 1]
            w = WatchHistory(
                whid=self.uuid(),
                vid=vid,
                watched_at=(self._today + timedelta(days=day_off)).isoformat(timespec="minutes"),
                progress_seconds=prog,
            )
            self.history[w.whid] = w

    def _seed_subscriptions(self) -> None:
        for ch in SEED_SUBSCRIPTIONS:
            s = Subscription(subid=self.uuid(), channel=ch)
            self.subscriptions[s.subid] = s

    def get_session_dict(self) -> Dict:
        return {
            "videos": {vid: asdict(v) for vid, v in self.videos.items()},
            "playlists": {plid: asdict(p) for plid, p in self.playlists.items()},
            "history": {whid: asdict(w) for whid, w in self.history.items()},
            "subscriptions": {subid: asdict(s) for subid, s in self.subscriptions.items()},
        }

    def _video_summary(self, v: Video) -> Dict:
        return {
            "vid": v.vid,
            "title": v.title,
            "channel": v.channel,
            "category": v.category,
            "duration_seconds": v.duration_seconds,
            "views": v.views,
            "likes": v.likes,
            "published_at": v.published_at,
        }

    def list_videos(self, category: Optional[str] = None, channel: Optional[str] = None) -> Dict:
        items = list(self.videos.values())
        if category:
            items = [v for v in items if v.category == category]
        if channel:
            items = [v for v in items if v.channel == channel]
        items.sort(key=lambda v: v.published_at, reverse=True)
        return {"status": "ok", "output": [self._video_summary(v) for v in items]}

    def get_video(self, vid: str) -> Dict:
        v = self.videos.get(vid)
        if not v:
            return {"status": "failed", "output": f"video {vid} not found"}
        return {"status": "ok", "output": asdict(v)}

    def search_videos(self, query: str) -> Dict:
        q = query.lower()
        items = [v for v in self.videos.values()
                 if q in v.title.lower() or q in v.description.lower()
                 or q in v.channel.lower() or q in v.category.lower()]
        items.sort(key=lambda v: v.views, reverse=True)
        return {"status": "ok", "output": [self._video_summary(v) for v in items]}

    def list_playlists(self) -> Dict:
        return {"status": "ok", "output": [asdict(p) for p in self.playlists.values()]}

    def get_playlist(self, plid: str) -> Dict:
        p = self.playlists.get(plid)
        if not p:
            return {"status": "failed", "output": f"playlist {plid} not found"}
        vids = [self._video_summary(self.videos[v]) for v in p.video_ids if v in self.videos]
        return {"status": "ok", "output": {"plid": p.plid, "name": p.name, "created_at": p.created_at, "videos": vids}}

    def create_playlist(self, name: str) -> Dict:
        p = Playlist(plid=self.uuid(), name=name, video_ids=[], created_at=self._now())
        self.playlists[p.plid] = p
        return {"status": "ok", "output": asdict(p)}

    def delete_playlist(self, plid: str) -> Dict:
        p = self.playlists.pop(plid, None)
        if not p:
            return {"status": "failed", "output": f"playlist {plid} not found"}
        return {"status": "ok", "output": {"plid": plid, "deleted": True}}

    def add_to_playlist(self, plid: str, vid: str) -> Dict:
        p = self.playlists.get(plid)
        if not p:
            return {"status": "failed", "output": f"playlist {plid} not found"}
        if vid not in self.videos:
            return {"status": "failed", "output": f"video {vid} not found"}
        if vid not in p.video_ids:
            p.video_ids.append(vid)
        return {"status": "ok", "output": asdict(p)}

    def remove_from_playlist(self, plid: str, vid: str) -> Dict:
        p = self.playlists.get(plid)
        if not p:
            return {"status": "failed", "output": f"playlist {plid} not found"}
        if vid in p.video_ids:
            p.video_ids.remove(vid)
        return {"status": "ok", "output": asdict(p)}

    def list_watch_history(self, limit: int = 20) -> Dict:
        items = list(self.history.values())
        items.sort(key=lambda w: w.watched_at, reverse=True)
        return {"status": "ok", "output": [asdict(w) for w in items[:limit]]}

    def record_watch(self, vid: str, progress_seconds: int) -> Dict:
        if vid not in self.videos:
            return {"status": "failed", "output": f"video {vid} not found"}
        w = WatchHistory(
            whid=self.uuid(),
            vid=vid,
            watched_at=self._now(),
            progress_seconds=progress_seconds,
        )
        self.history[w.whid] = w
        self.videos[vid].views += 1
        return {"status": "ok", "output": asdict(w)}

    def clear_history(self) -> Dict:
        count = len(self.history)
        self.history.clear()
        return {"status": "ok", "output": {"cleared": count}}

    def list_subscriptions(self) -> Dict:
        return {"status": "ok", "output": [asdict(s) for s in self.subscriptions.values()]}

    def subscribe(self, channel: str) -> Dict:
        for s in self.subscriptions.values():
            if s.channel == channel:
                return {"status": "failed", "output": f"already subscribed to {channel}"}
        s = Subscription(subid=self.uuid(), channel=channel)
        self.subscriptions[s.subid] = s
        return {"status": "ok", "output": asdict(s)}

    def unsubscribe(self, channel: str) -> Dict:
        target = None
        for subid, s in self.subscriptions.items():
            if s.channel == channel:
                target = subid
                break
        if not target:
            return {"status": "failed", "output": f"not subscribed to {channel}"}
        del self.subscriptions[target]
        return {"status": "ok", "output": {"channel": channel, "unsubscribed": True}}

    def like_video(self, vid: str) -> Dict:
        v = self.videos.get(vid)
        if not v:
            return {"status": "failed", "output": f"video {vid} not found"}
        v.likes += 1
        return {"status": "ok", "output": self._video_summary(v)}

    def get_recommended(self, limit: int = 5) -> Dict:
        subscribed_channels = {s.channel for s in self.subscriptions.values()}
        watched_vids = {w.vid for w in self.history.values()}
        primary = [v for v in self.videos.values()
                   if v.vid not in watched_vids and v.channel in subscribed_channels]
        if len(primary) < limit:
            extras = [v for v in self.videos.values()
                      if v.vid not in watched_vids and v not in primary]
            primary.extend(extras)
        primary.sort(key=lambda v: v.views, reverse=True)
        return {"status": "ok", "output": [self._video_summary(v) for v in primary[:limit]]}

    def get_stats(self) -> Dict:
        by_category: Dict[str, int] = {}
        by_channel: Dict[str, int] = {}
        for v in self.videos.values():
            by_category[v.category] = by_category.get(v.category, 0) + 1
            by_channel[v.channel] = by_channel.get(v.channel, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total_videos": len(self.videos),
                "total_playlists": len(self.playlists),
                "total_history": len(self.history),
                "total_subscriptions": len(self.subscriptions),
                "by_category": by_category,
                "by_channel": by_channel,
            },
        }
