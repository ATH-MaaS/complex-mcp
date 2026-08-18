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


class MondaySession:
    """Deterministic sandbox for the monday.com mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "monday.yaml") as f:
                info = yaml.safe_load(f)

            self.workspaces: List[Dict[str, Any]] = list(info.get("workspaces", []))
            self.boards: List[Dict[str, Any]] = list(info.get("boards", []))
            self.groups: List[Dict[str, Any]] = [
                {**g, "position": int(g.get("position") or 0)} for g in info.get("groups", [])
            ]
            self.columns: List[Dict[str, Any]] = [
                {**c, "position": int(c.get("position") or 0)} for c in info.get("columns", [])
            ]
            self.items: List[Dict[str, Any]] = list(info.get("items", []))
            self.column_values: List[Dict[str, Any]] = [
                {
                    "item_id": cv["item_id"],
                    "column_id": cv["column_id"],
                    "text": cv["text"],
                    "value": (str(cv.get("value") or "") or None),
                }
                for cv in info.get("column_values", [])
            ]
            self.users: List[Dict[str, Any]] = [
                {**u, "is_admin": _to_bool(u.get("is_admin", False))} for u in info.get("users", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMonday')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"items": self.items, "column_values": self.column_values}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _find_board(self, board_id):
        return next((b for b in self.boards if b["board_id"] == board_id), None)

    def _find_item(self, item_id):
        return next((i for i in self.items if i["item_id"] == item_id), None)

    def _find_group(self, board_id, group_id):
        return next((g for g in self.groups if g["board_id"] == board_id and g["group_id"] == group_id), None)

    def _board_columns(self, board_id):
        cols = [c for c in self.columns if c["board_id"] == board_id]
        return sorted(cols, key=lambda c: c["position"])

    def _column_values_for(self, item_id):
        out = []
        for cv in self.column_values:
            if cv["item_id"] == item_id:
                out.append({"id": cv["column_id"], "text": cv["text"], "value": cv["value"]})
        return out

    def _item_view(self, item):
        return {
            "id": item["item_id"],
            "name": item["name"],
            "board_id": item["board_id"],
            "group": {"id": item["group_id"]},
            "created_at": item["created_at"],
            "column_values": self._column_values_for(item["item_id"]),
        }

    # --- API methods -------------------------------------------------------
    def list_workspaces(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"workspaces": [
            {"id": w["workspace_id"], "name": w["name"], "kind": w["kind"], "description": w["description"]}
            for w in self.workspaces
        ]}}

    def list_boards(self, workspace_id: str | None = None) -> Dict[str, Any]:
        boards = list(self.boards)
        if workspace_id:
            boards = [b for b in boards if b["workspace_id"] == workspace_id]
        return {"status": "ok", "output": {"boards": [
            {
                "id": b["board_id"], "name": b["name"], "description": b["description"],
                "state": b["state"], "board_kind": b["board_kind"], "workspace_id": b["workspace_id"],
            }
            for b in boards
        ]}}

    def get_board(self, board_id: str) -> Dict[str, Any]:
        b = self._find_board(board_id)
        if not b:
            return {"status": "failed", "output": f"Board {board_id} not found"}
        groups = sorted([g for g in self.groups if g["board_id"] == board_id], key=lambda g: g["position"])
        return {"status": "ok", "output": {
            "id": b["board_id"], "name": b["name"], "description": b["description"],
            "state": b["state"], "board_kind": b["board_kind"], "workspace_id": b["workspace_id"],
            "groups": [
                {"id": g["group_id"], "title": g["title"], "color": g["color"], "position": g["position"]}
                for g in groups
            ],
            "columns": [
                {"id": c["column_id"], "title": c["title"], "type": c["type"], "position": c["position"]}
                for c in self._board_columns(board_id)
            ],
        }}

    def get_board_items(self, board_id: str) -> Dict[str, Any]:
        if not self._find_board(board_id):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        items = [i for i in self.items if i["board_id"] == board_id]
        return {"status": "ok", "output": {"items": [self._item_view(i) for i in items]}}

    def list_items(self, board_id: str | None = None, group_id: str | None = None) -> Dict[str, Any]:
        items = list(self.items)
        if board_id:
            items = [i for i in items if i["board_id"] == board_id]
        if group_id:
            items = [i for i in items if i["group_id"] == group_id]
        return {"status": "ok", "output": {"items": [self._item_view(i) for i in items]}}

    def get_item(self, item_id: str) -> Dict[str, Any]:
        item = self._find_item(item_id)
        if not item:
            return {"status": "failed", "output": f"Item {item_id} not found"}
        return {"status": "ok", "output": self._item_view(item)}

    def create_item(self, board_id: str, name: str, group_id: str | None = None,
                    column_values: Dict[str, Any] | None = None) -> Dict[str, Any]:
        b = self._find_board(board_id)
        if not b:
            return {"status": "failed", "output": f"Board {board_id} not found"}
        if group_id:
            if not self._find_group(board_id, group_id):
                return {"status": "failed", "output": f"Group {group_id} not found on board {board_id}"}
        else:
            board_groups = sorted([g for g in self.groups if g["board_id"] == board_id], key=lambda g: g["position"])
            if not board_groups:
                return {"status": "failed", "output": f"Board {board_id} has no groups"}
            group_id = board_groups[0]["group_id"]

        item = {
            "item_id": f"item-{self.uuid()}",
            "board_id": board_id,
            "group_id": group_id,
            "name": name,
            "created_at": self._now(),
        }
        self.items.append(item)
        if column_values:
            for column_id, val in column_values.items():
                if isinstance(val, dict):
                    text = val.get("text", "")
                    value = val.get("value")
                else:
                    text = str(val)
                    value = None
                self.column_values.append({
                    "item_id": item["item_id"], "column_id": column_id, "text": text, "value": value,
                })
        return {"status": "ok", "output": self._item_view(item)}

    def update_item(self, item_id: str, column_id: str | None = None, text: str | None = None,
                    value: str | None = None, group_id: str | None = None) -> Dict[str, Any]:
        item = self._find_item(item_id)
        if not item:
            return {"status": "failed", "output": f"Item {item_id} not found"}
        if group_id is not None:
            if not self._find_group(item["board_id"], group_id):
                return {"status": "failed", "output": f"Group {group_id} not found on board {item['board_id']}"}
            item["group_id"] = group_id
        if column_id is not None:
            existing = next((cv for cv in self.column_values
                             if cv["item_id"] == item_id and cv["column_id"] == column_id), None)
            if existing:
                if text is not None:
                    existing["text"] = text
                if value is not None:
                    existing["value"] = value
            else:
                self.column_values.append({
                    "item_id": item_id, "column_id": column_id, "text": text or "", "value": value,
                })
        return {"status": "ok", "output": self._item_view(item)}

    def delete_item(self, item_id: str) -> Dict[str, Any]:
        item = self._find_item(item_id)
        if not item:
            return {"status": "failed", "output": f"Item {item_id} not found"}
        self.items[:] = [i for i in self.items if i["item_id"] != item_id]
        self.column_values[:] = [cv for cv in self.column_values if cv["item_id"] != item_id]
        return {"status": "ok", "output": {"id": item_id, "deleted": True}}

    def list_users(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"users": [
            {
                "id": u["user_id"], "name": u["name"], "email": u["email"],
                "title": u["title"], "is_admin": u["is_admin"],
            }
            for u in self.users
        ]}}


if __name__ == "__main__":
    s = MondaySession(seed=12)
    print(s.list_workspaces())
    print(s.list_boards())
