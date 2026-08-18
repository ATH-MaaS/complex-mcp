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
class Book:
    bid: str
    title: str
    author: str
    kind: str = "book"  # book|article
    total_pages: int = 100
    progress: int = 0

@dataclass
class Bookmark:
    kid: str
    book_id: str
    page: int
    note: str = ""

@dataclass
class Highlight:
    hid: str
    book_id: str
    page: int
    text: str
    color: str = "yellow"

SEED_BOOKS = [
    ("Meditations", "Marcus Aurelius", "book", 200),
    ("The Pragmatic Programmer", "Andy Hunt", "book", 320),
    ("On the Nature of Software", "J. Doe", "article", 25),
]

class ReadSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.books: Dict[str, Book] = {}
            self.bookmarks: Dict[str, Bookmark] = {}
            self.highlights: Dict[str, Highlight] = {}
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightRead')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self):
        for title, author, kind, pages in SEED_BOOKS:
            b = Book(bid=self.uuid(), title=title, author=author, kind=kind, total_pages=pages, progress=self.rng.randint(0, pages))
            self.books[b.bid] = b

    def get_session_dict(self):
        return {
            "books": {k: asdict(v) for k, v in self.books.items()},
            "bookmarks": {k: asdict(v) for k, v in self.bookmarks.items()},
            "highlights": {k: asdict(v) for k, v in self.highlights.items()},
        }

    def list_books(self, kind: Optional[str] = None):
        out = [asdict(b) for b in self.books.values() if (kind is None or b.kind == kind)]
        return {"status": "ok", "output": out}

    def get_book(self, bid: str):
        b = self.books.get(bid)
        if not b: return {"status": "failed", "output": f"book {bid} not found"}
        return {"status": "ok", "output": asdict(b)}

    def add_book(self, title: str, author: str, kind: str = "book", total_pages: int = 100):
        b = Book(bid=self.uuid(), title=title, author=author, kind=kind, total_pages=total_pages)
        self.books[b.bid] = b
        return {"status": "ok", "output": asdict(b)}

    def delete_book(self, bid: str):
        if bid not in self.books: return {"status": "failed", "output": f"book {bid} not found"}
        del self.books[bid]
        return {"status": "ok", "output": bid}

    def update_progress(self, bid: str, page: int):
        b = self.books.get(bid)
        if not b: return {"status": "failed", "output": f"book {bid} not found"}
        b.progress = max(0, min(page, b.total_pages))
        return {"status": "ok", "output": asdict(b)}

    def list_bookmarks(self, book_id: Optional[str] = None):
        out = [asdict(m) for m in self.bookmarks.values() if (book_id is None or m.book_id == book_id)]
        return {"status": "ok", "output": out}

    def add_bookmark(self, book_id: str, page: int, note: str = ""):
        if book_id not in self.books: return {"status": "failed", "output": "book not found"}
        m = Bookmark(kid=self.uuid(), book_id=book_id, page=page, note=note)
        self.bookmarks[m.kid] = m
        return {"status": "ok", "output": asdict(m)}

    def delete_bookmark(self, kid: str):
        if kid not in self.bookmarks: return {"status": "failed", "output": "bookmark not found"}
        del self.bookmarks[kid]
        return {"status": "ok", "output": kid}

    def list_highlights(self, book_id: Optional[str] = None):
        out = [asdict(h) for h in self.highlights.values() if (book_id is None or h.book_id == book_id)]
        return {"status": "ok", "output": out}

    def add_highlight(self, book_id: str, page: int, text: str, color: str = "yellow"):
        if book_id not in self.books: return {"status": "failed", "output": "book not found"}
        h = Highlight(hid=self.uuid(), book_id=book_id, page=page, text=text, color=color)
        self.highlights[h.hid] = h
        return {"status": "ok", "output": asdict(h)}

    def delete_highlight(self, hid: str):
        if hid not in self.highlights: return {"status": "failed", "output": "highlight not found"}
        del self.highlights[hid]
        return {"status": "ok", "output": hid}

    def search(self, query: str):
        q = query.lower()
        hits = []
        for b in self.books.values():
            if q in b.title.lower() or q in b.author.lower():
                hits.append(asdict(b))
        return {"status": "ok", "output": hits}

    def get_stats(self):
        finished = sum(1 for b in self.books.values() if b.progress >= b.total_pages)
        return {"status": "ok", "output": {
            "total_books": len(self.books),
            "finished": finished,
            "total_bookmarks": len(self.bookmarks),
            "total_highlights": len(self.highlights),
        }}
