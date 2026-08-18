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


SEED_PODCASTS = [
    ("The Signal Beat",  "Ana Rivers",   "Weekly deep dives on emerging tech.",         "tech",    "https://feeds.example.com/signalbeat.xml"),
    ("Kitchen Table",    "Marco Diaz",   "Home cooks talk pantry hacks and comfort food.","food",    "https://feeds.example.com/kitchentable.xml"),
    ("History Unfolded", "Priya Nair",   "Underreported moments from the last century.",  "history", "https://feeds.example.com/history.xml"),
]

SEED_EPISODES = [
    (1, "AI Chips in 2026",            "State of the accelerator market.",        3300,  -14),
    (1, "The Rust Foundation Update",  "New leadership, new priorities.",         2700,  -7),
    (1, "Deep Dive: Vector Databases", "How they work under the hood.",           4500,  -2),
    (2, "Sourdough for Skeptics",      "Why your starter keeps dying.",           1800,  -21),
    (2, "One-Pot Weeknights",          "Five dinners, one pan.",                  2100,  -10),
    (2, "Freezer Meal Prep",           "Batch cook for busy weeks.",              1650,  -4),
    (3, "The 1918 Flu Revisited",       "What we got wrong the first time.",      3900,  -30),
    (3, "Cold War Radio Wars",         "Propaganda over the airwaves.",           3600,  -8),
]

SEED_QUEUE = [
    (2, 0, -3),
    (5, 1, -2),
    (7, 2, -1),
]

SEED_PROGRESS = [
    (1, 1200, False),
    (3, 4500, True),
    (4, 400,  False),
    (8, 3600, True),
]

SEED_DOWNLOADS = [
    (2, -2, 47.3),
    (7, -1, 61.8),
]


@dataclass
class Podcast:
    pid: str
    title: str
    host: str
    description: str
    category: str
    feed_url: str


@dataclass
class Episode:
    eid: str
    podcast_id: str
    title: str
    description: str
    duration_seconds: int
    published_at: str
    audio_url: str


@dataclass
class QueueItem:
    qid: str
    episode_id: str
    position: int
    added_at: str


@dataclass
class Progress:
    episode_id: str
    seconds_played: int
    completed: bool


@dataclass
class Download:
    did: str
    episode_id: str
    downloaded_at: str
    size_mb: float


