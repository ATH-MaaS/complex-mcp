import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import time
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


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class SlackSession:
    """Deterministic sandbox for the Slack Web API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "slack.yaml") as f:
                info = yaml.safe_load(f)

            self.users: List[Dict[str, Any]] = [
                {
                    **u,
                    "is_admin": _to_bool(u.get("is_admin", False)),
                    "is_bot": _to_bool(u.get("is_bot", False)),
                }
                for u in info.get("users", [])
            ]
            self.channels: List[Dict[str, Any]] = [
                {
                    **c,
                    "is_private": _to_bool(c.get("is_private", False)),
                    "is_archived": _to_bool(c.get("is_archived", False)),
                    "created": _to_int(c.get("created", 0)),
                    "num_members": _to_int(c.get("num_members", 0)),
                }
                for c in info.get("channels", [])
            ]
            self.messages: List[Dict[str, Any]] = [
                {
                    **m,
                    "thread_ts": (str(m.get("thread_ts") or "") or None),
                    "reply_count": _to_int(m.get("reply_count", 0)),
                    "reactions": self._parse_reactions(str(m.get("reactions") or "")),
                }
                for m in info.get("messages", [])
            ]
            self.channel_members: List[Dict[str, Any]] = list(info.get("channel_members", []))
            self.team: Dict[str, Any] = info.get("team", {})
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSlack')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"messages": self.messages, "channels": self.channels}

    # --- helpers -----------------------------------------------------------
    def uuid(self) -> str:
        alphabet = "0123456789ABCDEF"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _next_ts(self) -> str:
        return f"{time.time():.6f}"

    @staticmethod
    def _parse_reactions(s):
        if not s:
            return []
        result = []
        for chunk in s.split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ":" in chunk:
                name, users = chunk.split(":", 1)
                user_list = [u.strip() for u in users.split(",") if u.strip()]
                result.append({"name": name, "users": user_list, "count": len(user_list)})
        return result

    # --- auth / team -------------------------------------------------------
    def auth_test(self) -> Dict[str, Any]:
        admin = next((u for u in self.users if u["is_admin"]), self.users[0])
        return {"status": "ok", "output": {
            "url": f"https://{self.team['domain']}.slack.com/",
            "team": self.team["name"],
            "user": admin["name"],
            "team_id": self.team["id"],
            "user_id": admin["id"],
        }}

    def team_info(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"team": self.team}}

    # --- users -------------------------------------------------------------
    def users_list(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"members": self.users}}

    def users_info(self, user: str) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == user:
                return {"status": "ok", "output": {"user": u}}
        return {"status": "failed", "output": "user_not_found"}

    def users_set_presence(self, user: str, presence: str) -> Dict[str, Any]:
        for u in self.users:
            if u["id"] == user:
                u["presence"] = "away" if presence == "away" else "auto"
                return {"status": "ok", "output": {"presence": u["presence"]}}
        return {"status": "failed", "output": "user_not_found"}

    # --- conversations -----------------------------------------------------
    def conversations_list(self, types: str = "public_channel,private_channel",
                           exclude_archived: bool = True) -> Dict[str, Any]:
        type_set = {t.strip() for t in types.split(",")}
        results = []
        for c in self.channels:
            if exclude_archived and c["is_archived"]:
                continue
            if c["is_private"] and "private_channel" not in type_set:
                continue
            if not c["is_private"] and "public_channel" not in type_set:
                continue
            results.append(c)
        return {"status": "ok", "output": {"channels": results}}

    def conversations_info(self, channel: str) -> Dict[str, Any]:
        for c in self.channels:
            if c["id"] == channel:
                return {"status": "ok", "output": {"channel": c}}
        return {"status": "failed", "output": "channel_not_found"}

    def conversations_create(self, name: str, is_private: bool = False,
                             user_id: str = "U01AMELIA") -> Dict[str, Any]:
        if any(c["name"] == name for c in self.channels):
            return {"status": "failed", "output": "name_taken"}
        channel = {
            "id": ("G" if is_private else "C") + "01" + self.uuid(),
            "name": name,
            "is_private": bool(is_private),
            "is_archived": False,
            "topic": "",
            "purpose": "",
            "creator": user_id,
            "created": int(time.time()),
            "num_members": 1,
        }
        self.channels.append(channel)
        self.channel_members.append({"channel_id": channel["id"], "user_id": user_id})
        return {"status": "ok", "output": {"channel": channel}}

    def conversations_archive(self, channel: str) -> Dict[str, Any]:
        for c in self.channels:
            if c["id"] == channel:
                c["is_archived"] = True
                return {"status": "ok", "output": {}}
        return {"status": "failed", "output": "channel_not_found"}

    def conversations_members(self, channel: str) -> Dict[str, Any]:
        members = [m["user_id"] for m in self.channel_members if m["channel_id"] == channel]
        if not members and not any(c["id"] == channel for c in self.channels):
            return {"status": "failed", "output": "channel_not_found"}
        return {"status": "ok", "output": {"members": members}}

    def conversations_invite(self, channel: str, users: str) -> Dict[str, Any]:
        results = []
        last = None
        for u in [s.strip() for s in users.split(",") if s.strip()]:
            last = self._invite_one(channel, u)
            results.append({"user": u, "ok": last.get("ok", False), "error": last.get("error")})
        return {"status": "ok", "output": {
            "ok": all(r["ok"] for r in results),
            "results": results,
            "channel": last and last.get("channel"),
        }}

    def _invite_one(self, channel_id, user_id):
        if not any(c["id"] == channel_id for c in self.channels):
            return {"ok": False, "error": "channel_not_found"}
        if not any(u["id"] == user_id for u in self.users):
            return {"ok": False, "error": "user_not_found"}
        if any(m["channel_id"] == channel_id and m["user_id"] == user_id for m in self.channel_members):
            return {"ok": False, "error": "already_in_channel"}
        self.channel_members.append({"channel_id": channel_id, "user_id": user_id})
        for c in self.channels:
            if c["id"] == channel_id:
                c["num_members"] += 1
        return {"ok": True, "error": None, "channel": next(c for c in self.channels if c["id"] == channel_id)}

    def conversations_history(self, channel: str, limit: int = 20, oldest: str | None = None,
                              latest: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == channel for c in self.channels):
            return {"status": "failed", "output": "channel_not_found"}
        msgs = [m for m in self.messages if m["channel_id"] == channel and m["thread_ts"] is None]
        if oldest:
            msgs = [m for m in msgs if float(m["ts"]) >= float(oldest)]
        if latest:
            msgs = [m for m in msgs if float(m["ts"]) <= float(latest)]
        msgs.sort(key=lambda m: float(m["ts"]), reverse=True)
        return {"status": "ok", "output": {"messages": msgs[:limit], "has_more": len(msgs) > limit}}

    def conversations_replies(self, channel: str, ts: str) -> Dict[str, Any]:
        parent = next((m for m in self.messages
                       if m["channel_id"] == channel and m["ts"] == ts), None)
        if not parent:
            return {"status": "failed", "output": "thread_not_found"}
        replies = [m for m in self.messages
                   if m["channel_id"] == channel and m["thread_ts"] == ts]
        replies.sort(key=lambda m: float(m["ts"]))
        return {"status": "ok", "output": {"messages": [parent] + replies}}

    # --- chat --------------------------------------------------------------
    def chat_post_message(self, channel: str, text: str, user: str = "U01AMELIA",
                          thread_ts: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == channel for c in self.channels):
            return {"status": "failed", "output": "channel_not_found"}
        ts = self._next_ts()
        msg = {
            "ts": ts,
            "channel_id": channel,
            "user_id": user,
            "text": text,
            "thread_ts": thread_ts,
            "reply_count": 0,
            "reactions": [],
        }
        self.messages.append(msg)
        if thread_ts:
            for m in self.messages:
                if m["channel_id"] == channel and m["ts"] == thread_ts:
                    m["reply_count"] += 1
        return {"status": "ok", "output": {"channel": channel, "ts": ts, "message": msg}}

    def chat_update(self, channel: str, ts: str, text: str) -> Dict[str, Any]:
        for m in self.messages:
            if m["channel_id"] == channel and m["ts"] == ts:
                m["text"] = text
                return {"status": "ok", "output": {"channel": channel, "ts": ts, "text": text}}
        return {"status": "failed", "output": "message_not_found"}

    def chat_delete(self, channel: str, ts: str) -> Dict[str, Any]:
        for i, m in enumerate(self.messages):
            if m["channel_id"] == channel and m["ts"] == ts:
                self.messages.pop(i)
                return {"status": "ok", "output": {"channel": channel, "ts": ts}}
        return {"status": "failed", "output": "message_not_found"}

    # --- reactions ---------------------------------------------------------
    def reactions_add(self, channel: str, timestamp: str, name: str,
                      user: str = "U01AMELIA") -> Dict[str, Any]:
        for m in self.messages:
            if m["channel_id"] == channel and m["ts"] == timestamp:
                for r in m["reactions"]:
                    if r["name"] == name:
                        if user not in r["users"]:
                            r["users"].append(user)
                            r["count"] = len(r["users"])
                        return {"status": "ok", "output": {}}
                m["reactions"].append({"name": name, "users": [user], "count": 1})
                return {"status": "ok", "output": {}}
        return {"status": "failed", "output": "message_not_found"}

    # --- search ------------------------------------------------------------
    def search_messages(self, query: str) -> Dict[str, Any]:
        q = query.lower()
        matches = [m for m in self.messages if q in m["text"].lower()]
        return {"status": "ok", "output": {"messages": {"total": len(matches), "matches": matches}}}


if __name__ == "__main__":
    s = SlackSession(seed=12)
    print(s.auth_test())
    print(s.conversations_list())
