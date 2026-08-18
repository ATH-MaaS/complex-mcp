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


STAGES = ("lead", "qualified", "proposal", "negotiation", "won", "lost")

SEED_CONTACTS = [
    ("Alice Chen",   "alice@acme.com",     "+1-415-555-0101", "Acme Corp",     "VP Engineering", ["priority", "enterprise"], "Met at MCP conf."),
    ("Bob Rivera",   "bob@nimbus.io",      "+1-415-555-0102", "Nimbus IO",     "CTO",             ["startup"],                 "Warm intro from Alice."),
    ("Carol Wu",     "carol@lightyear.ai", "+1-415-555-0103", "Lightyear AI",  "Product Lead",    ["ai"],                      ""),
    ("Dan Patel",    "dan@finfabric.com",  "+1-212-555-0104", "FinFabric",     "Head of Data",    ["fintech"],                 "Interested in benchmark tools."),
    ("Eve Nakamura", "eve@zenithsoft.jp",  "+81-3-5555-0105", "Zenith Soft",   "Director",        ["enterprise"],              "Contract in JPY."),
]

SEED_DEALS = [
    ("MCP Platform License",   0, "proposal",    45000.0,  12, "Annual license."),
    ("Pilot: RAG stack",       1, "qualified",   15000.0,  20, "Three-month pilot."),
    ("Consulting: LLM eval",   2, "negotiation", 30000.0,   5, "Custom eval suite."),
    ("Data pipeline upgrade",  3, "won",         80000.0, -10, "Closed last month."),
    ("Legacy renewal",         4, "lost",        50000.0, -30, "Went with competitor."),
]


@dataclass
class Contact:
    cid: str
    name: str
    email: str
    phone: str = ""
    company: str = ""
    title: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Deal:
    did: str
    title: str
    contact_id: str
    stage: str
    amount: float
    close_date: str
    notes: str = ""