class PodcastSession:
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
            self.podcasts: Dict[str, Podcast] = {}
            self.episodes: Dict[str, Episode] = {}
            self.queue: Dict[str, QueueItem] = {}
            self.progress: Dict[str, Progress] = {}
            self.downloads: Dict[str, Download] = {}
            self.subscribed: set = set()
            self._podcast_index: List[str] = []
            self._episode_index: List[str] = []
            self._seed_podcasts()
            self._seed_episodes()
            self._seed_queue()
            self._seed_progress()
            self._seed_downloads()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPodcast')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_podcasts(self) -> None:
        for title, host, desc, cat, url in SEED_PODCASTS:
            p = Podcast(
                pid=self.uuid(),
                title=title,
                host=host,
                description=desc,
                category=cat,
                feed_url=url,
            )
            self.podcasts[p.pid] = p
            self._podcast_index.append(p.pid)

    def _seed_episodes(self) -> None:
        for pod_idx, title, desc, dur, day_off in SEED_EPISODES:
            pid = self._podcast_index[pod_idx - 1]
            pub = (self._today + timedelta(days=day_off)).isoformat(timespec="minutes")
            e = Episode(
                eid=self.uuid(),
                podcast_id=pid,
                title=title,
                description=desc,
                duration_seconds=dur,
                published_at=pub,
                audio_url=f"https://audio.example.com/{self.uuid()[:10]}.mp3",
            )
            self.episodes[e.eid] = e
            self._episode_index.append(e.eid)

    def _seed_queue(self) -> None:
        for ep_idx, pos, day_off in SEED_QUEUE:
            eid = self._episode_index[ep_idx - 1]
            q = QueueItem(
                qid=self.uuid(),
                episode_id=eid,
                position=pos,
                added_at=(self._today + timedelta(days=day_off)).isoformat(timespec="minutes"),
            )
            self.queue[q.qid] = q

    def _seed_progress(self) -> None:
        for ep_idx, secs, done in SEED_PROGRESS:
            eid = self._episode_index[ep_idx - 1]
            self.progress[eid] = Progress(episode_id=eid, seconds_played=secs, completed=done)

    def _seed_downloads(self) -> None:
        for ep_idx, day_off, size in SEED_DOWNLOADS:
            eid = self._episode_index[ep_idx - 1]
            d = Download(
                did=self.uuid(),
                episode_id=eid,
                downloaded_at=(self._today + timedelta(days=day_off)).isoformat(timespec="minutes"),
                size_mb=size,
            )
            self.downloads[d.did] = d

    def get_session_dict(self) -> Dict:
        return {
            "podcasts": {pid: asdict(p) for pid, p in self.podcasts.items()},
            "episodes": {eid: asdict(e) for eid, e in self.episodes.items()},
            "queue": {qid: asdict(q) for qid, q in self.queue.items()},
            "progress": {eid: asdict(pr) for eid, pr in self.progress.items()},
            "downloads": {did: asdict(d) for did, d in self.downloads.items()},
            "subscribed": sorted(self.subscribed),
        }

    def _podcast_summary(self, p: Podcast) -> Dict:
        return {
            "pid": p.pid,
            "title": p.title,
            "host": p.host,
            "category": p.category,
            "subscribed": p.pid in self.subscribed,
        }

    def _episode_summary(self, e: Episode) -> Dict:
        return {
            "eid": e.eid,
            "podcast_id": e.podcast_id,
            "title": e.title,
            "duration_seconds": e.duration_seconds,
            "published_at": e.published_at,
        }

    def list_podcasts(self, category: Optional[str] = None) -> Dict:
        items = list(self.podcasts.values())
        if category:
            items = [p for p in items if p.category == category]
        items.sort(key=lambda p: p.title.lower())
        return {"status": "ok", "output": [self._podcast_summary(p) for p in items]}

    def get_podcast(self, pid: str) -> Dict:
        p = self.podcasts.get(pid)
        if not p:
            return {"status": "failed", "output": f"podcast {pid} not found"}
        out = asdict(p)
        out["subscribed"] = pid in self.subscribed
        return {"status": "ok", "output": out}

    def subscribe_podcast(self, podcast_id: str) -> Dict:
        if podcast_id not in self.podcasts:
            return {"status": "failed", "output": f"podcast {podcast_id} not found"}
        if podcast_id in self.subscribed:
            return {"status": "failed", "output": f"already subscribed to {podcast_id}"}
        self.subscribed.add(podcast_id)
        return {"status": "ok", "output": {"podcast_id": podcast_id, "subscribed": True}}

    def unsubscribe_podcast(self, podcast_id: str) -> Dict:
        if podcast_id not in self.subscribed:
            return {"status": "failed", "output": f"not subscribed to {podcast_id}"}
        self.subscribed.discard(podcast_id)
        return {"status": "ok", "output": {"podcast_id": podcast_id, "subscribed": False}}

    def list_episodes(self, podcast_id: Optional[str] = None) -> Dict:
        items = list(self.episodes.values())
        if podcast_id:
            if podcast_id not in self.podcasts:
                return {"status": "failed", "output": f"podcast {podcast_id} not found"}
            items = [e for e in items if e.podcast_id == podcast_id]
        items.sort(key=lambda e: e.published_at, reverse=True)
        return {"status": "ok", "output": [self._episode_summary(e) for e in items]}

    def get_episode(self, eid: str) -> Dict:
        e = self.episodes.get(eid)
        if not e:
            return {"status": "failed", "output": f"episode {eid} not found"}
        return {"status": "ok", "output": asdict(e)}

    def search_episodes(self, query: str) -> Dict:
        q = query.lower()
        items = [e for e in self.episodes.values()
                 if q in e.title.lower() or q in e.description.lower()]
        items.sort(key=lambda e: e.published_at, reverse=True)
        return {"status": "ok", "output": [self._episode_summary(e) for e in items]}

    def list_queue(self) -> Dict:
        items = list(self.queue.values())
        items.sort(key=lambda q: q.position)
        return {"status": "ok", "output": [asdict(q) for q in items]}

    def add_to_queue(self, episode_id: str) -> Dict:
        if episode_id not in self.episodes:
            return {"status": "failed", "output": f"episode {episode_id} not found"}
        for q in self.queue.values():
            if q.episode_id == episode_id:
                return {"status": "failed", "output": f"episode {episode_id} already queued"}
        pos = max((q.position for q in self.queue.values()), default=-1) + 1
        q = QueueItem(qid=self.uuid(), episode_id=episode_id, position=pos, added_at=self._now())
        self.queue[q.qid] = q
        return {"status": "ok", "output": asdict(q)}

    def remove_from_queue(self, qid: str) -> Dict:
        q = self.queue.pop(qid, None)
        if not q:
            return {"status": "failed", "output": f"queue item {qid} not found"}
        return {"status": "ok", "output": {"qid": qid, "removed": True}}

    def reorder_queue(self, qid: str, position: int) -> Dict:
        target = self.queue.get(qid)
        if not target:
            return {"status": "failed", "output": f"queue item {qid} not found"}
        ordered = sorted([q for q in self.queue.values() if q.qid != qid], key=lambda q: q.position)
        position = max(0, min(position, len(ordered)))
        ordered.insert(position, target)
        for idx, q in enumerate(ordered):
            q.position = idx
        return {"status": "ok", "output": [asdict(q) for q in ordered]}

    def list_progress(self) -> Dict:
        return {"status": "ok", "output": [asdict(p) for p in self.progress.values()]}

    def update_progress(self, episode_id: str, seconds_played: int) -> Dict:
        e = self.episodes.get(episode_id)
        if not e:
            return {"status": "failed", "output": f"episode {episode_id} not found"}
        completed = seconds_played >= e.duration_seconds
        pr = Progress(episode_id=episode_id, seconds_played=seconds_played, completed=completed)
        self.progress[episode_id] = pr
        return {"status": "ok", "output": asdict(pr)}

    def mark_completed(self, episode_id: str) -> Dict:
        e = self.episodes.get(episode_id)
        if not e:
            return {"status": "failed", "output": f"episode {episode_id} not found"}
        pr = Progress(episode_id=episode_id, seconds_played=e.duration_seconds, completed=True)
        self.progress[episode_id] = pr
        return {"status": "ok", "output": asdict(pr)}

    def list_downloads(self) -> Dict:
        items = list(self.downloads.values())
        items.sort(key=lambda d: d.downloaded_at, reverse=True)
        return {"status": "ok", "output": [asdict(d) for d in items]}

    def download_episode(self, episode_id: str) -> Dict:
        e = self.episodes.get(episode_id)
        if not e:
            return {"status": "failed", "output": f"episode {episode_id} not found"}
        for d in self.downloads.values():
            if d.episode_id == episode_id:
                return {"status": "failed", "output": f"episode {episode_id} already downloaded"}
        size = round(e.duration_seconds * 0.016, 1)
        d = Download(
            did=self.uuid(),
            episode_id=episode_id,
            downloaded_at=self._now(),
            size_mb=size,
        )
        self.downloads[d.did] = d
        return {"status": "ok", "output": asdict(d)}

    def delete_download(self, did: str) -> Dict:
        d = self.downloads.pop(did, None)
        if not d:
            return {"status": "failed", "output": f"download {did} not found"}
        return {"status": "ok", "output": {"did": did, "deleted": True}}

    def get_stats(self) -> Dict:
        total_downloaded_mb = round(sum(d.size_mb for d in self.downloads.values()), 2)
        completed = sum(1 for p in self.progress.values() if p.completed)
        return {
            "status": "ok",
            "output": {
                "total_podcasts": len(self.podcasts),
                "total_episodes": len(self.episodes),
                "total_subscribed": len(self.subscribed),
                "queue_length": len(self.queue),
                "progress_entries": len(self.progress),
                "completed_episodes": completed,
                "downloads": len(self.downloads),
                "total_downloaded_mb": total_downloaded_mb,
            },
        }
