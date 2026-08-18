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


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# The member whose token is used (the "me" of /members/me).
_ME = "5f1a000000000000000000a1"


class TrelloSession:
    """Deterministic sandbox for the Trello mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "trello.yaml") as f:
                info = yaml.safe_load(f)

            self.members: List[Dict[str, Any]] = [dict(m) for m in info.get("members", [])]
            self.boards: List[Dict[str, Any]] = [
                {
                    **b,
                    "closed": _to_bool(b.get("closed", False)),
                    "member_ids": [x for x in str(b.get("member_ids", "") or "").split(";") if x],
                }
                for b in info.get("boards", [])
            ]
            self.lists: List[Dict[str, Any]] = [
                {
                    **l,
                    "pos": _to_float(l.get("pos")),
                    "closed": _to_bool(l.get("closed", False)),
                }
                for l in info.get("lists", [])
            ]
            self.cards: List[Dict[str, Any]] = [
                {
                    **c,
                    "pos": _to_float(c.get("pos")),
                    "closed": _to_bool(c.get("closed", False)),
                    "due": (str(c.get("due", "") or "") or None),
                    "member_ids": [x for x in str(c.get("member_ids", "") or "").split(";") if x],
                    "labels": [x for x in str(c.get("labels", "") or "").split(";") if x],
                }
                for c in info.get("cards", [])
            ]
            self.checklists: List[Dict[str, Any]] = [self._coerce_checklist(cl) for cl in info.get("checklists", [])]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTrello')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"cards": self.cards}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=24))

    def _coerce_checklist(self, r):
        items = []
        for n, raw in enumerate(str(r.get("items", "") or "").split(";")):
            if not raw:
                continue
            name, _, state = raw.partition(":")
            items.append({
                "id": f"ci{r['id'][-4:]}{n:02d}",
                "name": name,
                "state": state or "incomplete",
                "pos": (n + 1) * 16384,
            })
        return {
            "id": r["id"],
            "name": r["name"],
            "id_card": r["id_card"],
            "id_board": r["id_board"],
            "check_items": items,
        }

    def _serialize_board(self, b):
        return {
            "id": b["id"],
            "name": b["name"],
            "desc": b["desc"],
            "closed": b["closed"],
            "idOrganization": b["id_organization"],
            "url": b["url"],
            "idMembers": b["member_ids"],
        }

    def _serialize_list(self, l):
        return {
            "id": l["id"],
            "name": l["name"],
            "idBoard": l["id_board"],
            "pos": l["pos"],
            "closed": l["closed"],
        }

    def _serialize_card(self, c):
        return {
            "id": c["id"],
            "name": c["name"],
            "desc": c["desc"],
            "idBoard": c["id_board"],
            "idList": c["id_list"],
            "pos": c["pos"],
            "due": c["due"],
            "closed": c["closed"],
            "idMembers": c["member_ids"],
            "labels": [{"name": n} for n in c["labels"]],
        }

    def _serialize_checklist(self, cl):
        return {
            "id": cl["id"],
            "name": cl["name"],
            "idCard": cl["id_card"],
            "idBoard": cl["id_board"],
            "checkItems": cl["check_items"],
        }

    # --- Members -----------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        me = next((m for m in self.members if m["id"] == _ME), self.members[0])
        return {"status": "ok", "output": me}

    def list_my_boards(self) -> Dict[str, Any]:
        boards = [b for b in self.boards if _ME in b["member_ids"] and not b["closed"]]
        return {"status": "ok", "output": [self._serialize_board(b) for b in boards]}

    # --- Boards ------------------------------------------------------------
    def get_board(self, board_id: str) -> Dict[str, Any]:
        for b in self.boards:
            if b["id"] == board_id:
                return {"status": "ok", "output": self._serialize_board(b)}
        return {"status": "failed", "output": f"Board {board_id} not found"}

    def list_board_lists(self, board_id: str) -> Dict[str, Any]:
        if not any(b["id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        lists = [l for l in self.lists if l["id_board"] == board_id and not l["closed"]]
        lists = sorted(lists, key=lambda l: l["pos"])
        return {"status": "ok", "output": [self._serialize_list(l) for l in lists]}

    # --- Lists -> cards ----------------------------------------------------
    def list_cards(self, list_id: str) -> Dict[str, Any]:
        if not any(l["id"] == list_id for l in self.lists):
            return {"status": "failed", "output": f"List {list_id} not found"}
        cards = [c for c in self.cards if c["id_list"] == list_id and not c["closed"]]
        cards = sorted(cards, key=lambda c: c["pos"])
        return {"status": "ok", "output": [self._serialize_card(c) for c in cards]}

    # --- Cards -------------------------------------------------------------
    def get_card(self, card_id: str) -> Dict[str, Any]:
        for c in self.cards:
            if c["id"] == card_id:
                return {"status": "ok", "output": self._serialize_card(c)}
        return {"status": "failed", "output": f"Card {card_id} not found"}

    def create_card(self, id_list: str, name: str, desc: str = "", due: str | None = None,
                    member_ids: List[str] | None = None) -> Dict[str, Any]:
        target = next((l for l in self.lists if l["id"] == id_list), None)
        if not target:
            return {"status": "failed", "output": f"List {id_list} not found"}
        siblings = [c for c in self.cards if c["id_list"] == id_list and not c["closed"]]
        next_pos = max((c["pos"] for c in siblings), default=0) + 16384
        card = {
            "id": self.uuid(),
            "name": name,
            "desc": desc or "",
            "id_board": target["id_board"],
            "id_list": id_list,
            "pos": next_pos,
            "due": due,
            "closed": False,
            "member_ids": member_ids or [],
            "labels": [],
        }
        self.cards.append(card)
        return {"status": "ok", "output": self._serialize_card(card)}

    def update_card(self, card_id: str, name: str | None = None, desc: str | None = None,
                    id_list: str | None = None, due: str | None = None,
                    closed: bool | None = None, pos: float | None = None) -> Dict[str, Any]:
        for i, c in enumerate(self.cards):
            if c["id"] == card_id:
                if name is not None:
                    self.cards[i]["name"] = name
                if desc is not None:
                    self.cards[i]["desc"] = desc
                if id_list is not None:
                    target = next((l for l in self.lists if l["id"] == id_list), None)
                    if not target:
                        return {"status": "failed", "output": f"List {id_list} not found"}
                    self.cards[i]["id_list"] = id_list
                    self.cards[i]["id_board"] = target["id_board"]
                if due is not None:
                    self.cards[i]["due"] = due or None
                if closed is not None:
                    self.cards[i]["closed"] = bool(closed)
                if pos is not None:
                    self.cards[i]["pos"] = float(pos)
                return {"status": "ok", "output": self._serialize_card(self.cards[i])}
        return {"status": "failed", "output": f"Card {card_id} not found"}

    def delete_card(self, card_id: str) -> Dict[str, Any]:
        for i, c in enumerate(self.cards):
            if c["id"] == card_id:
                self.cards.pop(i)
                self.checklists[:] = [cl for cl in self.checklists if cl["id_card"] != card_id]
                return {"status": "ok", "output": {"_value": None, "deleted": True, "id": card_id}}
        return {"status": "failed", "output": f"Card {card_id} not found"}

    # --- Checklists --------------------------------------------------------
    def list_card_checklists(self, card_id: str) -> Dict[str, Any]:
        if not any(c["id"] == card_id for c in self.cards):
            return {"status": "failed", "output": f"Card {card_id} not found"}
        return {"status": "ok", "output": [
            self._serialize_checklist(cl) for cl in self.checklists if cl["id_card"] == card_id
        ]}

    def create_checklist(self, id_card: str, name: str = "Checklist") -> Dict[str, Any]:
        card = next((c for c in self.cards if c["id"] == id_card), None)
        if not card:
            return {"status": "failed", "output": f"Card {id_card} not found"}
        checklist = {
            "id": self.uuid(),
            "name": name or "Checklist",
            "id_card": id_card,
            "id_board": card["id_board"],
            "check_items": [],
        }
        self.checklists.append(checklist)
        return {"status": "ok", "output": self._serialize_checklist(checklist)}


if __name__ == "__main__":
    s = TrelloSession(seed=12)
    print(s.get_me())
    print(s.list_my_boards())
