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


def _to_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class PlaidSession:
    """Deterministic sandbox for the Plaid mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read the in-memory
    tables so repeated calls within a session stay consistent. Plaid uses POST for
    reads, and each response carries a request_id derived from self.rng.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "plaid.yaml") as f:
                info = yaml.safe_load(f)

            self.accounts: List[Dict[str, Any]] = [
                {
                    "account_id": a["account_id"],
                    "name": a["name"],
                    "official_name": (str(a.get("official_name", "")) or None),
                    "mask": a["mask"],
                    "type": a["type"],
                    "subtype": a["subtype"],
                    "balances": {
                        "available": _to_float(a.get("available")),
                        "current": _to_float(a.get("current")),
                        "limit": _to_float(a.get("limit")),
                        "iso_currency_code": a["iso_currency_code"],
                        "unofficial_currency_code": None,
                    },
                }
                for a in info.get("accounts", [])
            ]

            self.transactions: List[Dict[str, Any]] = [
                {
                    "transaction_id": t["transaction_id"],
                    "account_id": t["account_id"],
                    "amount": _to_float(t.get("amount")),
                    "iso_currency_code": t["iso_currency_code"],
                    "date": t["date"],
                    "name": t["name"],
                    "merchant_name": (str(t.get("merchant_name", "")) or None),
                    "category": [c for c in str(t.get("category", "")).split(";") if c],
                    "pending": _to_bool(t.get("pending", False)),
                    "payment_channel": t["payment_channel"],
                }
                for t in info.get("transactions", [])
            ]

            self.item: Dict[str, Any] = dict(info.get("item", {}))
            self.identity: Dict[str, Any] = dict(info.get("identity", {}))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPlaid')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"accounts": self.accounts, "transactions": self.transactions}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _request_id(self) -> str:
        return self.uuid()

    # --- API methods -------------------------------------------------------
    def get_accounts(self, account_ids: List[str] | None = None) -> Dict[str, Any]:
        accounts = list(self.accounts)
        if account_ids:
            wanted = set(account_ids)
            accounts = [a for a in accounts if a["account_id"] in wanted]
        return {"status": "ok", "output": {
            "accounts": accounts,
            "item": self.item["item"],
            "request_id": self._request_id(),
        }}

    def get_balances(self, account_ids: List[str] | None = None) -> Dict[str, Any]:
        # Same shape as get_accounts; balances are embedded in each account.
        return self.get_accounts(account_ids=account_ids)

    def get_transactions(self, start_date: str | None = None, end_date: str | None = None,
                         account_ids: List[str] | None = None, count: int = 100,
                         offset: int = 0) -> Dict[str, Any]:
        txns = list(self.transactions)
        if account_ids:
            wanted = set(account_ids)
            txns = [t for t in txns if t["account_id"] in wanted]
        if start_date:
            txns = [t for t in txns if t["date"] >= start_date]
        if end_date:
            txns = [t for t in txns if t["date"] <= end_date]
        txns.sort(key=lambda t: t["date"], reverse=True)
        total = len(txns)
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0
        try:
            count = max(1, min(int(count), 500))
        except (TypeError, ValueError):
            count = 100
        page = txns[offset: offset + count]
        accounts = list(self.accounts)
        if account_ids:
            wanted = set(account_ids)
            accounts = [a for a in accounts if a["account_id"] in wanted]
        return {"status": "ok", "output": {
            "accounts": accounts,
            "transactions": page,
            "total_transactions": total,
            "item": self.item["item"],
            "request_id": self._request_id(),
        }}

    def get_institution_by_id(self, institution_id: str) -> Dict[str, Any]:
        inst = self.item["institution"]
        if institution_id != inst["institution_id"]:
            return {"status": "failed", "output": f"Unknown institution {institution_id}"}
        return {"status": "ok", "output": {
            "institution": inst,
            "request_id": self._request_id(),
        }}

    def get_identity(self, account_ids: List[str] | None = None) -> Dict[str, Any]:
        owners_map = self.identity.get("owners", {})
        accounts = []
        for a in self.accounts:
            if account_ids and a["account_id"] not in set(account_ids):
                continue
            owners = owners_map.get(a["account_id"], [])
            accounts.append({**a, "owners": owners})
        return {"status": "ok", "output": {
            "accounts": accounts,
            "item": self.item["item"],
            "request_id": self._request_id(),
        }}


if __name__ == "__main__":
    s = PlaidSession(seed=12)
    print(s.get_accounts())
    print(s.get_transactions(count=3))
