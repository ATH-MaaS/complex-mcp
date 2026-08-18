import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
import hashlib
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class MailchimpSession:
    """Deterministic sandbox for the Mailchimp Marketing mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent. A member's
    ``id`` is the ``subscriber_hash`` (MD5 of the lowercased email), so member lookups
    accept either the hash or the raw email address.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "mailchimp.yaml") as f:
                info = yaml.safe_load(f)

            self.lists: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "company": r["company"],
                    "from_name": r["from_name"],
                    "from_email": r["from_email"],
                    "subject": r["subject"],
                    "member_count": _to_int(r.get("member_count", 0)),
                    "unsubscribe_count": _to_int(r.get("unsubscribe_count", 0)),
                    "date_created": r["date_created"],
                }
                for r in info.get("lists", [])
            ]

            self.members: List[Dict[str, Any]] = [
                {
                    "id": self._subscriber_hash(r["email_address"]),
                    "list_id": r["list_id"],
                    "email_address": r["email_address"],
                    "full_name": r["full_name"],
                    "status": r["status"],
                    "timestamp_signup": r["timestamp_signup"],
                    "member_rating": _to_int(r.get("member_rating", 0)),
                    "_pk": f"{r['list_id']}@{self._subscriber_hash(r['email_address'])}",
                }
                for r in info.get("members", [])
            ]

            self.campaigns: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "list_id": r["list_id"],
                    "type": r["type"],
                    "status": r["status"],
                    "emails_sent": _to_int(r.get("emails_sent", 0)),
                    "send_time": (r.get("send_time") or None),
                    "create_time": r["create_time"],
                    "recipients": {"list_id": r["list_id"]},
                    "settings": {
                        "subject_line": r["subject_line"],
                        "from_name": r["from_name"],
                        "reply_to": r["reply_to"],
                        "title": r["title"],
                    },
                }
                for r in info.get("campaigns", [])
            ]

            self.reports: List[Dict[str, Any]] = [
                {
                    "id": r["campaign_id"],
                    "emails_sent": _to_int(r.get("emails_sent", 0)),
                    "opens": {
                        "opens_total": _to_int(r.get("opens_total", 0)),
                        "unique_opens": _to_int(r.get("unique_opens", 0)),
                        "open_rate": _to_float(r.get("open_rate", 0.0)),
                    },
                    "clicks": {
                        "clicks_total": _to_int(r.get("clicks_total", 0)),
                        "unique_clicks": _to_int(r.get("unique_clicks", 0)),
                        "click_rate": _to_float(r.get("click_rate", 0.0)),
                    },
                    "unsubscribed": _to_int(r.get("unsubscribed", 0)),
                    "bounces": {"hard_bounces": _to_int(r.get("bounces", 0))},
                }
                for r in info.get("reports", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMailchimp')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"members": self.members, "campaigns": self.campaigns}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=10))

    def _subscriber_hash(self, email: str) -> str:
        return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()

    def _get_list(self, list_id):
        for lst in self.lists:
            if lst["id"] == list_id:
                return lst
        return None

    def _get_member(self, pk):
        for m in self.members:
            if m["_pk"] == pk:
                return m
        return None

    def _get_campaign(self, campaign_id):
        for c in self.campaigns:
            if c["id"] == campaign_id:
                return c
        return None

    def _get_report(self, campaign_id):
        for r in self.reports:
            if r["id"] == campaign_id:
                return r
        return None

    def _resolve_member_pk(self, list_id, subscriber_hash):
        candidate = self._subscriber_hash(subscriber_hash) if "@" in subscriber_hash else subscriber_hash
        return f"{list_id}@{candidate}"

    def _strip_pk(self, member):
        return {k: v for k, v in member.items() if k != "_pk"}

    # --- API methods -------------------------------------------------------
    def list_lists(self) -> Dict[str, Any]:
        rows = list(self.lists)
        return {"status": "ok", "output": {"lists": rows, "total_items": len(rows)}}

    def get_list(self, list_id: str) -> Dict[str, Any]:
        lst = self._get_list(list_id)
        if lst:
            return {"status": "ok", "output": lst}
        return {"status": "failed", "output": f"List {list_id} not found"}

    def list_members(self, list_id: str, status: str | None = None) -> Dict[str, Any]:
        if not self._get_list(list_id):
            return {"status": "failed", "output": f"List {list_id} not found"}
        members = [self._strip_pk(m) for m in self.members if m["list_id"] == list_id]
        if status:
            members = [m for m in members if m["status"] == status]
        return {"status": "ok", "output": {
            "members": members,
            "list_id": list_id,
            "total_items": len(members),
        }}

    def get_member(self, list_id: str, subscriber_hash: str) -> Dict[str, Any]:
        pk = self._resolve_member_pk(list_id, subscriber_hash)
        m = self._get_member(pk)
        if m:
            return {"status": "ok", "output": self._strip_pk(m)}
        return {"status": "failed", "output": f"Member {subscriber_hash} not found in list {list_id}"}

    def create_member(self, list_id: str, email_address: str, status: str = "subscribed",
                      full_name: str = "", member_rating: int = 0) -> Dict[str, Any]:
        lst = self._get_list(list_id)
        if not lst:
            return {"status": "failed", "output": f"List {list_id} not found"}
        sub_hash = self._subscriber_hash(email_address)
        pk = f"{list_id}@{sub_hash}"
        if self._get_member(pk):
            return {"status": "failed", "output": f"Member {email_address} already exists in list {list_id}"}
        member = {
            "id": sub_hash,
            "list_id": list_id,
            "email_address": email_address,
            "full_name": full_name,
            "status": status,
            "timestamp_signup": self._now(),
            "member_rating": _to_int(member_rating),
            "_pk": pk,
        }
        self.members.append(member)
        lst["member_count"] = lst["member_count"] + 1
        return {"status": "ok", "output": self._strip_pk(member)}

    def update_member(self, list_id: str, subscriber_hash: str, status: str | None = None,
                      full_name: str | None = None, member_rating: int | None = None) -> Dict[str, Any]:
        pk = self._resolve_member_pk(list_id, subscriber_hash)
        member = self._get_member(pk)
        if not member:
            return {"status": "failed", "output": f"Member {subscriber_hash} not found in list {list_id}"}
        if status is not None:
            member["status"] = status
        if full_name is not None:
            member["full_name"] = full_name
        if member_rating is not None:
            member["member_rating"] = _to_int(member_rating)
        return {"status": "ok", "output": self._strip_pk(member)}

    def list_campaigns(self, status: str | None = None) -> Dict[str, Any]:
        campaigns = list(self.campaigns)
        if status:
            campaigns = [c for c in campaigns if c["status"] == status]
        return {"status": "ok", "output": {"campaigns": campaigns, "total_items": len(campaigns)}}

    def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        c = self._get_campaign(campaign_id)
        if c:
            return {"status": "ok", "output": c}
        return {"status": "failed", "output": f"Campaign {campaign_id} not found"}

    def create_campaign(self, list_id: str, subject_line: str, from_name: str, reply_to: str,
                        title: str = "", type_: str = "regular") -> Dict[str, Any]:
        if not self._get_list(list_id):
            return {"status": "failed", "output": f"List {list_id} not found"}
        campaign = {
            "id": "camp-" + self.uuid(),
            "list_id": list_id,
            "type": type_,
            "status": "save",
            "emails_sent": 0,
            "send_time": None,
            "create_time": self._now(),
            "recipients": {"list_id": list_id},
            "settings": {
                "subject_line": subject_line,
                "from_name": from_name,
                "reply_to": reply_to,
                "title": title,
            },
        }
        self.campaigns.append(campaign)
        return {"status": "ok", "output": campaign}

    def send_campaign(self, campaign_id: str) -> Dict[str, Any]:
        c = self._get_campaign(campaign_id)
        if not c:
            return {"status": "failed", "output": f"Campaign {campaign_id} not found"}
        if c["status"] == "sent":
            return {"status": "failed", "output": f"Campaign {campaign_id} has already been sent"}
        lst = self._get_list(c["list_id"])
        recipients = lst["member_count"] if lst else 0
        c["status"] = "sent"
        c["emails_sent"] = recipients
        c["send_time"] = self._now()
        if not self._get_report(campaign_id):
            self.reports.append({
                "id": campaign_id,
                "emails_sent": recipients,
                "opens": {"opens_total": 0, "unique_opens": 0, "open_rate": 0.0},
                "clicks": {"clicks_total": 0, "unique_clicks": 0, "click_rate": 0.0},
                "unsubscribed": 0,
                "bounces": {"hard_bounces": 0},
            })
        return {"status": "ok", "output": {"id": campaign_id, "status": "sent", "emails_sent": recipients}}

    def get_report(self, campaign_id: str) -> Dict[str, Any]:
        r = self._get_report(campaign_id)
        if r:
            return {"status": "ok", "output": r}
        if self._get_campaign(campaign_id):
            return {"status": "failed", "output": f"No report available for campaign {campaign_id}"}
        return {"status": "failed", "output": f"Campaign {campaign_id} not found"}


if __name__ == "__main__":
    s = MailchimpSession(seed=12)
    print(s.list_lists())
    print(s.list_campaigns(status="sent"))
