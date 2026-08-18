from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


DEFAULT_NOTEBOOKS = [
    {"nbid": "nb_personal", "name": "Personal", "color": "#4285F4", "description": "Personal notes"},
    {"nbid": "nb_work",     "name": "Work",     "color": "#DB4437", "description": "Work notes"},
    {"nbid": "nb_ideas",    "name": "Ideas",    "color": "#0F9D58", "description": "Ideas and brainstorms"},
]

SEED_NOTES = [
    ("Weekly reflection",            "Reflections on the past week and next steps.", "nb_personal", ["journal"],        False, False),
    ("Grocery list",                 "Milk, eggs, bread, apples, coffee.",           "nb_personal", ["errand"],         True,  False),
    ("Q1 OKRs draft",                "Objectives and key results for Q1 planning.",  "nb_work",     ["planning", "okr"],True,  False),
    ("Sprint retro notes",           "What went well, what didn't, action items.",   "nb_work",     ["retro"],          False, False),
    ("Startup idea: MCP marketplace","Marketplace for stateful MCP servers.",        "nb_ideas",    ["startup"],        False, False),
    ("Old draft: 2025 goals",        "Archived draft of last year's goals.",         "nb_personal", ["draft"],          False, True),
]


@dataclass
class Notebook:
    nbid: str
    name: str
    color: str
    description: str = ""


@dataclass
class Note:
    nid: str
    title: str
    content: str
    notebook_id: str
    tags: List[str] = field(default_factory=list)
    is_pinned: bool = False
    is_archived: bool = False
    created_at: str = ""
    updated_at: str = ""


