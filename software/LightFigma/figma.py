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


class FigmaSession:
    """Deterministic sandbox for the Figma mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "figma.yaml") as f:
                info = yaml.safe_load(f)

            self.projects: List[Dict[str, Any]] = list(info.get("projects", []))
            self.files: List[Dict[str, Any]] = list(info.get("files", []))
            self.components: List[Dict[str, Any]] = list(info.get("components", []))
            self.comments: List[Dict[str, Any]] = [
                {**c, "resolved": _to_bool(c.get("resolved", False))} for c in info.get("comments", [])
            ]
            self.team: Dict[str, Any] = info.get("team", {})
            self.file_nodes: Dict[str, Any] = info.get("file_nodes", {})
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightFigma')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"comments": self.comments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _find_file(self, file_key):
        return next((f for f in self.files if f["file_key"] == file_key), None)

    def _iter_nodes(self, node):
        yield node
        for child in node.get("children", []):
            yield from self._iter_nodes(child)

    def _user(self, user_id):
        return next((u for u in self.team["users"] if u["id"] == user_id), None)

    def _comment_view(self, c):
        user = self._user(c["user_id"]) or {"id": c["user_id"], "handle": c["user_handle"]}
        return {
            "id": c["comment_id"],
            "file_key": c["file_key"],
            "message": c["message"],
            "client_meta": {"node_id": c["node_id"]},
            "user": {"id": user["id"], "handle": user["handle"], "img_url": user.get("img_url")},
            "resolved_at": c.get("created_at") if c["resolved"] else None,
            "created_at": c["created_at"],
        }

    # --- API methods -------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.team["me"]}

    def get_team_projects(self, team_id: str) -> Dict[str, Any]:
        if team_id != self.team["team"]["id"]:
            return {"status": "failed", "output": f"Team {team_id} not found"}
        return {"status": "ok", "output": {
            "name": self.team["team"]["name"],
            "projects": [
                {"id": p["project_id"], "name": p["name"]}
                for p in self.projects if p["team_id"] == team_id
            ],
        }}

    def get_project_files(self, project_id: str) -> Dict[str, Any]:
        if not any(p["project_id"] == project_id for p in self.projects):
            return {"status": "failed", "output": f"Project {project_id} not found"}
        files = [f for f in self.files if f["project_id"] == project_id]
        return {"status": "ok", "output": {
            "name": next(p["name"] for p in self.projects if p["project_id"] == project_id),
            "files": [
                {
                    "key": f["file_key"],
                    "name": f["name"],
                    "thumbnail_url": f["thumbnail_url"],
                    "last_modified": f["last_modified"],
                }
                for f in files
            ],
        }}

    def get_file(self, file_key: str) -> Dict[str, Any]:
        f = self._find_file(file_key)
        if not f:
            return {"status": "failed", "output": f"File {file_key} not found"}
        return {"status": "ok", "output": {
            "name": f["name"],
            "role": f["role"],
            "lastModified": f["last_modified"],
            "editorType": f["editor_type"],
            "thumbnailUrl": f["thumbnail_url"],
            "version": f["version"],
            "document": self.file_nodes.get(file_key, {"id": "0:0", "name": "Document", "type": "DOCUMENT", "children": []}),
            "components": {
                c["node_id"]: {"key": c["component_key"], "name": c["name"], "description": c["description"]}
                for c in self.components if c["file_key"] == file_key
            },
        }}

    def get_file_nodes(self, file_key: str, ids: str) -> Dict[str, Any]:
        f = self._find_file(file_key)
        if not f:
            return {"status": "failed", "output": f"File {file_key} not found"}
        root = self.file_nodes.get(file_key)
        wanted = [i.strip() for i in (ids or "").split(",") if i.strip()]
        nodes = {}
        if root:
            index = {n["id"]: n for n in self._iter_nodes(root)}
            for nid in wanted:
                if nid in index:
                    nodes[nid] = {"document": index[nid]}
                else:
                    nodes[nid] = None
        return {"status": "ok", "output": {
            "name": f["name"],
            "lastModified": f["last_modified"],
            "version": f["version"],
            "nodes": nodes,
        }}

    def get_comments(self, file_key: str) -> Dict[str, Any]:
        f = self._find_file(file_key)
        if not f:
            return {"status": "failed", "output": f"File {file_key} not found"}
        comments = [self._comment_view(c) for c in self.comments if c["file_key"] == file_key]
        return {"status": "ok", "output": {"comments": comments}}

    def create_comment(self, file_key: str, message: str, node_id: str | None = None,
                       user_id: str = "user-1001") -> Dict[str, Any]:
        f = self._find_file(file_key)
        if not f:
            return {"status": "failed", "output": f"File {file_key} not found"}
        user = self._user(user_id) or self.team["me"]
        comment = {
            "comment_id": f"cmt-{self.uuid()}",
            "file_key": file_key,
            "user_id": user["id"],
            "user_handle": user["handle"],
            "message": message,
            "node_id": node_id or "",
            "resolved": False,
            "created_at": self._now(),
        }
        self.comments.append(comment)
        return {"status": "ok", "output": self._comment_view(comment)}

    def get_components(self, file_key: str) -> Dict[str, Any]:
        f = self._find_file(file_key)
        if not f:
            return {"status": "failed", "output": f"File {file_key} not found"}
        comps = [c for c in self.components if c["file_key"] == file_key]
        return {"status": "ok", "output": {
            "meta": {
                "components": [
                    {
                        "key": c["component_key"],
                        "file_key": c["file_key"],
                        "node_id": c["node_id"],
                        "name": c["name"],
                        "description": c["description"],
                    }
                    for c in comps
                ]
            }
        }}


if __name__ == "__main__":
    s = FigmaSession(seed=12)
    print(s.get_me())
    print(s.get_team_projects("team-501"))
