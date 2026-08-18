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


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _opt_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class BinanceSession:
    """Deterministic sandbox for the Binance Spot mock, ported from the FastAPI service.

    Covers symbol price ticker, 24hr ticker, order book depth, klines (candles) and
    account balances. Numeric fields are rendered as Binance-style 8-decimal strings.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "binance.yaml") as f:
                info = yaml.safe_load(f)

            self.prices: List[Dict[str, Any]] = [
                {
                    "symbol": r["symbol"],
                    "price": _opt_float(r.get("price")),
                    "priceChange": _opt_float(r.get("priceChange")),
                    "priceChangePercent": _opt_float(r.get("priceChangePercent")),
                    "highPrice": _opt_float(r.get("highPrice")),
                    "lowPrice": _opt_float(r.get("lowPrice")),
                    "volume": _opt_float(r.get("volume")),
                }
                for r in info.get("prices", [])
            ]
            self.klines: List[Dict[str, Any]] = [
                {
                    "symbol": r["symbol"],
                    "interval": r["interval"],
                    "open_time": _to_int(r.get("open_time")),
                    "open": _opt_float(r.get("open")),
                    "high": _opt_float(r.get("high")),
                    "low": _opt_float(r.get("low")),
                    "close": _opt_float(r.get("close")),
                    "volume": _opt_float(r.get("volume")),
                    "close_time": _to_int(r.get("close_time")),
                }
                for r in info.get("klines", [])
            ]
            self.balances: List[Dict[str, Any]] = [
                {
                    "asset": r["asset"],
                    "free": _opt_float(r.get("free")),
                    "locked": _opt_float(r.get("locked")),
                }
                for r in info.get("balances", [])
            ]
            self.depth: List[Dict[str, Any]] = [
                {
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "price": _opt_float(r.get("price")),
                    "qty": _opt_float(r.get("qty")),
                }
                for r in info.get("depth", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightBinance')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"prices": self.prices}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _fmt(self, v) -> str:
        return f"{_to_float(v):.8f}"

    # --- Ticker price ------------------------------------------------------
    def get_ticker_price(self, symbol: str | None = None) -> Dict[str, Any]:
        if symbol:
            p = next((x for x in self.prices if x["symbol"] == symbol.upper()), None)
            if not p:
                return {"status": "failed", "output": "Invalid symbol."}
            return {"status": "ok", "output": {"symbol": p["symbol"], "price": self._fmt(p["price"])}}
        return {"status": "ok", "output": [
            {"symbol": p["symbol"], "price": self._fmt(p["price"])} for p in self.prices
        ]}

    # --- 24hr ticker -------------------------------------------------------
    def _ticker_24hr_view(self, p):
        return {
            "symbol": p["symbol"],
            "priceChange": self._fmt(p["priceChange"]),
            "priceChangePercent": f"{p['priceChangePercent']:.3f}",
            "lastPrice": self._fmt(p["price"]),
            "highPrice": self._fmt(p["highPrice"]),
            "lowPrice": self._fmt(p["lowPrice"]),
            "volume": self._fmt(p["volume"]),
        }

    def get_ticker_24hr(self, symbol: str | None = None) -> Dict[str, Any]:
        if symbol:
            p = next((x for x in self.prices if x["symbol"] == symbol.upper()), None)
            if not p:
                return {"status": "failed", "output": "Invalid symbol."}
            return {"status": "ok", "output": self._ticker_24hr_view(p)}
        return {"status": "ok", "output": [self._ticker_24hr_view(p) for p in self.prices]}

    # --- Order book depth --------------------------------------------------
    def get_depth(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        sym = (symbol or "").upper()
        levels = [d for d in self.depth if d["symbol"] == sym]
        if not levels:
            return {"status": "failed", "output": "Invalid symbol."}
        bids = sorted((d for d in levels if d["side"] == "bid"), key=lambda d: d["price"], reverse=True)
        asks = sorted((d for d in levels if d["side"] == "ask"), key=lambda d: d["price"])
        bids = bids[:limit]
        asks = asks[:limit]
        return {"status": "ok", "output": {
            "lastUpdateId": 1027024,
            "bids": [[self._fmt(b["price"]), self._fmt(b["qty"])] for b in bids],
            "asks": [[self._fmt(a["price"]), self._fmt(a["qty"])] for a in asks],
        }}

    # --- Klines / candlesticks --------------------------------------------
    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> Dict[str, Any]:
        sym = (symbol or "").upper()
        candles = [k for k in self.klines if k["symbol"] == sym and k["interval"] == interval]
        if not candles:
            return {"status": "failed", "output": "Invalid symbol."}
        candles = sorted(candles, key=lambda k: k["open_time"])[:limit]
        out = []
        for k in candles:
            out.append([
                k["open_time"],
                self._fmt(k["open"]),
                self._fmt(k["high"]),
                self._fmt(k["low"]),
                self._fmt(k["close"]),
                self._fmt(k["volume"]),
                k["close_time"],
                self._fmt(k["close"] * k["volume"]),
                0,
                "0",
                "0",
                "0",
            ])
        return {"status": "ok", "output": out}

    # --- Account -----------------------------------------------------------
    def get_account(self) -> Dict[str, Any]:
        balances = [
            {"asset": b["asset"], "free": self._fmt(b["free"]), "locked": self._fmt(b["locked"])}
            for b in self.balances
        ]
        return {"status": "ok", "output": {
            "makerCommission": 10,
            "takerCommission": 10,
            "buyerCommission": 0,
            "sellerCommission": 0,
            "canTrade": True,
            "canWithdraw": True,
            "canDeposit": True,
            "accountType": "SPOT",
            "balances": balances,
            "permissions": ["SPOT"],
        }}


if __name__ == "__main__":
    s = BinanceSession(seed=12)
    print(s.get_ticker_price())
    print(s.get_account())