class CRMSession:
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
            self.contacts: Dict[str, Contact] = {}
            self.deals: Dict[str, Deal] = {}
            self._today = datetime(2026, 1, 5)
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightCRM')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self) -> None:
        contact_ids: List[str] = []
        for name, email, phone, company, title, tags, notes in SEED_CONTACTS:
            c = Contact(
                cid=self.uuid(),
                name=name,
                email=email,
                phone=phone,
                company=company,
                title=title,
                tags=list(tags),
                notes=notes,
            )
            self.contacts[c.cid] = c
            contact_ids.append(c.cid)
        for title, contact_idx, stage, amount, day_offset, notes in SEED_DEALS:
            close_date = (self._today + timedelta(days=day_offset)).date().isoformat()
            d = Deal(
                did=self.uuid(),
                title=title,
                contact_id=contact_ids[contact_idx],
                stage=stage,
                amount=amount,
                close_date=close_date,
                notes=notes,
            )
            self.deals[d.did] = d

    def get_session_dict(self) -> Dict:
        return {
            "contacts": {cid: asdict(c) for cid, c in self.contacts.items()},
            "deals": {did: asdict(d) for did, d in self.deals.items()},
        }

    def _contact_summary(self, c: Contact) -> Dict:
        return {
            "cid": c.cid,
            "name": c.name,
            "email": c.email,
            "company": c.company,
            "title": c.title,
            "tags": list(c.tags),
        }

    def _deal_summary(self, d: Deal) -> Dict:
        return {
            "did": d.did,
            "title": d.title,
            "contact_id": d.contact_id,
            "stage": d.stage,
            "amount": d.amount,
            "close_date": d.close_date,
        }

    def list_contacts(self, tag: Optional[str] = None) -> Dict:
        items = list(self.contacts.values())
        if tag:
            items = [c for c in items if tag in c.tags]
        items.sort(key=lambda c: c.name.lower())
        return {"status": "ok", "output": [self._contact_summary(c) for c in items]}

    def get_contact(self, cid: str) -> Dict:
        c = self.contacts.get(cid)
        if not c:
            return {"status": "failed", "output": f"contact {cid} not found"}
        return {"status": "ok", "output": asdict(c)}

    def create_contact(self, name: str, email: str,
                       phone: str = "", company: str = "",
                       title: str = "", tags: Optional[List[str]] = None,
                       notes: str = "") -> Dict:
        c = Contact(
            cid=self.uuid(),
            name=name,
            email=email,
            phone=phone,
            company=company,
            title=title,
            tags=list(tags) if tags else [],
            notes=notes,
        )
        self.contacts[c.cid] = c
        return {"status": "ok", "output": self._contact_summary(c)}

    def update_contact(self, cid: str,
                       name: Optional[str] = None,
                       email: Optional[str] = None,
                       phone: Optional[str] = None,
                       company: Optional[str] = None,
                       title: Optional[str] = None,
                       tags: Optional[List[str]] = None,
                       notes: Optional[str] = None) -> Dict:
        c = self.contacts.get(cid)
        if not c:
            return {"status": "failed", "output": f"contact {cid} not found"}
        for k, v in {
            "name": name, "email": email, "phone": phone,
            "company": company, "title": title, "notes": notes,
        }.items():
            if v is not None:
                setattr(c, k, v)
        if tags is not None:
            c.tags = list(tags)
        return {"status": "ok", "output": self._contact_summary(c)}

    def delete_contact(self, cid: str) -> Dict:
        c = self.contacts.pop(cid, None)
        if not c:
            return {"status": "failed", "output": f"contact {cid} not found"}
        removed = [did for did, d in self.deals.items() if d.contact_id == cid]
        for did in removed:
            del self.deals[did]
        return {"status": "ok", "output": {"cid": cid, "removed_deals": len(removed)}}

    def list_deals(self, stage: Optional[str] = None,
                   contact_id: Optional[str] = None) -> Dict:
        items = list(self.deals.values())
        if stage:
            if stage not in STAGES:
                return {"status": "failed", "output": f"stage must be one of {STAGES}"}
            items = [d for d in items if d.stage == stage]
        if contact_id:
            items = [d for d in items if d.contact_id == contact_id]
        items.sort(key=lambda d: d.close_date)
        return {"status": "ok", "output": [self._deal_summary(d) for d in items]}

    def get_deal(self, did: str) -> Dict:
        d = self.deals.get(did)
        if not d:
            return {"status": "failed", "output": f"deal {did} not found"}
        return {"status": "ok", "output": asdict(d)}

    def create_deal(self, title: str, contact_id: str,
                    stage: str = "lead",
                    amount: float = 0.0,
                    close_date: str = "",
                    notes: str = "") -> Dict:
        if contact_id not in self.contacts:
            return {"status": "failed", "output": f"contact {contact_id} not found"}
        if stage not in STAGES:
            return {"status": "failed", "output": f"stage must be one of {STAGES}"}
        d = Deal(
            did=self.uuid(),
            title=title,
            contact_id=contact_id,
            stage=stage,
            amount=amount,
            close_date=close_date,
            notes=notes,
        )
        self.deals[d.did] = d
        return {"status": "ok", "output": self._deal_summary(d)}

    def update_deal(self, did: str,
                    title: Optional[str] = None,
                    contact_id: Optional[str] = None,
                    stage: Optional[str] = None,
                    amount: Optional[float] = None,
                    close_date: Optional[str] = None,
                    notes: Optional[str] = None) -> Dict:
        d = self.deals.get(did)
        if not d:
            return {"status": "failed", "output": f"deal {did} not found"}
        if contact_id is not None and contact_id not in self.contacts:
            return {"status": "failed", "output": f"contact {contact_id} not found"}
        if stage is not None and stage not in STAGES:
            return {"status": "failed", "output": f"stage must be one of {STAGES}"}
        for k, v in {
            "title": title, "contact_id": contact_id, "stage": stage,
            "amount": amount, "close_date": close_date, "notes": notes,
        }.items():
            if v is not None:
                setattr(d, k, v)
        return {"status": "ok", "output": self._deal_summary(d)}

    def delete_deal(self, did: str) -> Dict:
        d = self.deals.pop(did, None)
        if not d:
            return {"status": "failed", "output": f"deal {did} not found"}
        return {"status": "ok", "output": {"did": did, "deleted": True}}

    def move_stage(self, did: str, stage: str) -> Dict:
        if stage not in STAGES:
            return {"status": "failed", "output": f"stage must be one of {STAGES}"}
        return self.update_deal(did, stage=stage)

    def search_contacts(self, query: str) -> Dict:
        q = query.lower()
        items = [c for c in self.contacts.values()
                 if q in c.name.lower() or q in c.email.lower()
                 or q in c.company.lower() or q in c.title.lower()
                 or q in c.notes.lower()
                 or any(q in tag.lower() for tag in c.tags)]
        items.sort(key=lambda c: c.name.lower())
        return {"status": "ok", "output": [self._contact_summary(c) for c in items]}

    def list_won(self) -> Dict:
        items = [d for d in self.deals.values() if d.stage == "won"]
        items.sort(key=lambda d: d.close_date, reverse=True)
        return {"status": "ok", "output": [self._deal_summary(d) for d in items]}

    def list_lost(self) -> Dict:
        items = [d for d in self.deals.values() if d.stage == "lost"]
        items.sort(key=lambda d: d.close_date, reverse=True)
        return {"status": "ok", "output": [self._deal_summary(d) for d in items]}

    def get_pipeline_summary(self) -> Dict:
        by_stage: Dict[str, Dict] = {s: {"count": 0, "amount": 0.0} for s in STAGES}
        for d in self.deals.values():
            b = by_stage.setdefault(d.stage, {"count": 0, "amount": 0.0})
            b["count"] += 1
            b["amount"] += float(d.amount)
        open_stages = {"lead", "qualified", "proposal", "negotiation"}
        pipeline_value = sum(
            float(d.amount) for d in self.deals.values() if d.stage in open_stages
        )
        return {
            "status": "ok",
            "output": {
                "by_stage": by_stage,
                "pipeline_value": pipeline_value,
                "total_deals": len(self.deals),
            },
        }

    def get_stats(self) -> Dict:
        won_amount = sum(float(d.amount) for d in self.deals.values() if d.stage == "won")
        lost_amount = sum(float(d.amount) for d in self.deals.values() if d.stage == "lost")
        by_stage: Dict[str, int] = {s: 0 for s in STAGES}
        for d in self.deals.values():
            by_stage[d.stage] = by_stage.get(d.stage, 0) + 1
        return {
            "status": "ok",
            "output": {
                "contacts": len(self.contacts),
                "deals": len(self.deals),
                "by_stage": by_stage,
                "won_amount": won_amount,
                "lost_amount": lost_amount,
            },
        }
