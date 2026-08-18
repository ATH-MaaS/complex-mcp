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

@dataclass
class SubForum:
    fid: str
    name: str
    description: str = ""

@dataclass
class Thread:
    tid: str
    subforum_id: str
    title: str
    author: str
    body: str
    created_at: str
    upvotes: int = 0
    downvotes: int = 0
    locked: bool = False
    pinned: bool = False

@dataclass
class Post:
    pid: str
    thread_id: str
    author: str
    body: str
    created_at: str
    upvotes: int = 0
    downvotes: int = 0

DEFAULT_SUBFORUMS = [
    ("general", "General discussion"),
    ("tech", "Technology"),
    ("random", "Off topic"),
]

class ForumSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.subforums: Dict[str, SubForum] = {}
            self.threads: Dict[str, Thread] = {}
            self.posts: Dict[str, Post] = {}
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightForum')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self):
        for name, desc in DEFAULT_SUBFORUMS:
            sf = SubForum(fid=self.uuid(), name=name, description=desc)
            self.subforums[sf.fid] = sf

    def get_session_dict(self):
        return {
            "subforums": {k: asdict(v) for k, v in self.subforums.items()},
            "threads": {k: asdict(v) for k, v in self.threads.items()},
            "posts": {k: asdict(v) for k, v in self.posts.items()},
        }

    def list_subforums(self):
        return {"status": "ok", "output": [asdict(s) for s in self.subforums.values()]}

    def create_subforum(self, name: str, description: str = ""):
        sf = SubForum(fid=self.uuid(), name=name, description=description)
        self.subforums[sf.fid] = sf
        return {"status": "ok", "output": asdict(sf)}

    def delete_subforum(self, fid: str):
        if fid not in self.subforums: return {"status": "failed", "output": "subforum not found"}
        del self.subforums[fid]
        return {"status": "ok", "output": fid}

    def list_threads(self, subforum_id: Optional[str] = None, pinned: Optional[bool] = None):
        out = []
        for t in self.threads.values():
            if subforum_id and t.subforum_id != subforum_id: continue
            if pinned is not None and t.pinned != pinned: continue
            out.append(asdict(t))
        return {"status": "ok", "output": out}

    def get_thread(self, tid: str):
        t = self.threads.get(tid)
        if not t: return {"status": "failed", "output": "thread not found"}
        return {"status": "ok", "output": asdict(t)}

    def create_thread(self, subforum_id: str, title: str, author: str, body: str):
        if subforum_id not in self.subforums: return {"status": "failed", "output": "subforum not found"}
        t = Thread(tid=self.uuid(), subforum_id=subforum_id, title=title, author=author,
                   body=body, created_at=self.os.now())
        self.threads[t.tid] = t
        return {"status": "ok", "output": asdict(t)}

    def delete_thread(self, tid: str):
        if tid not in self.threads: return {"status": "failed", "output": "thread not found"}
        del self.threads[tid]
        for pid in [p.pid for p in self.posts.values() if p.thread_id == tid]:
            del self.posts[pid]
        return {"status": "ok", "output": tid}

    def lock_thread(self, tid: str, locked: bool = True):
        t = self.threads.get(tid)
        if not t: return {"status": "failed", "output": "thread not found"}
        t.locked = locked
        return {"status": "ok", "output": asdict(t)}

    def pin_thread(self, tid: str, pinned: bool = True):
        t = self.threads.get(tid)
        if not t: return {"status": "failed", "output": "thread not found"}
        t.pinned = pinned
        return {"status": "ok", "output": asdict(t)}

    def list_posts(self, thread_id: str):
        out = [asdict(p) for p in self.posts.values() if p.thread_id == thread_id]
        return {"status": "ok", "output": out}

    def add_post(self, thread_id: str, author: str, body: str):
        t = self.threads.get(thread_id)
        if not t: return {"status": "failed", "output": "thread not found"}
        if t.locked: return {"status": "failed", "output": "thread is locked"}
        p = Post(pid=self.uuid(), thread_id=thread_id, author=author, body=body, created_at=self.os.now())
        self.posts[p.pid] = p
        return {"status": "ok", "output": asdict(p)}

    def delete_post(self, pid: str):
        if pid not in self.posts: return {"status": "failed", "output": "post not found"}
        del self.posts[pid]
        return {"status": "ok", "output": pid}

    def upvote_thread(self, tid: str):
        t = self.threads.get(tid)
        if not t: return {"status": "failed", "output": "thread not found"}
        t.upvotes += 1
        return {"status": "ok", "output": asdict(t)}

    def downvote_thread(self, tid: str):
        t = self.threads.get(tid)
        if not t: return {"status": "failed", "output": "thread not found"}
        t.downvotes += 1
        return {"status": "ok", "output": asdict(t)}

    def upvote_post(self, pid: str):
        p = self.posts.get(pid)
        if not p: return {"status": "failed", "output": "post not found"}
        p.upvotes += 1
        return {"status": "ok", "output": asdict(p)}

    def downvote_post(self, pid: str):
        p = self.posts.get(pid)
        if not p: return {"status": "failed", "output": "post not found"}
        p.downvotes += 1
        return {"status": "ok", "output": asdict(p)}

    def search_threads(self, query: str):
        q = query.lower()
        hits = [asdict(t) for t in self.threads.values() if q in t.title.lower() or q in t.body.lower()]
        return {"status": "ok", "output": hits}

    def top_threads(self, limit: int = 5):
        ranked = sorted(self.threads.values(), key=lambda t: t.upvotes - t.downvotes, reverse=True)
        return {"status": "ok", "output": [asdict(t) for t in ranked[:limit]]}

    def get_stats(self):
        return {"status": "ok", "output": {
            "subforums": len(self.subforums),
            "threads": len(self.threads),
            "posts": len(self.posts),
        }}
