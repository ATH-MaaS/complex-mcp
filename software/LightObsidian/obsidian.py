import random
from typing import Dict, List, Any
from pathlib import Path
import re
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

_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


class ObsidianSession:
    """Deterministic sandbox for the Obsidian Local REST API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "obsidian.yaml") as f:
                info = yaml.safe_load(f)

            self.notes: List[Dict[str, Any]] = [
                {
                    "path": r["path"],
                    "title": r["title"],
                    "size_bytes": int(r.get("size_bytes") or 0),
                    "modified_at": r["modified_at"],
                    "tags": [t.strip() for t in str(r.get("tags") or "").split(";") if t.strip()],
                }
                for r in info.get("notes", [])
            ]
            self.contents: Dict[str, str] = {
                r["path"]: r["content"].replace("\\n", "\n") for r in info.get("note_contents", [])
            }
            self.vault: Dict[str, Any] = info.get("vault", {})
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightObsidian')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"notes": self.notes, "contents": self.contents}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _index_of(self, path):
        for i, n in enumerate(self.notes):
            if n["path"] == path:
                return i
        return -1

    def _extract_tags(self, content):
        return [m.group(1) for m in re.finditer(r"(?:^|\s)#([A-Za-z0-9_/-]+)", content)]

    # --- Vault -------------------------------------------------------------
    def get_vault(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.vault}

    # --- Notes -------------------------------------------------------------
    def list_notes(self, folder: str | None = None, tag: str | None = None) -> Dict[str, Any]:
        results = list(self.notes)
        if folder:
            prefix = folder.rstrip("/") + "/"
            results = [n for n in results if n["path"].startswith(prefix)]
        if tag:
            results = [n for n in results if tag.lower() in [t.lower() for t in n["tags"]]]
        results.sort(key=lambda n: n["modified_at"], reverse=True)
        return {"status": "ok", "output": {"count": len(results), "results": results}}

    def get_note(self, path: str) -> Dict[str, Any]:
        idx = self._index_of(path)
        if idx < 0:
            return {"status": "failed", "output": f"Note {path} not found"}
        note = dict(self.notes[idx])
        note["content"] = self.contents.get(path, "")
        return {"status": "ok", "output": note}

    def create_note(self, path: str, content: str) -> Dict[str, Any]:
        if self._index_of(path) >= 0:
            return {"status": "failed", "output": f"Note {path} already exists"}
        title = Path(path).stem
        note = {
            "path": path,
            "title": title,
            "size_bytes": len(content.encode("utf-8")),
            "modified_at": self._now(),
            "tags": self._extract_tags(content),
        }
        self.notes.append(note)
        self.contents[path] = content
        return {"status": "ok", "output": {**note, "content": content}}

    def update_note(self, path: str, content: str | None = None, append: str | None = None) -> Dict[str, Any]:
        idx = self._index_of(path)
        if idx < 0:
            return {"status": "failed", "output": f"Note {path} not found"}
        if content is not None:
            self.contents[path] = content
        elif append is not None:
            self.contents[path] = self.contents.get(path, "") + append
        else:
            return {"status": "failed", "output": "Either content or append must be provided"}
        new_body = self.contents[path]
        self.notes[idx]["size_bytes"] = len(new_body.encode("utf-8"))
        self.notes[idx]["modified_at"] = self._now()
        self.notes[idx]["tags"] = self._extract_tags(new_body)
        return {"status": "ok", "output": {**self.notes[idx], "content": new_body}}

    def delete_note(self, path: str) -> Dict[str, Any]:
        idx = self._index_of(path)
        if idx < 0:
            return {"status": "failed", "output": f"Note {path} not found"}
        self.notes.pop(idx)
        self.contents.pop(path, None)
        return {"status": "ok", "output": {"deleted": True, "path": path}}

    # --- Search / links / daily -------------------------------------------
    def search(self, query: str, content: bool = False) -> Dict[str, Any]:
        q = query.lower()
        results = []
        for n in self.notes:
            body = self.contents.get(n["path"], "")
            title_hit = q in n["title"].lower()
            path_hit = q in n["path"].lower()
            body_hit = q in body.lower()
            if title_hit or path_hit or body_hit:
                entry = {**n, "match_in": []}
                if title_hit:
                    entry["match_in"].append("title")
                if path_hit:
                    entry["match_in"].append("path")
                if body_hit:
                    entry["match_in"].append("body")
                if content and body_hit:
                    for line in body.splitlines():
                        if q in line.lower():
                            entry["snippet"] = line.strip()
                            break
                results.append(entry)
        return {"status": "ok", "output": {"count": len(results), "query": query, "results": results}}

    def list_backlinks(self, path: str) -> Dict[str, Any]:
        target_title = Path(path).stem
        backlinks = []
        for n in self.notes:
            if n["path"] == path:
                continue
            body = self.contents.get(n["path"], "")
            for m in _WIKILINK.finditer(body):
                if m.group(1).strip() == target_title:
                    backlinks.append({"path": n["path"], "title": n["title"]})
                    break
        return {"status": "ok", "output": {"path": path, "count": len(backlinks), "backlinks": backlinks}}

    def get_daily(self, date_str: str) -> Dict[str, Any]:
        path = f"Daily/{date_str}.md"
        return self.get_note(path)


if __name__ == "__main__":
    s = ObsidianSession(seed=12)
    print(s.get_vault())
    print(s.list_notes())
