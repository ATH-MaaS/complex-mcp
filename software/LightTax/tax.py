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


FILING_STATUSES = ("single", "married_joint", "married_separate", "head_household")
FILING_STATE = ("draft", "filed", "amended", "accepted", "rejected")
SOURCE_TYPES = ("w2", "1099", "dividend", "capital_gain", "other")


@dataclass
class Filing:
    fid: str
    tax_year: int
    filing_status: str
    gross_income: float
    deductions_total: float
    tax_owed: float
    refund: float
    status: str


@dataclass
class Deduction:
    did: str
    filing_id: str
    category: str
    amount: float
    description: str
    date: str
    receipt_ref: str = ""


@dataclass
class IncomeSource:
    isid: str
    filing_id: str
    source_type: str
    employer_or_payer: str
    amount: float
    withheld: float


class TaxSession:
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
            self._today = datetime(2026, 1, 5)
            self.filings: Dict[str, Filing] = {}
            self.deductions: Dict[str, Deduction] = {}
            self.income_sources: Dict[str, IncomeSource] = {}
            self._seed_filings()
            self._seed_income_sources()
            self._seed_deductions()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTax')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed_filings(self) -> None:
        self._fid_2024 = self.uuid()
        self._fid_2025 = self.uuid()
        self.filings[self._fid_2024] = Filing(
            fid=self._fid_2024,
            tax_year=2024,
            filing_status="single",
            gross_income=82000.0,
            deductions_total=14200.0,
            tax_owed=11250.0,
            refund=1120.0,
            status="accepted",
        )
        self.filings[self._fid_2025] = Filing(
            fid=self._fid_2025,
            tax_year=2025,
            filing_status="married_joint",
            gross_income=145000.0,
            deductions_total=0.0,
            tax_owed=0.0,
            refund=0.0,
            status="draft",
        )

    def _seed_income_sources(self) -> None:
        base = datetime(2026, 1, 1)
        seeds = [
            (self._fid_2024, "w2",           "Acme Corp",         78000.0, 12400.0),
            (self._fid_2024, "1099",         "Freelance LLC",       4000.0,   0.0),
            (self._fid_2025, "w2",           "Acme Corp",         95000.0, 15200.0),
            (self._fid_2025, "dividend",     "Vanguard Brokerage",  2100.0,  210.0),
        ]
        for fid, stype, payer, amount, withheld in seeds:
            src = IncomeSource(
                isid=self.uuid(),
                filing_id=fid,
                source_type=stype,
                employer_or_payer=payer,
                amount=float(amount),
                withheld=float(withheld),
            )
            self.income_sources[src.isid] = src

    def _seed_deductions(self) -> None:
        base = datetime(2024, 3, 15)
        seeds = [
            (self._fid_2024, "mortgage_interest", 6800.0, "Home mortgage interest", 30,  "recpt_001"),
            (self._fid_2024, "charity",            2400.0, "Cash donations",         90,  "recpt_002"),
            (self._fid_2024, "medical",            1350.0, "Out-of-pocket medical",  120, "recpt_003"),
            (self._fid_2025, "charity",             800.0, "Donation to nonprofit",  200, "recpt_004"),
            (self._fid_2025, "student_loan",       2500.0, "Interest paid",          260, "recpt_005"),
            (self._fid_2025, "business_expense",   1500.0, "Home office deduction",  310, "recpt_006"),
        ]
        for fid, cat, amount, desc, day_offset, ref in seeds:
            d = (base + timedelta(days=day_offset)).date().isoformat()
            ded = Deduction(
                did=self.uuid(),
                filing_id=fid,
                category=cat,
                amount=float(amount),
                description=desc,
                date=d,
                receipt_ref=ref,
            )
            self.deductions[ded.did] = ded

    def get_session_dict(self) -> Dict:
        return {
            "today": self._today.date().isoformat(),
            "filings": {fid: asdict(f) for fid, f in self.filings.items()},
            "deductions": {did: asdict(d) for did, d in self.deductions.items()},
            "income_sources": {isid: asdict(s) for isid, s in self.income_sources.items()},
        }

    def _filing_summary(self, f: Filing) -> Dict:
        return {
            "fid": f.fid,
            "tax_year": f.tax_year,
            "filing_status": f.filing_status,
            "gross_income": f.gross_income,
            "deductions_total": f.deductions_total,
            "tax_owed": f.tax_owed,
            "refund": f.refund,
            "status": f.status,
        }

    def list_filings(self, status: Optional[str] = None) -> Dict:
        items = list(self.filings.values())
        if status:
            if status not in FILING_STATE:
                return {"status": "failed", "output": f"status must be one of {FILING_STATE}"}
            items = [f for f in items if f.status == status]
        items.sort(key=lambda f: f.tax_year, reverse=True)
        return {"status": "ok", "output": [self._filing_summary(f) for f in items]}

    def get_filing(self, fid: str) -> Dict:
        f = self.filings.get(fid)
        if not f:
            return {"status": "failed", "output": f"filing {fid} not found"}
        return {"status": "ok", "output": asdict(f)}

    def create_filing(self, tax_year: int, filing_status: str,
                      gross_income: float = 0.0) -> Dict:
        if filing_status not in FILING_STATUSES:
            return {"status": "failed", "output": f"filing_status must be one of {FILING_STATUSES}"}
        f = Filing(
            fid=self.uuid(),
            tax_year=int(tax_year),
            filing_status=filing_status,
            gross_income=float(gross_income),
            deductions_total=0.0,
            tax_owed=0.0,
            refund=0.0,
            status="draft",
        )
        self.filings[f.fid] = f
        return {"status": "ok", "output": self._filing_summary(f)}

    def update_filing(self, fid: str,
                      filing_status: Optional[str] = None,
                      gross_income: Optional[float] = None,
                      tax_owed: Optional[float] = None,
                      refund: Optional[float] = None) -> Dict:
        f = self.filings.get(fid)
        if not f:
            return {"status": "failed", "output": f"filing {fid} not found"}
        if filing_status is not None:
            if filing_status not in FILING_STATUSES:
                return {"status": "failed", "output": f"filing_status must be one of {FILING_STATUSES}"}
            f.filing_status = filing_status
        if gross_income is not None:
            f.gross_income = float(gross_income)
        if tax_owed is not None:
            f.tax_owed = float(tax_owed)
        if refund is not None:
            f.refund = float(refund)
        return {"status": "ok", "output": self._filing_summary(f)}

    def delete_filing(self, fid: str) -> Dict:
        if fid not in self.filings:
            return {"status": "failed", "output": f"filing {fid} not found"}
        del self.filings[fid]
        removed_ded = [did for did, d in self.deductions.items() if d.filing_id == fid]
        for did in removed_ded:
            del self.deductions[did]
        removed_src = [isid for isid, s in self.income_sources.items() if s.filing_id == fid]
        for isid in removed_src:
            del self.income_sources[isid]
        return {"status": "ok", "output": {
            "fid": fid,
            "removed_deductions": len(removed_ded),
            "removed_income_sources": len(removed_src),
        }}

    def submit_filing(self, fid: str) -> Dict:
        f = self.filings.get(fid)
        if not f:
            return {"status": "failed", "output": f"filing {fid} not found"}
        if f.status not in {"draft", "rejected"}:
            return {"status": "failed", "output": f"cannot submit from status {f.status}"}
        f.status = "filed"
        return {"status": "ok", "output": self._filing_summary(f)}

    def amend_filing(self, fid: str) -> Dict:
        f = self.filings.get(fid)
        if not f:
            return {"status": "failed", "output": f"filing {fid} not found"}
        if f.status not in {"filed", "accepted"}:
            return {"status": "failed", "output": f"cannot amend from status {f.status}"}
        f.status = "amended"
        return {"status": "ok", "output": self._filing_summary(f)}

    def list_deductions(self, filing_id: Optional[str] = None,
                        category: Optional[str] = None) -> Dict:
        items = list(self.deductions.values())
        if filing_id:
            items = [d for d in items if d.filing_id == filing_id]
        if category:
            items = [d for d in items if d.category == category]
        items.sort(key=lambda d: d.date)
        return {"status": "ok", "output": [asdict(d) for d in items]}

    def _refresh_deductions_total(self, filing_id: str) -> None:
        f = self.filings.get(filing_id)
        if not f:
            return
        total = 0.0
        for d in self.deductions.values():
            if d.filing_id == filing_id:
                total += d.amount
        f.deductions_total = round(total, 2)

    def add_deduction(self, filing_id: str, category: str, amount: float,
                      description: str = "", date: str = "",
                      receipt_ref: str = "") -> Dict:
        if filing_id not in self.filings:
            return {"status": "failed", "output": f"filing {filing_id} not found"}
        d = Deduction(
            did=self.uuid(),
            filing_id=filing_id,
            category=category,
            amount=float(amount),
            description=description,
            date=date or self._today.date().isoformat(),
            receipt_ref=receipt_ref,
        )
        self.deductions[d.did] = d
        self._refresh_deductions_total(filing_id)
        return {"status": "ok", "output": asdict(d)}

    def update_deduction(self, did: str,
                         category: Optional[str] = None,
                         amount: Optional[float] = None,
                         description: Optional[str] = None,
                         date: Optional[str] = None,
                         receipt_ref: Optional[str] = None) -> Dict:
        d = self.deductions.get(did)
        if not d:
            return {"status": "failed", "output": f"deduction {did} not found"}
        if category is not None:
            d.category = category
        if amount is not None:
            d.amount = float(amount)
        if description is not None:
            d.description = description
        if date is not None:
            d.date = date
        if receipt_ref is not None:
            d.receipt_ref = receipt_ref
        self._refresh_deductions_total(d.filing_id)
        return {"status": "ok", "output": asdict(d)}

    def delete_deduction(self, did: str) -> Dict:
        d = self.deductions.pop(did, None)
        if not d:
            return {"status": "failed", "output": f"deduction {did} not found"}
        self._refresh_deductions_total(d.filing_id)
        return {"status": "ok", "output": {"did": did, "deleted": True}}

    def list_income_sources(self, filing_id: Optional[str] = None) -> Dict:
        items = list(self.income_sources.values())
        if filing_id:
            items = [s for s in items if s.filing_id == filing_id]
        items.sort(key=lambda s: (s.filing_id, s.source_type))
        return {"status": "ok", "output": [asdict(s) for s in items]}

    def _refresh_gross_income(self, filing_id: str) -> None:
        f = self.filings.get(filing_id)
        if not f:
            return
        total = 0.0
        for s in self.income_sources.values():
            if s.filing_id == filing_id:
                total += s.amount
        f.gross_income = round(total, 2)

    def add_income_source(self, filing_id: str, source_type: str,
                          employer_or_payer: str, amount: float,
                          withheld: float = 0.0) -> Dict:
        if filing_id not in self.filings:
            return {"status": "failed", "output": f"filing {filing_id} not found"}
        if source_type not in SOURCE_TYPES:
            return {"status": "failed", "output": f"source_type must be one of {SOURCE_TYPES}"}
        s = IncomeSource(
            isid=self.uuid(),
            filing_id=filing_id,
            source_type=source_type,
            employer_or_payer=employer_or_payer,
            amount=float(amount),
            withheld=float(withheld),
        )
        self.income_sources[s.isid] = s
        self._refresh_gross_income(filing_id)
        return {"status": "ok", "output": asdict(s)}

    def update_income_source(self, isid: str,
                             source_type: Optional[str] = None,
                             employer_or_payer: Optional[str] = None,
                             amount: Optional[float] = None,
                             withheld: Optional[float] = None) -> Dict:
        s = self.income_sources.get(isid)
        if not s:
            return {"status": "failed", "output": f"income source {isid} not found"}
        if source_type is not None:
            if source_type not in SOURCE_TYPES:
                return {"status": "failed", "output": f"source_type must be one of {SOURCE_TYPES}"}
            s.source_type = source_type
        if employer_or_payer is not None:
            s.employer_or_payer = employer_or_payer
        if amount is not None:
            s.amount = float(amount)
        if withheld is not None:
            s.withheld = float(withheld)
        self._refresh_gross_income(s.filing_id)
        return {"status": "ok", "output": asdict(s)}

    def get_filing_summary(self, fid: str) -> Dict:
        f = self.filings.get(fid)
        if not f:
            return {"status": "failed", "output": f"filing {fid} not found"}
        gross = 0.0
        withheld = 0.0
        by_source: Dict[str, float] = {}
        for s in self.income_sources.values():
            if s.filing_id == fid:
                gross += s.amount
                withheld += s.withheld
                by_source[s.source_type] = by_source.get(s.source_type, 0.0) + s.amount
        ded_total = 0.0
        by_cat: Dict[str, float] = {}
        for d in self.deductions.values():
            if d.filing_id == fid:
                ded_total += d.amount
                by_cat[d.category] = by_cat.get(d.category, 0.0) + d.amount
        return {
            "status": "ok",
            "output": {
                "fid": fid,
                "tax_year": f.tax_year,
                "filing_status": f.filing_status,
                "status": f.status,
                "gross_income": round(gross, 2),
                "withheld_total": round(withheld, 2),
                "deductions_total": round(ded_total, 2),
                "tax_owed": f.tax_owed,
                "refund": f.refund,
                "income_by_source": {k: round(v, 2) for k, v in by_source.items()},
                "deductions_by_category": {k: round(v, 2) for k, v in by_cat.items()},
            },
        }

    def get_stats(self) -> Dict:
        by_state: Dict[str, int] = {s: 0 for s in FILING_STATE}
        for f in self.filings.values():
            by_state[f.status] = by_state.get(f.status, 0) + 1
        return {
            "status": "ok",
            "output": {
                "filings": len(self.filings),
                "deductions": len(self.deductions),
                "income_sources": len(self.income_sources),
                "by_status": by_state,
            },
        }
