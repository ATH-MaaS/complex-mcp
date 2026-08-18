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


class MicrosoftTeamsSession:
    """Deterministic sandbox for the Microsoft Teams (Graph) mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent. Graph wraps
    collections as {"value": [...]}; here the Light envelope carries that payload as output.
    """

    # The signed-in user (the "me" of /me/joinedTeams).
    _ME = "user-001"

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "microsoft_teams.yaml") as f:
                info = yaml.safe_load(f)

            self.teams: List[Dict[str, Any]] = [
                {
                    "id": t["id"],
                    "displayName": t["display_name"],
                    "description": t["description"],
                    "visibility": t["visibility"],
                    "isArchived": _to_bool(t.get("is_archived", False)),
                    "webUrl": t["web_url"],
                    "member_ids": [x for x in str(t.get("member_ids", "")).split(";") if x],
                }
                for t in info.get("teams", [])
            ]
            self.channels: List[Dict[str, Any]] = [
                {
                    "id": c["id"],
                    "team_id": c["team_id"],
                    "displayName": c["display_name"],
                    "description": c["description"],
                    "membershipType": c["membership_type"],
                    "webUrl": c["web_url"],
                    "createdDateTime": c["created_date"],
                }
                for c in info.get("channels", [])
            ]
            self.messages: List[Dict[str, Any]] = [
                {
                    "id": m["id"],
                    "channel_id": m["channel_id"],
                    "team_id": m["team_id"],
                    "from_user_id": m["from_user_id"],
                    "from_display_name": m["from_display_name"],
                    "content": m["content"],
                    "contentType": m["content_type"],
                    "importance": m["importance"],
                    "createdDateTime": m["created_date"],
                }
                for m in info.get("messages", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMicrosoftTeams')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"messages": self.messages}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=4))

    def _serialize_team(self, t):
        return {
            "id": t["id"],
            "displayName": t["displayName"],
            "description": t["description"],
            "visibility": t["visibility"],
            "isArchived": t["isArchived"],
            "webUrl": t["webUrl"],
        }

    def _serialize_channel(self, c):
        return {
            "id": c["id"],
            "displayName": c["displayName"],
            "description": c["description"],
            "membershipType": c["membershipType"],
            "webUrl": c["webUrl"],
            "createdDateTime": c["createdDateTime"],
        }

    def _serialize_message(self, m):
        return {
            "id": m["id"],
            "messageType": "message",
            "createdDateTime": m["createdDateTime"],
            "importance": m["importance"],
            "channelIdentity": {
                "teamId": m["team_id"],
                "channelId": m["channel_id"],
            },
            "from": {
                "user": {
                    "id": m["from_user_id"],
                    "displayName": m["from_display_name"],
                }
            },
            "body": {
                "contentType": m["contentType"],
                "content": m["content"],
            },
        }

    def _channel(self, team_id, channel_id):
        return next(
            (c for c in self.channels if c["id"] == channel_id and c["team_id"] == team_id),
            None,
        )

    # --- API methods -------------------------------------------------------
    def list_joined_teams(self) -> Dict[str, Any]:
        teams = [t for t in self.teams if self._ME in t["member_ids"] and not t["isArchived"]]
        return {"status": "ok", "output": {"value": [self._serialize_team(t) for t in teams]}}

    def get_team(self, team_id: str) -> Dict[str, Any]:
        for t in self.teams:
            if t["id"] == team_id:
                return {"status": "ok", "output": self._serialize_team(t)}
        return {"status": "failed", "output": f"Team {team_id} not found"}

    def list_channels(self, team_id: str) -> Dict[str, Any]:
        if not any(t["id"] == team_id for t in self.teams):
            return {"status": "failed", "output": f"Team {team_id} not found"}
        channels = [c for c in self.channels if c["team_id"] == team_id]
        return {"status": "ok", "output": {"value": [self._serialize_channel(c) for c in channels]}}

    def list_messages(self, team_id: str, channel_id: str) -> Dict[str, Any]:
        if not self._channel(team_id, channel_id):
            return {"status": "failed", "output": f"Channel {channel_id} not found"}
        msgs = [
            m for m in self.messages
            if m["channel_id"] == channel_id and m["team_id"] == team_id
        ]
        msgs = sorted(msgs, key=lambda m: m["createdDateTime"], reverse=True)
        return {"status": "ok", "output": {"value": [self._serialize_message(m) for m in msgs]}}

    def send_message(self, team_id: str, channel_id: str, content: str,
                     content_type: str = "html", importance: str = "normal") -> Dict[str, Any]:
        if not self._channel(team_id, channel_id):
            return {"status": "failed", "output": f"Channel {channel_id} not found"}
        if not content:
            return {"status": "failed", "output": "body.content is required"}
        now = self._now()
        msg = {
            "id": str(int(self.rng.random() * 1e13)) + self.uuid(),
            "channel_id": channel_id,
            "team_id": team_id,
            "from_user_id": self._ME,
            "from_display_name": "Alex Carter",
            "content": content,
            "contentType": content_type or "html",
            "importance": importance or "normal",
            "createdDateTime": now,
        }
        self.messages.append(msg)
        return {"status": "ok", "output": self._serialize_message(msg)}


if __name__ == "__main__":
    s = MicrosoftTeamsSession(seed=12)
    print(s.list_joined_teams())
    print(s.get_team("19:team-eng0001@thread.tacv2"))
