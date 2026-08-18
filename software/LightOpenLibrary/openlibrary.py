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


def _split(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]


class OpenlibrarySession:
    """Deterministic sandbox for the Open Library API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "openlibrary.yaml") as f:
                info = yaml.safe_load(f)

            self.authors: List[Dict[str, Any]] = [
                {
                    "author_id": r["author_id"],
                    "name": r["name"],
                    "birth_date": (str(r.get("birth_date") or "") or None),
                    "death_date": (str(r.get("death_date") or "") or None),
                    "bio": r["bio"],
                    "top_work": r["top_work"],
                    "work_count": int(r["work_count"]),
                }
                for r in info.get("authors", [])
            ]
            self.works: List[Dict[str, Any]] = [
                {
                    "work_id": r["work_id"],
                    "title": r["title"],
                    "author_id": r["author_id"],
                    "first_publish_year": int(r["first_publish_year"]),
                    "subjects": _split(r["subjects"]),
                    "description": r["description"],
                    "edition_count": int(r["edition_count"]),
                }
                for r in info.get("works", [])
            ]
            self.editions: List[Dict[str, Any]] = [
                {
                    "edition_id": r["edition_id"],
                    "work_id": r["work_id"],
                    "title": r["title"],
                    "isbn_13": r["isbn_13"],
                    "isbn_10": r["isbn_10"],
                    "publisher": r["publisher"],
                    "publish_date": r["publish_date"],
                    "number_of_pages": int(r["number_of_pages"]),
                    "language": r["language"],
                }
                for r in info.get("editions", [])
            ]
            self.subjects: List[Dict[str, Any]] = list(info.get("subjects", []))
            self._authors_by_id = {a["author_id"]: a for a in self.authors}
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightOpenLibrary')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"works": self.works}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _author_name(self, author_id):
        a = self._authors_by_id.get(author_id)
        return a["name"] if a else "Unknown"

    def _work_doc(self, w):
        return {
            "key": f"/works/{w['work_id']}",
            "type": "work",
            "title": w["title"],
            "first_publish_year": w["first_publish_year"],
            "author_key": [w["author_id"]],
            "author_name": [self._author_name(w["author_id"])],
            "subject": w["subjects"],
            "edition_count": w["edition_count"],
        }

    def _edition_doc(self, e):
        return {
            "key": f"/books/{e['edition_id']}",
            "title": e["title"],
            "works": [{"key": f"/works/{e['work_id']}"}],
            "isbn_13": [e["isbn_13"]],
            "isbn_10": [e["isbn_10"]],
            "publishers": [e["publisher"]],
            "publish_date": e["publish_date"],
            "number_of_pages": e["number_of_pages"],
            "languages": [{"key": f"/languages/{e['language']}"}],
            "type": {"key": "/type/edition"},
        }

    def _find_work(self, work_id):
        return next((w for w in self.works if w["work_id"] == work_id), None)

    # --- Search ------------------------------------------------------------
    def search(self, q: str | None = None, author: str | None = None, title: str | None = None,
               page: int = 1, limit: int = 20) -> Dict[str, Any]:
        matches = list(self.works)
        if title:
            t = title.lower()
            matches = [w for w in matches if t in w["title"].lower()]
        if author:
            a = author.lower()
            matches = [w for w in matches if a in self._author_name(w["author_id"]).lower()]
        if q:
            ql = q.lower()
            matches = [
                w for w in matches
                if ql in w["title"].lower()
                or ql in self._author_name(w["author_id"]).lower()
                or any(ql in s.lower() for s in w["subjects"])
            ]
        matches.sort(key=lambda w: w["edition_count"], reverse=True)
        page = max(1, int(page or 1))
        limit = max(1, min(int(limit or 20), 100))
        start = (page - 1) * limit
        docs = [self._work_doc(w) for w in matches[start:start + limit]]
        return {"status": "ok", "output": {
            "numFound": len(matches),
            "start": start,
            "numFoundExact": True,
            "docs": docs,
        }}

    # --- Works -------------------------------------------------------------
    def get_work(self, work_id: str) -> Dict[str, Any]:
        w = self._find_work(work_id)
        if not w:
            return {"status": "failed", "output": f"Work {work_id} not found"}
        return {"status": "ok", "output": {
            "key": f"/works/{w['work_id']}",
            "title": w["title"],
            "description": w["description"],
            "first_publish_date": str(w["first_publish_year"]),
            "subjects": w["subjects"],
            "authors": [
                {"author": {"key": f"/authors/{w['author_id']}"}, "type": {"key": "/type/author_role"}}
            ],
            "type": {"key": "/type/work"},
        }}

    def get_work_editions(self, work_id: str) -> Dict[str, Any]:
        w = self._find_work(work_id)
        if not w:
            return {"status": "failed", "output": f"Work {work_id} not found"}
        eds = [e for e in self.editions if e["work_id"] == work_id]
        entries = [self._edition_doc(e) for e in eds]
        return {"status": "ok", "output": {
            "links": {"work": f"/works/{work_id}"},
            "size": len(entries),
            "entries": entries,
        }}

    # --- Editions / ISBN ---------------------------------------------------
    def get_isbn(self, isbn: str) -> Dict[str, Any]:
        isbn = (isbn or "").replace("-", "")
        e = next((x for x in self.editions if x["isbn_13"] == isbn or x["isbn_10"] == isbn), None)
        if not e:
            return {"status": "failed", "output": f"No edition found for ISBN {isbn}"}
        return {"status": "ok", "output": self._edition_doc(e)}

    # --- Authors -----------------------------------------------------------
    def get_author(self, author_id: str) -> Dict[str, Any]:
        a = self._authors_by_id.get(author_id)
        if not a:
            return {"status": "failed", "output": f"Author {author_id} not found"}
        return {"status": "ok", "output": {
            "key": f"/authors/{a['author_id']}",
            "name": a["name"],
            "birth_date": a["birth_date"],
            "death_date": a["death_date"],
            "bio": a["bio"],
            "top_work": a["top_work"],
            "work_count": a["work_count"],
            "type": {"key": "/type/author"},
        }}

    def get_author_works(self, author_id: str) -> Dict[str, Any]:
        if author_id not in self._authors_by_id:
            return {"status": "failed", "output": f"Author {author_id} not found"}
        works = [w for w in self.works if w["author_id"] == author_id]
        entries = []
        for w in works:
            entries.append({
                "key": f"/works/{w['work_id']}",
                "title": w["title"],
                "first_publish_date": str(w["first_publish_year"]),
                "subjects": w["subjects"],
                "type": {"key": "/type/work"},
            })
        return {"status": "ok", "output": {"size": len(entries), "entries": entries}}

    # --- Subjects ----------------------------------------------------------
    def get_subject(self, subject: str) -> Dict[str, Any]:
        key = (subject or "").lower().replace(" ", "_")
        meta = next((s for s in self.subjects if s["subject"] == key), None)
        name = meta["name"] if meta else subject.replace("_", " ").title()
        works = [w for w in self.works if key in [s.replace(" ", "_") for s in w["subjects"]]]
        works.sort(key=lambda w: w["edition_count"], reverse=True)
        return {"status": "ok", "output": {
            "key": f"/subjects/{key}",
            "name": name,
            "subject_type": "subject",
            "work_count": len(works),
            "works": [
                {
                    "key": f"/works/{w['work_id']}",
                    "title": w["title"],
                    "authors": [{"key": f"/authors/{w['author_id']}", "name": self._author_name(w["author_id"])}],
                    "first_publish_year": w["first_publish_year"],
                    "edition_count": w["edition_count"],
                }
                for w in works
            ],
        }}


if __name__ == "__main__":
    s = OpenlibrarySession(seed=12)
    print(s.search(q="ring"))
    print(s.get_subject("fantasy"))