class NotesSession:
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
            self.notebooks: Dict[str, Notebook] = {
                n["nbid"]: Notebook(**n) for n in DEFAULT_NOTEBOOKS
            }
            self.notes: Dict[str, Note] = {}
            self._today = datetime(2026, 1, 5)
            self._seed_notes()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightNotes')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_notes(self) -> None:
        for i, (title, content, nbid, tags, is_pinned, is_archived) in enumerate(SEED_NOTES):
            created = (self._today - timedelta(days=(len(SEED_NOTES) - i))).isoformat(timespec="minutes")
            n = Note(
                nid=self.uuid(),
                title=title,
                content=content,
                notebook_id=nbid,
                tags=list(tags),
                is_pinned=is_pinned,
                is_archived=is_archived,
                created_at=created,
                updated_at=created,
            )
            self.notes[n.nid] = n

    def get_session_dict(self) -> Dict:
        return {
            "notebooks": {nbid: asdict(nb) for nbid, nb in self.notebooks.items()},
            "notes": {nid: asdict(n) for nid, n in self.notes.items()},
        }

    def _note_summary(self, n: Note) -> Dict:
        return {
            "nid": n.nid,
            "title": n.title,
            "notebook_id": n.notebook_id,
            "tags": list(n.tags),
            "is_pinned": n.is_pinned,
            "is_archived": n.is_archived,
            "updated_at": n.updated_at,
        }

    def list_notebooks(self) -> Dict:
        return {"status": "ok", "output": [asdict(nb) for nb in self.notebooks.values()]}

    def create_notebook(self, name: str, color: str = "#888888", description: str = "") -> Dict:
        nbid = "nb_" + self.uuid()[:8]
        nb = Notebook(nbid=nbid, name=name, color=color, description=description)
        self.notebooks[nbid] = nb
        return {"status": "ok", "output": asdict(nb)}

    def delete_notebook(self, nbid: str) -> Dict:
        if nbid not in self.notebooks:
            return {"status": "failed", "output": f"notebook {nbid} not found"}
        del self.notebooks[nbid]
        removed = [nid for nid, n in self.notes.items() if n.notebook_id == nbid]
        for nid in removed:
            del self.notes[nid]
        return {"status": "ok", "output": {"nbid": nbid, "removed_notes": len(removed)}}

    def list_notes(self, notebook_id: Optional[str] = None,
                   tag: Optional[str] = None,
                   archived: Optional[bool] = None) -> Dict:
        items = list(self.notes.values())
        if notebook_id:
            items = [n for n in items if n.notebook_id == notebook_id]
        if tag:
            items = [n for n in items if tag in n.tags]
        if archived is not None:
            items = [n for n in items if n.is_archived == archived]
        items.sort(key=lambda n: (not n.is_pinned, n.updated_at), reverse=False)
        return {"status": "ok", "output": [self._note_summary(n) for n in items]}

    def get_note(self, nid: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        return {"status": "ok", "output": asdict(n)}

    def create_note(self, title: str, content: str = "",
                    notebook_id: str = "nb_personal",
                    tags: Optional[List[str]] = None) -> Dict:
        if notebook_id not in self.notebooks:
            return {"status": "failed", "output": f"notebook {notebook_id} not found"}
        n = Note(
            nid=self.uuid(),
            title=title,
            content=content,
            notebook_id=notebook_id,
            tags=list(tags) if tags else [],
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.notes[n.nid] = n
        return {"status": "ok", "output": self._note_summary(n)}

    def update_note(self, nid: str,
                    title: Optional[str] = None,
                    content: Optional[str] = None,
                    notebook_id: Optional[str] = None,
                    tags: Optional[List[str]] = None) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        if notebook_id is not None and notebook_id not in self.notebooks:
            return {"status": "failed", "output": f"notebook {notebook_id} not found"}
        for k, v in {"title": title, "content": content, "notebook_id": notebook_id}.items():
            if v is not None:
                setattr(n, k, v)
        if tags is not None:
            n.tags = list(tags)
        n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def delete_note(self, nid: str) -> Dict:
        n = self.notes.pop(nid, None)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        return {"status": "ok", "output": {"nid": nid, "deleted": True}}

    def pin_note(self, nid: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        n.is_pinned = True
        n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def unpin_note(self, nid: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        n.is_pinned = False
        n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def archive_note(self, nid: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        n.is_archived = True
        n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def unarchive_note(self, nid: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        n.is_archived = False
        n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def add_tag(self, nid: str, tag: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        if tag not in n.tags:
            n.tags.append(tag)
            n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def remove_tag(self, nid: str, tag: str) -> Dict:
        n = self.notes.get(nid)
        if not n:
            return {"status": "failed", "output": f"note {nid} not found"}
        if tag in n.tags:
            n.tags.remove(tag)
            n.updated_at = self._now()
        return {"status": "ok", "output": self._note_summary(n)}

    def search_notes(self, query: str) -> Dict:
        q = query.lower()
        items = [n for n in self.notes.values()
                 if q in n.title.lower() or q in n.content.lower()
                 or any(q in tag.lower() for tag in n.tags)]
        items.sort(key=lambda n: n.updated_at, reverse=True)
        return {"status": "ok", "output": [self._note_summary(n) for n in items]}

    def list_recent(self, limit: int = 5) -> Dict:
        items = sorted(self.notes.values(), key=lambda n: n.updated_at, reverse=True)
        return {"status": "ok", "output": [self._note_summary(n) for n in items[:limit]]}

    def list_pinned(self) -> Dict:
        items = [n for n in self.notes.values() if n.is_pinned]
        items.sort(key=lambda n: n.updated_at, reverse=True)
        return {"status": "ok", "output": [self._note_summary(n) for n in items]}

    def get_stats(self) -> Dict:
        by_notebook: Dict[str, int] = {nbid: 0 for nbid in self.notebooks}
        pinned = 0
        archived = 0
        for n in self.notes.values():
            by_notebook[n.notebook_id] = by_notebook.get(n.notebook_id, 0) + 1
            if n.is_pinned:
                pinned += 1
            if n.is_archived:
                archived += 1
        return {
            "status": "ok",
            "output": {
                "total": len(self.notes),
                "notebooks": len(self.notebooks),
                "pinned": pinned,
                "archived": archived,
                "by_notebook": by_notebook,
            },
        }
