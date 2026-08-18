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


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class AlpacaSession:
    """Deterministic sandbox for the Alpaca trading mock, ported from the FastAPI service.

    Numeric fields are returned as strings to match Alpaca's JSON conventions.
    Buy orders validate buying power; sell orders validate the held position.
    Mutations persist within the session.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "alpaca.yaml") as f:
                info = yaml.safe_load(f)

            self.account: Dict[str, Any] = dict(info.get("account", {}))
            self.positions: List[Dict[str, Any]] = self._coerce_positions(info.get("positions", []))
            self.orders: List[Dict[str, Any]] = self._coerce_orders(info.get("orders", []))
            self.assets: List[Dict[str, Any]] = self._coerce_assets(info.get("assets", []))
            self.quotes: Dict[str, Any] = self._coerce_quotes(info.get("quotes", []))
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAlpaca')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"orders": self.orders, "positions": self.positions}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _coerce_positions(self, rows):
        out = []
        for r in rows:
            out.append({
                "asset_id": r["asset_id"],
                "symbol": r["symbol"],
                "qty": r["qty"],
                "avg_entry_price": r["avg_entry_price"],
                "current_price": r["current_price"],
                "side": r["side"],
                "market_value": r["market_value"],
                "cost_basis": r["cost_basis"],
                "unrealized_pl": r["unrealized_pl"],
                "asset_class": "us_equity",
                "exchange": "NASDAQ",
            })
        return out

    def _coerce_orders(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "client_order_id": r["client_order_id"],
                "symbol": r["symbol"],
                "qty": r["qty"],
                "filled_qty": r["filled_qty"],
                "side": r["side"],
                "type": r["type"],
                "time_in_force": r["time_in_force"],
                "limit_price": (str(r.get("limit_price", "")) or None),
                "status": r["status"],
                "filled_avg_price": (str(r.get("filled_avg_price", "")) or None),
                "submitted_at": r["submitted_at"],
                "filled_at": (str(r.get("filled_at", "")) or None),
            })
        return out

    def _coerce_assets(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "symbol": r["symbol"],
                "name": r["name"],
                "exchange": r["exchange"],
                "class": r["asset_class"],
                "tradable": _to_bool(r["tradable"]),
                "fractionable": _to_bool(r["fractionable"]),
                "status": "active",
            })
        return out

    def _coerce_quotes(self, rows):
        quotes = {}
        for r in rows:
            quotes[r["symbol"]] = {
                "t": r["timestamp"],
                "bp": _to_float(r.get("bid_price"), default=0.0),
                "bs": int(_to_float(r.get("bid_size"), default=0.0)),
                "ap": _to_float(r.get("ask_price"), default=0.0),
                "as": int(_to_float(r.get("ask_size"), default=0.0)),
            }
        return quotes

    def _new_order_id(self):
        return f"ORD-{self.uuid()}"

    def _find_position(self, symbol):
        return next((p for p in self.positions if p["symbol"] == symbol.upper()), None)

    def _find_asset(self, symbol):
        return next((a for a in self.assets if a["symbol"] == symbol.upper()), None)

    def _ref_price(self, symbol):
        q = self.quotes.get(symbol.upper())
        if q:
            return q["ap"]
        pos = self._find_position(symbol)
        if pos:
            return _to_float(pos["current_price"])
        return 0.0

    # --- API methods -------------------------------------------------------
    def get_account(self) -> Dict[str, Any]:
        return {"status": "ok", "output": dict(self.account)}

    def list_positions(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.positions)}

    def get_position(self, symbol: str) -> Dict[str, Any]:
        p = self._find_position(symbol)
        if not p:
            return {"status": "failed", "output": f"position not found for {symbol.upper()}"}
        return {"status": "ok", "output": p}

    def list_orders(self, status: str | None = None) -> Dict[str, Any]:
        results = list(self.orders)
        if status and status != "all":
            if status == "open":
                results = [o for o in results if o["status"] in ("new", "accepted", "partially_filled")]
            elif status == "closed":
                results = [o for o in results if o["status"] in ("filled", "canceled", "expired")]
            else:
                results = [o for o in results if o["status"] == status]
        return {"status": "ok", "output": results}

    def get_order(self, order_id: str) -> Dict[str, Any]:
        o = next((o for o in self.orders if o["id"] == order_id), None)
        if not o:
            return {"status": "failed", "output": f"order not found: {order_id}"}
        return {"status": "ok", "output": o}

    def create_order(self, symbol: str, qty: float, side: str, type: str = "market",
                     time_in_force: str = "day", limit_price: float | None = None) -> Dict[str, Any]:
        symbol = (symbol or "").upper()
        side = (side or "").lower()
        if side not in ("buy", "sell"):
            return {"status": "failed", "output": "side must be 'buy' or 'sell'"}
        asset = self._find_asset(symbol)
        if not asset:
            return {"status": "failed", "output": f"asset not found: {symbol}"}
        if not asset["tradable"]:
            return {"status": "failed", "output": f"asset {symbol} is not tradable"}
        qty_f = _to_float(qty)
        if qty_f <= 0:
            return {"status": "failed", "output": "qty must be positive"}

        price = _to_float(limit_price) if limit_price else self._ref_price(symbol)

        if side == "buy":
            cost = price * qty_f
            buying_power = _to_float(self.account["buying_power"])
            if cost > buying_power:
                return {"status": "failed",
                        "output": f"insufficient buying power: need {cost:.2f}, have {buying_power:.2f}"}
        else:  # sell
            pos = self._find_position(symbol)
            held = _to_float(pos["qty"]) if pos else 0.0
            if qty_f > held:
                return {"status": "failed",
                        "output": f"insufficient qty available: requested {qty_f:.0f}, held {held:.0f}"}

        order = {
            "id": self._new_order_id(),
            "client_order_id": f"cli-{self.uuid()}",
            "symbol": symbol,
            "qty": str(int(qty_f)) if qty_f.is_integer() else str(qty_f),
            "filled_qty": "0",
            "side": side,
            "type": type or "market",
            "time_in_force": time_in_force or "day",
            "limit_price": str(limit_price) if limit_price else None,
            "status": "new",
            "filled_avg_price": None,
            "submitted_at": self._now(),
            "filled_at": None,
        }
        self.orders.append(order)
        return {"status": "ok", "output": order}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        o = next((o for o in self.orders if o["id"] == order_id), None)
        if not o:
            return {"status": "failed", "output": f"order not found: {order_id}"}
        if o["status"] in ("filled", "canceled", "expired"):
            return {"status": "failed", "output": f"order {order_id} is not cancelable (status {o['status']})"}
        o["status"] = "canceled"
        return {"status": "ok", "output": {"status": "canceled", "id": order_id}}

    def list_assets(self, status: str | None = None, asset_class: str | None = None) -> Dict[str, Any]:
        results = list(self.assets)
        if status:
            results = [a for a in results if a["status"] == status]
        if asset_class:
            results = [a for a in results if a["class"] == asset_class]
        return {"status": "ok", "output": results}

    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        q = self.quotes.get(symbol.upper())
        if not q:
            return {"status": "failed", "output": f"no quote for {symbol.upper()}"}
        return {"status": "ok", "output": {"symbol": symbol.upper(), "quote": q}}


if __name__ == "__main__":
    s = AlpacaSession(seed=12)
    print(s.get_account())
    print(s.list_positions())
