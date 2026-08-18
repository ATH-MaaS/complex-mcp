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


WALLET_KINDS = ("fiat", "crypto")
TRANSFER_STATUSES = ("pending", "completed", "failed")

DEFAULT_WALLETS = [
    {"wid": "wal_usd", "name": "USD Checking", "currency": "USD", "balance": 5000.0, "kind": "fiat"},
    {"wid": "wal_eur", "name": "EUR Savings",  "currency": "EUR", "balance": 2000.0, "kind": "fiat"},
    {"wid": "wal_btc", "name": "BTC Wallet",   "currency": "BTC", "balance": 0.5,    "kind": "crypto"},
    {"wid": "wal_eth", "name": "ETH Wallet",   "currency": "ETH", "balance": 3.2,    "kind": "crypto"},
]

SEED_TRANSFERS = [
    ("wal_usd", "wal_eur",  200.0, 1.50, 1, "completed", "Rent contribution"),
    ("wal_usd", "wal_btc",  500.0, 5.00, 2, "completed", "Buy BTC"),
    ("wal_eth", "wal_usd",  0.5,   0.01, 3, "pending",   "Convert ETH to USD"),
    ("wal_eur", "wal_usd",  120.0, 1.00, 4, "failed",    "Failed FX transfer"),
    ("wal_btc", "wal_eth",  0.01,  0.001, 5, "completed", "Swap portion"),
    ("wal_usd", "wal_eur",  75.0,  0.75, 6, "pending",   "Vacation fund"),
]


@dataclass
class Wallet:
    wid: str
    name: str
    currency: str
    balance: float
    kind: str


@dataclass
class Transfer:
    trid: str
    from_wid: str
    to_wid: str
    amount: float
    fee: float
    timestamp: str
    status: str
    memo: str = ""


