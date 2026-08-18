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


def _strict_int(v) -> int:
    return int(str(v).strip())


class KrakenSession:
    """Deterministic sandbox for the Kraken mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read the in-memory
    tables so repeated calls within a session stay consistent. Mirrors a subset of
    the Kraken REST API (Ticker, OHLC, AssetPairs, Assets, Balance) and returns the
    Light envelope {"status": "ok"/"failed", "output": ...}.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "kraken.yaml") as f:
                info = yaml.safe_load(f)

            self.tickers: List[Dict[str, Any]] = [
                {
                    "pair": r["pair"],
                    "altname": r["altname"],
                    "ask": r["ask"],
                    "bid": r["bid"],
                    "last": r["last"],
                    "volume": r["volume"],
                    "high": r["high"],
                    "low": r["low"],
                    "open": r["open"],
                }
                for r in info.get("tickers", [])
            ]
            self.ohlc: List[Dict[str, Any]] = [
                {
                    "pair": r["pair"],
                    "time": _strict_int(r["time"]),
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "vwap": r["vwap"],
                    "volume": r["volume"],
                    "count": _strict_int(r["count"]),
                }
                for r in info.get("ohlc", [])
            ]
            self.pairs: List[Dict[str, Any]] = [
                {
                    "pair": r["pair"],
                    "altname": r["altname"],
                    "wsname": r["wsname"],
                    "base": r["base"],
                    "quote": r["quote"],
                    "pair_decimals": _strict_int(r["pair_decimals"]),
                    "lot_decimals": _strict_int(r["lot_decimals"]),
                    "ordermin": r["ordermin"],
                    "status": r["status"],
                }
                for r in info.get("pairs", [])
            ]
            self.assets: List[Dict[str, Any]] = [
                {
                    "asset": r["asset"],
                    "altname": r["altname"],
                    "aclass": r["aclass"],
                    "decimals": _strict_int(r["decimals"]),
                    "display_decimals": _strict_int(r["display_decimals"]),
                }
                for r in info.get("assets", [])
            ]
            self.balances: List[Dict[str, Any]] = [
                {"asset": r["asset"], "balance": r["balance"]} for r in info.get("balances", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightKraken')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"balances": self.balances}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _resolve_pair(self, pair):
        """Resolve a pair by canonical name or altname (case-insensitive)."""
        if not pair:
            return None
        p = pair.strip().upper()
        for t in self.tickers:
            if t["pair"].upper() == p or t["altname"].upper() == p:
                return t["pair"]
        return None

    # --- API methods -------------------------------------------------------
    def get_ticker(self, pair: str | None = None) -> Dict[str, Any]:
        requested = [p.strip() for p in pair.split(",")] if pair else None
        if not requested:
            requested = [t["altname"] for t in self.tickers]
        result = {}
        for req in requested:
            canonical = self._resolve_pair(req)
            if not canonical:
                return {"status": "failed", "output": f"Unknown asset pair: {req}"}
            t = next(t for t in self.tickers if t["pair"] == canonical)
            result[canonical] = {
                "a": [t["ask"], "1", "1.000"],
                "b": [t["bid"], "1", "1.000"],
                "c": [t["last"], "0.10000000"],
                "v": [t["volume"], t["volume"]],
                "h": [t["high"], t["high"]],
                "l": [t["low"], t["low"]],
                "o": t["open"],
            }
        return {"status": "ok", "output": result}

    def get_ohlc(self, pair: str, interval: int = 60) -> Dict[str, Any]:
        canonical = self._resolve_pair(pair)
        if not canonical:
            return {"status": "failed", "output": f"Unknown asset pair: {pair}"}
        candles = [c for c in self.ohlc if c["pair"] == canonical]
        candles = sorted(candles, key=lambda c: c["time"])
        rows = [
            [c["time"], c["open"], c["high"], c["low"], c["close"],
             c["vwap"], c["volume"], c["count"]]
            for c in candles
        ]
        last = candles[-1]["time"] if candles else 0
        result = {canonical: rows, "last": last}
        return {"status": "ok", "output": result}

    def get_asset_pairs(self, pair: str | None = None) -> Dict[str, Any]:
        pairs = self.pairs
        if pair:
            requested = {p.strip().upper() for p in pair.split(",")}
            pairs = [
                p for p in self.pairs
                if p["pair"].upper() in requested or p["altname"].upper() in requested
            ]
            if not pairs:
                return {"status": "failed", "output": f"Unknown asset pair: {pair}"}
        result = {}
        for p in pairs:
            result[p["pair"]] = {
                "altname": p["altname"],
                "wsname": p["wsname"],
                "aclass_base": "currency",
                "base": p["base"],
                "aclass_quote": "currency",
                "quote": p["quote"],
                "pair_decimals": p["pair_decimals"],
                "lot_decimals": p["lot_decimals"],
                "ordermin": p["ordermin"],
                "status": p["status"],
            }
        return {"status": "ok", "output": result}

    def get_assets(self, asset: str | None = None) -> Dict[str, Any]:
        assets = self.assets
        if asset:
            requested = {a.strip().upper() for a in asset.split(",")}
            assets = [
                a for a in self.assets
                if a["asset"].upper() in requested or a["altname"].upper() in requested
            ]
            if not assets:
                return {"status": "failed", "output": f"Unknown asset: {asset}"}
        result = {}
        for a in assets:
            result[a["asset"]] = {
                "aclass": a["aclass"],
                "altname": a["altname"],
                "decimals": a["decimals"],
                "display_decimals": a["display_decimals"],
            }
        return {"status": "ok", "output": result}

    def get_balance(self) -> Dict[str, Any]:
        result = {b["asset"]: b["balance"] for b in self.balances}
        return {"status": "ok", "output": result}


if __name__ == "__main__":
    s = KrakenSession(seed=12)
    print(s.get_ticker("XBTUSD"))
    print(s.get_balance())
