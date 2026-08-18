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


def _strict_int(v) -> int:
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def _opt_str(v):
    s = "" if v is None else str(v)
    return s or None


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


class PinterestSession:
    """Deterministic sandbox for the Pinterest API v5 mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "pinterest.yaml") as f:
                info = yaml.safe_load(f)

            self.boards: List[Dict[str, Any]] = [
                {
                    **b,
                    "board_id": b["board_id"],
                    "pin_count": _strict_int(b.get("pin_count")),
                    "follower_count": _strict_int(b.get("follower_count")),
                    "collaborator_count": _strict_int(b.get("collaborator_count")),
                }
                for b in info.get("boards", [])
            ]
            self.board_sections: List[Dict[str, Any]] = [
                {
                    **s,
                    "section_id": s["section_id"],
                    "board_id": s["board_id"],
                    "pin_count": _strict_int(s.get("pin_count")),
                }
                for s in info.get("board_sections", [])
            ]
            self.pins: List[Dict[str, Any]] = [
                {
                    **p,
                    "pin_id": p["pin_id"],
                    "board_id": p["board_id"],
                    "board_section_id": _opt_str(p.get("board_section_id", "")),
                    "link": _opt_str(p.get("link", "")),
                    "alt_text": _opt_str(p.get("alt_text", "")),
                    "is_promoted": _to_bool(p.get("is_promoted", False)),
                    "pin_metrics_impressions": _strict_int(p.get("pin_metrics_impressions")),
                    "pin_metrics_saves": _strict_int(p.get("pin_metrics_saves")),
                    "pin_metrics_clicks": _strict_int(p.get("pin_metrics_clicks")),
                }
                for p in info.get("pins", [])
            ]
            self.pin_analytics: List[Dict[str, Any]] = [
                {
                    "pin_id": r["pin_id"],
                    "date": r["date"],
                    "impressions": _strict_int(r.get("impressions")),
                    "saves": _strict_int(r.get("saves")),
                    "pin_clicks": _strict_int(r.get("pin_clicks")),
                    "outbound_clicks": _strict_int(r.get("outbound_clicks")),
                }
                for r in info.get("pin_analytics", [])
            ]
            self.user_analytics: List[Dict[str, Any]] = [
                {
                    "date": r["date"],
                    "impressions": _strict_int(r.get("impressions")),
                    "saves": _strict_int(r.get("saves")),
                    "pin_clicks": _strict_int(r.get("pin_clicks")),
                    "outbound_clicks": _strict_int(r.get("outbound_clicks")),
                    "profile_visits": _strict_int(r.get("profile_visits")),
                    "follows": _strict_int(r.get("follows")),
                }
                for r in info.get("user_analytics", [])
            ]
            self.ad_accounts: List[Dict[str, Any]] = [
                {**a, "ad_account_id": a["ad_account_id"]} for a in info.get("ad_accounts", [])
            ]
            self.campaigns: List[Dict[str, Any]] = [
                {
                    **c,
                    "campaign_id": c["campaign_id"],
                    "ad_account_id": c["ad_account_id"],
                    "daily_spend_cap_micro": _strict_int(c.get("daily_spend_cap_micro")),
                    "lifetime_spend_cap_micro": _strict_int(c.get("lifetime_spend_cap_micro")),
                    "end_time": _opt_str(c.get("end_time", "")),
                }
                for c in info.get("campaigns", [])
            ]
            self.user_account_raw = info.get("user_account", [])

            self._next_board_id = max(
                (self._extract_numeric_id(b["board_id"], "board_") for b in self.boards), default=0
            ) + 1
            self._next_section_id = max(
                (self._extract_numeric_id(s["section_id"], "section_") for s in self.board_sections), default=0
            ) + 1
            self._next_pin_id = max(
                (self._extract_numeric_id(p["pin_id"], "pin_") for p in self.pins), default=0
            ) + 1
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPinterest')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"boards": self.boards, "pins": self.pins, "board_sections": self.board_sections}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    @staticmethod
    def _extract_numeric_id(id_str, prefix) -> int:
        stripped = id_str.replace(prefix, "", 1)
        try:
            return int(stripped)
        except (ValueError, TypeError):
            return 0

    # --- User Account ------------------------------------------------------
    def get_user_account(self) -> Dict[str, Any]:
        raw = self.user_account_raw
        account = raw[0] if isinstance(raw, list) else raw
        return {"status": "ok", "output": {"type": "user_account", "user_account": account}}

    def get_user_analytics(self, start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
        results = list(self.user_analytics)
        if start_date:
            results = [r for r in results if r["date"] >= start_date]
        if end_date:
            results = [r for r in results if r["date"] <= end_date]
        results = sorted(results, key=lambda x: x["date"])
        return {"status": "ok", "output": {
            "type": "user_analytics",
            "count": len(results),
            "results": results,
        }}

    # --- Boards ------------------------------------------------------------
    def list_boards(self, privacy: str | None = None, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.boards)
        if privacy:
            results = [b for b in results if b["privacy"].upper() == privacy.upper()]
        results = sorted(results, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "boards",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_board(self, board_id: str) -> Dict[str, Any]:
        for b in self.boards:
            if b["board_id"] == board_id:
                return {"status": "ok", "output": {"type": "board", "board": b}}
        return {"status": "failed", "output": f"Board {board_id} not found"}

    def create_board(self, name: str, description: str | None = None, privacy: str | None = None) -> Dict[str, Any]:
        if name is None:
            return {"status": "failed", "output": "Missing required field: name"}
        now = self._now()
        board = {
            "board_id": f"board_{self._next_board_id}",
            "name": name,
            "description": description if description is not None else "",
            "privacy": privacy if privacy is not None else "PUBLIC",
            "created_at": now,
            "updated_at": now,
            "pin_count": 0,
            "follower_count": 0,
            "collaborator_count": 0,
        }
        self.boards.append(board)
        self._next_board_id += 1
        return {"status": "ok", "output": {"type": "board", "board": board}}

    def update_board(self, board_id: str, name: str | None = None, description: str | None = None,
                     privacy: str | None = None) -> Dict[str, Any]:
        data = {k: v for k, v in {"name": name, "description": description, "privacy": privacy}.items() if v is not None}
        for i, board in enumerate(self.boards):
            if board["board_id"] == board_id:
                updatable = {"name", "description", "privacy"}
                for k, v in data.items():
                    if k in updatable:
                        self.boards[i][k] = v
                self.boards[i]["updated_at"] = self._now()
                return {"status": "ok", "output": {"type": "board", "board": self.boards[i]}}
        return {"status": "failed", "output": f"Board {board_id} not found"}

    def delete_board(self, board_id: str) -> Dict[str, Any]:
        for i, board in enumerate(self.boards):
            if board["board_id"] == board_id:
                self.boards.pop(i)
                return {"status": "ok", "output": {"type": "board", "deleted": True, "board_id": board_id}}
        return {"status": "failed", "output": f"Board {board_id} not found"}

    def list_board_pins(self, board_id: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if not any(b["board_id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        results = [p for p in self.pins if p["board_id"] == board_id]
        results = sorted(results, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "pins",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    # --- Board Sections ----------------------------------------------------
    def list_board_sections(self, board_id: str) -> Dict[str, Any]:
        if not any(b["board_id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        sections = [s for s in self.board_sections if s["board_id"] == board_id]
        return {"status": "ok", "output": {"type": "board_sections", "count": len(sections), "results": sections}}

    def create_board_section(self, board_id: str, name: str) -> Dict[str, Any]:
        if not any(b["board_id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        if not name:
            return {"status": "failed", "output": "Missing required field: name"}
        section = {
            "section_id": f"section_{self._next_section_id}",
            "board_id": board_id,
            "name": name,
            "pin_count": 0,
        }
        self.board_sections.append(section)
        self._next_section_id += 1
        return {"status": "ok", "output": {"type": "board_section", "board_section": section}}

    def list_section_pins(self, board_id: str, section_id: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if not any(b["board_id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        if not any(s["section_id"] == section_id and s["board_id"] == board_id for s in self.board_sections):
            return {"status": "failed", "output": f"Section {section_id} not found in board {board_id}"}
        results = [p for p in self.pins if p["board_section_id"] == section_id]
        results = sorted(results, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "pins",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    # --- Pins --------------------------------------------------------------
    def list_pins(self, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = sorted(self.pins, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "pins",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_pin(self, pin_id: str) -> Dict[str, Any]:
        for p in self.pins:
            if p["pin_id"] == pin_id:
                return {"status": "ok", "output": {"type": "pin", "pin": p}}
        return {"status": "failed", "output": f"Pin {pin_id} not found"}

    def create_pin(self, board_id: str, title: str, description: str | None = None, link: str | None = None,
                   media_type: str | None = None, board_section_id: str | None = None,
                   dominant_color: str | None = None, alt_text: str | None = None) -> Dict[str, Any]:
        if board_id is None:
            return {"status": "failed", "output": "Missing required field: board_id"}
        if title is None:
            return {"status": "failed", "output": "Missing required field: title"}
        if not any(b["board_id"] == board_id for b in self.boards):
            return {"status": "failed", "output": f"Board {board_id} not found"}
        now = self._now()
        pin = {
            "pin_id": f"pin_{self._next_pin_id}",
            "board_id": board_id,
            "board_section_id": board_section_id,
            "title": title,
            "description": description if description is not None else "",
            "link": link,
            "media_type": media_type if media_type is not None else "image",
            "created_at": now,
            "updated_at": now,
            "dominant_color": dominant_color if dominant_color is not None else "#FFFFFF",
            "alt_text": alt_text,
            "is_promoted": False,
            "pin_metrics_impressions": 0,
            "pin_metrics_saves": 0,
            "pin_metrics_clicks": 0,
        }
        self.pins.append(pin)
        self._next_pin_id += 1
        return {"status": "ok", "output": {"type": "pin", "pin": pin}}

    def update_pin(self, pin_id: str, title: str | None = None, description: str | None = None,
                   link: str | None = None, board_id: str | None = None,
                   board_section_id: str | None = None, alt_text: str | None = None) -> Dict[str, Any]:
        data = {k: v for k, v in {
            "title": title, "description": description, "link": link,
            "board_id": board_id, "board_section_id": board_section_id, "alt_text": alt_text,
        }.items() if v is not None}
        for i, pin in enumerate(self.pins):
            if pin["pin_id"] == pin_id:
                updatable = {"title", "description", "link", "board_id", "board_section_id", "alt_text"}
                for k, v in data.items():
                    if k in updatable:
                        self.pins[i][k] = v
                self.pins[i]["updated_at"] = self._now()
                return {"status": "ok", "output": {"type": "pin", "pin": self.pins[i]}}
        return {"status": "failed", "output": f"Pin {pin_id} not found"}

    def delete_pin(self, pin_id: str) -> Dict[str, Any]:
        for i, pin in enumerate(self.pins):
            if pin["pin_id"] == pin_id:
                self.pins.pop(i)
                return {"status": "ok", "output": {"type": "pin", "deleted": True, "pin_id": pin_id}}
        return {"status": "failed", "output": f"Pin {pin_id} not found"}

    def get_pin_analytics(self, pin_id: str, start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
        if not any(p["pin_id"] == pin_id for p in self.pins):
            return {"status": "failed", "output": f"Pin {pin_id} not found"}
        results = [a for a in self.pin_analytics if a["pin_id"] == pin_id]
        if start_date:
            results = [r for r in results if r["date"] >= start_date]
        if end_date:
            results = [r for r in results if r["date"] <= end_date]
        results = sorted(results, key=lambda x: x["date"])
        return {"status": "ok", "output": {
            "type": "pin_analytics",
            "count": len(results),
            "pin_id": pin_id,
            "results": results,
        }}

    def search_pins(self, query: str, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        q_lower = query.lower()
        results = [
            p for p in self.pins
            if q_lower in p.get("title", "").lower()
            or q_lower in p.get("description", "").lower()
        ]
        results = sorted(results, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "pins",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    # --- Media -------------------------------------------------------------
    def get_media_upload_status(self, media_id: str) -> Dict[str, Any]:
        if any(p["pin_id"] == media_id for p in self.pins):
            return {"status": "ok", "output": {
                "type": "media_upload",
                "media_id": media_id,
                "status": "succeeded",
                "media_type": "image",
            }}
        return {"status": "failed", "output": f"Media {media_id} not found"}

    # --- Ad Accounts -------------------------------------------------------
    def list_ad_accounts(self, limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        results = list(self.ad_accounts)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "ad_accounts",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_ad_account(self, ad_account_id: str) -> Dict[str, Any]:
        for a in self.ad_accounts:
            if a["ad_account_id"] == ad_account_id:
                return {"status": "ok", "output": {"type": "ad_account", "ad_account": a}}
        return {"status": "failed", "output": f"Ad account {ad_account_id} not found"}

    def list_campaigns(self, ad_account_id: str, status: str | None = None,
                       limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        if not any(a["ad_account_id"] == ad_account_id for a in self.ad_accounts):
            return {"status": "failed", "output": f"Ad account {ad_account_id} not found"}
        results = [c for c in self.campaigns if c["ad_account_id"] == ad_account_id]
        if status:
            results = [c for c in results if c["status"].upper() == status.upper()]
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "campaigns",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}


if __name__ == "__main__":
    s = PinterestSession(seed=12)
    print(s.list_boards())
    print(s.get_user_account())
