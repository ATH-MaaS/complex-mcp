from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


FOLDERS = ["inbox", "sent", "drafts", "trash", "spam"]

SENDERS = [
    ("Alice Cooper", "alice.cooper@example.com"),
    ("Bob Martin", "bob.martin@example.com"),
    ("Carol Diaz", "carol.diaz@example.com"),
    ("David Kim", "david.kim@example.com"),
    ("Eva Torres", "eva.torres@example.com"),
    ("Frank Hall", "frank.hall@example.com"),
    ("Grace Chen", "grace.chen@example.com"),
    ("Henry Park", "henry.park@example.com"),
    ("Newsletter", "hello@newsletter.example.com"),
    ("BankOfLight", "no-reply@bankoflight.example.com"),
    ("ShopLight", "orders@shoplight.example.com"),
    ("Security Team", "security@example.com"),
]

TEMPLATES = [
    ("Meeting tomorrow at 10", "Hi, just confirming our meeting tomorrow at 10am. Let me know if that still works."),
    ("Project update", "Sharing the latest project status: milestone 2 complete, milestone 3 in progress. Let's sync Friday."),
    ("Weekly newsletter", "This week: 5 new articles, 3 upcoming events. Check the site for details."),
    ("Your order has shipped", "Order #12345 has shipped and will arrive in 2-3 business days."),
    ("Statement ready", "Your monthly statement is now available. Log in to view details."),
    ("New sign-in detected", "We noticed a new sign-in to your account. If this wasn't you, please secure your account."),
    ("Lunch this week?", "Free for lunch anytime this week? Would love to catch up."),
    ("Report attached", "Please find the quarterly report attached. Let me know if you have questions."),
    ("Reminder: renew subscription", "Your subscription renews in 7 days at $9.99/month."),
    ("Team offsite planning", "We're finalizing the team offsite dates. Please fill out the poll by Friday."),
    ("Invoice #INV-2087", "Attached is invoice INV-2087 for services rendered. Payment due in 30 days."),
    ("Welcome aboard", "Welcome to the team! Here are some resources to help you get started."),
]


@dataclass
class Message:
    mid: str
    sender_name: str
    sender_email: str
    to: List[str]
    cc: List[str]
    subject: str
    body: str
    timestamp: str
    read: bool = False
    starred: bool = False
    folder: str = "inbox"


CORPUS_PATH = Path("software") / "LightMail" / "corpus"


class MailSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"],
            ) if os_cfg else DummyOSConnector()
            self.user_email = "me@example.com"
            self.messages: Dict[str, Message] = {}
            self._seed_messages()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightMail')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed_messages(self) -> None:
        now = datetime(2026, 1, 1, 9, 0, 0)
        for i in range(24):
            name, email = self.rng.choice(SENDERS)
            subject, body = self.rng.choice(TEMPLATES)
            ts = now - timedelta(hours=self.rng.randint(1, 24 * 20))
            m = Message(
                mid=self.uuid(),
                sender_name=name,
                sender_email=email,
                to=[self.user_email],
                cc=[],
                subject=subject,
                body=body,
                timestamp=ts.isoformat(timespec="seconds"),
                read=self.rng.random() < 0.3,
                starred=False,
                folder="inbox",
            )
            self.messages[m.mid] = m

    def get_session_dict(self) -> Dict:
        return {
            "user_email": self.user_email,
            "messages": {mid: asdict(m) for mid, m in self.messages.items()},
        }

    def _msg_summary(self, m: Message) -> Dict:
        return {
            "mid": m.mid,
            "from": f"{m.sender_name} <{m.sender_email}>",
            "subject": m.subject,
            "timestamp": m.timestamp,
            "read": m.read,
            "starred": m.starred,
            "folder": m.folder,
        }

    def list_folders(self) -> Dict:
        counts = {f: 0 for f in FOLDERS}
        unread = {f: 0 for f in FOLDERS}
        for m in self.messages.values():
            if m.folder in counts:
                counts[m.folder] += 1
                if not m.read:
                    unread[m.folder] += 1
        return {
            "status": "ok",
            "output": [
                {"name": f, "total": counts[f], "unread": unread[f]} for f in FOLDERS
            ],
        }

    def list_messages(self, folder: str, limit: int = 20, offset: int = 0) -> Dict:
        if folder not in FOLDERS:
            return {"status": "failed", "output": f"unknown folder {folder}"}
        items = [m for m in self.messages.values() if m.folder == folder]
        items.sort(key=lambda m: m.timestamp, reverse=True)
        window = items[offset : offset + limit]
        return {
            "status": "ok",
            "output": [self._msg_summary(m) for m in window],
        }

    def get_message(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        return {"status": "ok", "output": asdict(m)}

    def mark_as_read(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.read = True
        return {"status": "ok", "output": self._msg_summary(m)}

    def mark_as_unread(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.read = False
        return {"status": "ok", "output": self._msg_summary(m)}

    def star(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.starred = True
        return {"status": "ok", "output": self._msg_summary(m)}

    def unstar(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.starred = False
        return {"status": "ok", "output": self._msg_summary(m)}

    def move_to_folder(self, mid: str, folder: str) -> Dict:
        if folder not in FOLDERS:
            return {"status": "failed", "output": f"unknown folder {folder}"}
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.folder = folder
        return {"status": "ok", "output": self._msg_summary(m)}

    def delete_message(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        m.folder = "trash"
        return {"status": "ok", "output": self._msg_summary(m)}

    def compose_email(self, to: List[str], subject: str, body: str, cc: Optional[List[str]] = None) -> Dict:
        ts = datetime(2026, 1, 1, 12, 0, 0).isoformat(timespec="seconds")
        m = Message(
            mid=self.uuid(),
            sender_name="Me",
            sender_email=self.user_email,
            to=list(to),
            cc=list(cc) if cc else [],
            subject=subject,
            body=body,
            timestamp=ts,
            read=True,
            starred=False,
            folder="drafts",
        )
        self.messages[m.mid] = m
        return {"status": "ok", "output": self._msg_summary(m)}

    def send_email(self, mid: str) -> Dict:
        m = self.messages.get(mid)
        if not m:
            return {"status": "failed", "output": f"message {mid} not found"}
        if m.folder != "drafts":
            return {"status": "failed", "output": f"message {mid} is not a draft"}
        m.folder = "sent"
        return {"status": "ok", "output": self._msg_summary(m)}

    def reply(self, mid: str, body: str) -> Dict:
        original = self.messages.get(mid)
        if not original:
            return {"status": "failed", "output": f"message {mid} not found"}
        return self.compose_email(
            to=[original.sender_email],
            subject=f"Re: {original.subject}",
            body=body,
        )

    def search_messages(self, query: str, folder: Optional[str] = None) -> Dict:
        q = query.lower()
        items: List[Message] = []
        for m in self.messages.values():
            if folder and m.folder != folder:
                continue
            hay = f"{m.subject}\n{m.body}\n{m.sender_name}\n{m.sender_email}".lower()
            if q in hay:
                items.append(m)
        items.sort(key=lambda m: m.timestamp, reverse=True)
        return {"status": "ok", "output": [self._msg_summary(m) for m in items]}
