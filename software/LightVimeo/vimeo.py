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


def _opt_csv_list(v, sep=";") -> List[str]:
    if v is None or str(v).strip() == "":
        return []
    return [part for part in str(v).split(sep)]


def _strict_int(v) -> int:
    return int(str(v).strip())


class VimeoSession:
    """Deterministic sandbox for the Vimeo mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read the in-memory
    tables. Mirrors a subset of the Vimeo API (api.vimeo.com): the authenticated
    user (/me), their videos, individual videos, other users, and a user's videos.
    List endpoints use Vimeo's paged envelope.
    """

    # The user whose token is in use (the "me" of /me).
    _ME = "12000001"

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "vimeo.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = [
                {
                    "id": u["id"],
                    "name": u["name"],
                    "link": u["link"],
                    "location": u["location"],
                    "bio": u["bio"],
                    "account": u["account"],
                    "created_time": u["created_time"],
                    "websites": [x for x in _opt_csv_list(u.get("websites"), sep=";") if x],
                }
                for u in info.get("users", [])
            ]
            self.videos: List[Dict[str, Any]] = [
                {
                    "id": v["id"],
                    "user_id": v["user_id"],
                    "name": v["name"],
                    "description": v["description"],
                    "duration": _strict_int(v["duration"]),
                    "width": _strict_int(v["width"]),
                    "height": _strict_int(v["height"]),
                    "privacy": v["privacy"],
                    "status": v["status"],
                    "plays": _strict_int(v["plays"]),
                    "likes": _strict_int(v["likes"]),
                    "created_time": v["created_time"],
                    "modified_time": v["modified_time"],
                    "link": v["link"],
                }
                for v in info.get("videos", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightVimeo')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"users": self.users, "videos": self.videos}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _serialize_user(self, u):
        return {
            "uri": f"/users/{u['id']}",
            "name": u["name"],
            "link": u["link"],
            "location": u["location"],
            "bio": u["bio"],
            "account": u["account"],
            "created_time": u["created_time"],
            "websites": [{"uri": "", "link": w} for w in u["websites"]],
            "metadata": {
                "connections": {
                    "videos": {
                        "uri": f"/users/{u['id']}/videos",
                        "total": sum(1 for v in self.videos if v["user_id"] == u["id"]),
                    }
                }
            },
        }

    def _serialize_video(self, v):
        owner = next((u for u in self.users if u["id"] == v["user_id"]), None)
        return {
            "uri": f"/videos/{v['id']}",
            "name": v["name"],
            "description": v["description"],
            "link": v["link"],
            "duration": v["duration"],
            "width": v["width"],
            "height": v["height"],
            "created_time": v["created_time"],
            "modified_time": v["modified_time"],
            "privacy": {"view": v["privacy"]},
            "status": v["status"],
            "stats": {"plays": v["plays"]},
            "metadata": {"connections": {"likes": {"total": v["likes"]}}},
            "user": {
                "uri": f"/users/{owner['id']}",
                "name": owner["name"],
                "link": owner["link"],
            } if owner else None,
        }

    def _paged(self, items, page=1, per_page=25):
        return {
            "total": len(items),
            "page": page,
            "per_page": per_page,
            "paging": {"next": None, "previous": None, "first": "?page=1", "last": "?page=1"},
            "data": items,
        }

    # --- API methods -------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        me = next((u for u in self.users if u["id"] == self._ME), self.users[0])
        return {"status": "ok", "output": self._serialize_user(me)}

    def get_my_videos(self, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        videos = [v for v in self.videos if v["user_id"] == self._ME]
        videos = sorted(videos, key=lambda v: v["created_time"], reverse=True)
        paged = self._paged([self._serialize_video(v) for v in videos], page=page, per_page=per_page)
        return {"status": "ok", "output": paged}

    def get_video(self, video_id: str) -> Dict[str, Any]:
        v = next((x for x in self.videos if x["id"] == str(video_id)), None)
        if not v:
            return {"status": "failed", "output": "The requested video could not be found."}
        return {"status": "ok", "output": self._serialize_video(v)}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        u = next((x for x in self.users if x["id"] == str(user_id)), None)
        if not u:
            return {"status": "failed", "output": "The requested user could not be found."}
        return {"status": "ok", "output": self._serialize_user(u)}

    def get_user_videos(self, user_id: str, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        if not any(u["id"] == str(user_id) for u in self.users):
            return {"status": "failed", "output": "The requested user could not be found."}
        videos = [v for v in self.videos if v["user_id"] == str(user_id)]
        videos = sorted(videos, key=lambda v: v["created_time"], reverse=True)
        paged = self._paged([self._serialize_video(v) for v in videos], page=page, per_page=per_page)
        return {"status": "ok", "output": paged}


if __name__ == "__main__":
    s = VimeoSession(seed=12)
    print(s.get_me())
    print(s.get_my_videos())
