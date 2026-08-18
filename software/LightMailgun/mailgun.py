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


class MailgunSession:
    """Deterministic sandbox for the Mailgun mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "mailgun.yaml") as f:
                info = yaml.safe_load(f)

            self.messages: List[Dict[str, Any]] = [
                {
                    "id": m["id"],
                    "domain": m["domain"],
                    "sender": m["sender"],
                    "recipient": m["recipient"],
                    "subject": m["subject"],
                    "body": m["body"],
                    "timestamp": m["timestamp"],
                }
                for m in info.get("messages", [])
            ]
            self.events: List[Dict[str, Any]] = [
                {
                    "id": e["id"],
                    "domain": e["domain"],
                    "message_id": e["message_id"],
                    "event": e["event"],
                    "recipient": e["recipient"],
                    "timestamp": e["timestamp"],
                    "reason": (e.get("reason") or None),
                }
                for e in info.get("events", [])
            ]
            self.members: List[Dict[str, Any]] = [
                {
                    "list_address": r["list_address"],
                    "address": r["address"],
                    "name": r["name"],
                    "subscribed": _to_bool(r.get("subscribed", False)),
                    "vars": r["vars"],
                }
                for r in info.get("list_members", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMailgun')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"messages": self.messages, "events": self.events, "members": self.members}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _now_iso(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789ABCDEF"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_message_id(self, domain: str) -> str:
        stamp = ''.join(self.rng.choices("0123456789", k=14))
        return f"{stamp}.{''.join(self.rng.choices('0123456789ABCDEF', k=12))}@{domain}"

    # --- API methods -------------------------------------------------------
    def send_message(self, domain: str, sender: str, to: str,
                     subject: str = "", text: str = "") -> Dict[str, Any]:
        if not sender or not to:
            return {"status": "failed", "output": "from and to are required"}
        msg_id = self._new_message_id(domain)
        now = self._now_iso()
        message = {
            "id": msg_id,
            "domain": domain,
            "sender": sender,
            "recipient": to,
            "subject": subject or "",
            "body": text or "",
            "timestamp": now,
        }
        self.messages.append(message)
        self.events.append({
            "id": f"ev_{''.join(self.rng.choices('0123456789abcdef', k=8))}",
            "domain": domain,
            "message_id": msg_id,
            "event": "accepted",
            "recipient": to,
            "timestamp": now,
            "reason": None,
        })
        return {"status": "ok", "output": {"id": f"<{msg_id}>", "message": "Queued. Thank you."}}

    def get_events(self, domain: str, event: str | None = None,
                   recipient: str | None = None, limit: int = 300) -> Dict[str, Any]:
        items = [e for e in self.events if e["domain"] == domain]
        if event:
            wanted = {x.strip().lower() for x in event.split(" OR ")}
            items = [e for e in items if e["event"].lower() in wanted]
        if recipient:
            items = [e for e in items if e["recipient"].lower() == recipient.lower()]
        items = sorted(items, key=lambda e: e["timestamp"], reverse=True)[:limit]
        out = []
        for e in items:
            item = {
                "id": e["id"],
                "event": e["event"],
                "timestamp": e["timestamp"],
                "recipient": e["recipient"],
                "message": {"headers": {"message-id": e["message_id"]}},
            }
            if e["reason"]:
                item["reason"] = e["reason"]
            out.append(item)
        return {"status": "ok", "output": {"items": out, "paging": {"next": None, "previous": None}}}

    def get_stats_total(self, domain: str, event: str | None = None) -> Dict[str, Any]:
        events_for_domain = [e for e in self.events if e["domain"] == domain]
        wanted = ["accepted", "delivered", "failed", "opened", "clicked"]
        if event:
            wanted = [x.strip().lower() for x in event.split(",")]
        stats = []
        for name in wanted:
            count = sum(1 for e in events_for_domain if e["event"].lower() == name)
            stats.append({"time": self._now_iso(), name: {"total": count}})
        return {"status": "ok", "output": {
            "start": min((e["timestamp"] for e in events_for_domain), default=self._now_iso()),
            "end": max((e["timestamp"] for e in events_for_domain), default=self._now_iso()),
            "resolution": "month",
            "stats": stats,
        }}

    def list_members(self, address: str, subscribed: bool | None = None) -> Dict[str, Any]:
        members = [m for m in self.members if m["list_address"].lower() == (address or "").lower()]
        if not members:
            if address not in {m["list_address"] for m in self.members}:
                return {"status": "failed", "output": f"mailing list {address} not found"}
        if subscribed is not None:
            members = [m for m in members if m["subscribed"] == subscribed]
        items = []
        for m in members:
            items.append({
                "address": m["address"],
                "name": m["name"],
                "subscribed": m["subscribed"],
                "vars": m["vars"],
            })
        return {"status": "ok", "output": {"items": items, "total_count": len(items)}}


if __name__ == "__main__":
    s = MailgunSession(seed=12)
    print(s.get_events("sandbox.mailgun.org"))
    print(s.list_members("newsletter@sandbox.mailgun.org"))