class WalletSession:
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
            self.wallets: Dict[str, Wallet] = {
                w["wid"]: Wallet(**w) for w in DEFAULT_WALLETS
            }
            self.transfers: Dict[str, Transfer] = {}
            self._seed_transfers()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightWallet')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_transfers(self) -> None:
        base = datetime(2026, 1, 1, 9, 0)
        for from_wid, to_wid, amount, fee, day, status, memo in SEED_TRANSFERS:
            ts = (base + timedelta(days=day - 1, hours=self.rng.randint(0, 8))).isoformat(timespec="minutes")
            tr = Transfer(
                trid=self.uuid(),
                from_wid=from_wid,
                to_wid=to_wid,
                amount=float(amount),
                fee=float(fee),
                timestamp=ts,
                status=status,
                memo=memo,
            )
            self.transfers[tr.trid] = tr

    def get_session_dict(self) -> Dict:
        return {
            "today": self._today.date().isoformat(),
            "wallets": {wid: asdict(w) for wid, w in self.wallets.items()},
            "transfers": {trid: asdict(tr) for trid, tr in self.transfers.items()},
        }

    def _tr_summary(self, tr: Transfer) -> Dict:
        return {
            "trid": tr.trid,
            "from_wid": tr.from_wid,
            "to_wid": tr.to_wid,
            "amount": tr.amount,
            "fee": tr.fee,
            "timestamp": tr.timestamp,
            "status": tr.status,
            "memo": tr.memo,
        }

    def list_wallets(self, kind: Optional[str] = None) -> Dict:
        items = list(self.wallets.values())
        if kind:
            if kind not in WALLET_KINDS:
                return {"status": "failed", "output": f"kind must be one of {WALLET_KINDS}"}
            items = [w for w in items if w.kind == kind]
        items.sort(key=lambda w: (w.kind, w.currency))
        return {"status": "ok", "output": [asdict(w) for w in items]}

    def get_wallet(self, wid: str) -> Dict:
        w = self.wallets.get(wid)
        if not w:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        return {"status": "ok", "output": asdict(w)}

    def create_wallet(self, name: str, currency: str, kind: str = "fiat",
                      balance: float = 0.0) -> Dict:
        if kind not in WALLET_KINDS:
            return {"status": "failed", "output": f"kind must be one of {WALLET_KINDS}"}
        wid = "wal_" + self.uuid()[:8]
        w = Wallet(wid=wid, name=name, currency=currency,
                   balance=float(balance), kind=kind)
        self.wallets[wid] = w
        return {"status": "ok", "output": asdict(w)}

    def delete_wallet(self, wid: str) -> Dict:
        if wid not in self.wallets:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        del self.wallets[wid]
        return {"status": "ok", "output": {"wid": wid, "deleted": True}}

    def deposit(self, wid: str, amount: float) -> Dict:
        w = self.wallets.get(wid)
        if not w:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        if amount <= 0:
            return {"status": "failed", "output": "amount must be positive"}
        w.balance = round(w.balance + float(amount), 8)
        return {"status": "ok", "output": {"wid": wid, "balance": w.balance}}

    def withdraw(self, wid: str, amount: float) -> Dict:
        w = self.wallets.get(wid)
        if not w:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        if amount <= 0:
            return {"status": "failed", "output": "amount must be positive"}
        if w.balance < amount:
            return {"status": "failed", "output": "insufficient balance"}
        w.balance = round(w.balance - float(amount), 8)
        return {"status": "ok", "output": {"wid": wid, "balance": w.balance}}

    def transfer(self, from_wid: str, to_wid: str, amount: float, memo: str = "") -> Dict:
        if from_wid == to_wid:
            return {"status": "failed", "output": "from_wid and to_wid must differ"}
        src = self.wallets.get(from_wid)
        dst = self.wallets.get(to_wid)
        if not src:
            return {"status": "failed", "output": f"wallet {from_wid} not found"}
        if not dst:
            return {"status": "failed", "output": f"wallet {to_wid} not found"}
        if amount <= 0:
            return {"status": "failed", "output": "amount must be positive"}
        if src.currency != dst.currency:
            return {"status": "failed", "output": "cross-currency transfers not supported"}
        if src.balance < amount:
            return {"status": "failed", "output": "insufficient balance"}
        src.balance = round(src.balance - float(amount), 8)
        dst.balance = round(dst.balance + float(amount), 8)
        tr = Transfer(
            trid=self.uuid(),
            from_wid=from_wid,
            to_wid=to_wid,
            amount=float(amount),
            fee=0.0,
            timestamp=self._now(),
            status="completed",
            memo=memo,
        )
        self.transfers[tr.trid] = tr
        return {"status": "ok", "output": self._tr_summary(tr)}

    def get_balance(self, wid: str) -> Dict:
        w = self.wallets.get(wid)
        if not w:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        return {"status": "ok", "output": {"wid": wid, "currency": w.currency, "balance": w.balance}}

    def list_transfers(self, wid: Optional[str] = None,
                       status: Optional[str] = None) -> Dict:
        items = list(self.transfers.values())
        if wid:
            items = [tr for tr in items if tr.from_wid == wid or tr.to_wid == wid]
        if status:
            if status not in TRANSFER_STATUSES:
                return {"status": "failed", "output": f"status must be one of {TRANSFER_STATUSES}"}
            items = [tr for tr in items if tr.status == status]
        items.sort(key=lambda tr: tr.timestamp, reverse=True)
        return {"status": "ok", "output": [self._tr_summary(tr) for tr in items]}

    def get_transfer(self, trid: str) -> Dict:
        tr = self.transfers.get(trid)
        if not tr:
            return {"status": "failed", "output": f"transfer {trid} not found"}
        return {"status": "ok", "output": asdict(tr)}

    def cancel_transfer(self, trid: str) -> Dict:
        tr = self.transfers.get(trid)
        if not tr:
            return {"status": "failed", "output": f"transfer {trid} not found"}
        if tr.status != "pending":
            return {"status": "failed", "output": f"only pending transfers can be cancelled, current status is {tr.status}"}
        tr.status = "failed"
        return {"status": "ok", "output": self._tr_summary(tr)}

    def get_total_value_by_currency(self, currency: str) -> Dict:
        total = 0.0
        for w in self.wallets.values():
            if w.currency == currency:
                total += w.balance
        return {"status": "ok", "output": {"currency": currency, "total": round(total, 8)}}

    def list_by_currency(self, currency: str) -> Dict:
        items = [w for w in self.wallets.values() if w.currency == currency]
        items.sort(key=lambda w: w.name)
        return {"status": "ok", "output": [asdict(w) for w in items]}

    def search_transfers(self, query: str) -> Dict:
        q = query.lower()
        items = [tr for tr in self.transfers.values()
                 if q in tr.memo.lower() or q in tr.from_wid.lower() or q in tr.to_wid.lower()]
        items.sort(key=lambda tr: tr.timestamp, reverse=True)
        return {"status": "ok", "output": [self._tr_summary(tr) for tr in items]}

    def get_wallet_history(self, wid: str, limit: int = 10) -> Dict:
        if wid not in self.wallets:
            return {"status": "failed", "output": f"wallet {wid} not found"}
        items = [tr for tr in self.transfers.values()
                 if tr.from_wid == wid or tr.to_wid == wid]
        items.sort(key=lambda tr: tr.timestamp, reverse=True)
        return {"status": "ok", "output": [self._tr_summary(tr) for tr in items[:limit]]}

    def get_stats(self) -> Dict:
        by_kind: Dict[str, int] = {k: 0 for k in WALLET_KINDS}
        by_currency: Dict[str, float] = {}
        by_status: Dict[str, int] = {s: 0 for s in TRANSFER_STATUSES}
        for w in self.wallets.values():
            by_kind[w.kind] = by_kind.get(w.kind, 0) + 1
            by_currency[w.currency] = round(by_currency.get(w.currency, 0.0) + w.balance, 8)
        for tr in self.transfers.values():
            by_status[tr.status] = by_status.get(tr.status, 0) + 1
        return {
            "status": "ok",
            "output": {
                "wallets": len(self.wallets),
                "transfers": len(self.transfers),
                "by_kind": by_kind,
                "balances_by_currency": by_currency,
                "transfers_by_status": by_status,
            },
        }
