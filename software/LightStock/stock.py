from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Set, Tuple, Literal
from collections import defaultdict
import random
import yaml
from pathlib import Path
import sys

WORK_DIR = Path('.')
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR.__str__())

from software.utils.time import TimeMachine
from software.utils.core import OSConnector, DummyOSConnector, uuid_rng
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed

@dataclass
class Stock:
    ticker: str
    name: str
    price: float
    sector: str
    description: str = ""
    pe_ratio: float = 0.0
    market_cap: str = "0B"

@dataclass
class Position:
    ticker: str
    quantity: int  # 正数为多头，负数为空头
    avg_price: float

@dataclass
class PendingOrder:
    oid: str
    ticker: str
    side: str  # "buy" or "sell"
    quantity: int
    price_type: str  # "limit", "stop_loss"
    limit_price: float = 0.0
    frozen_margin: float = 0.0

@dataclass
class StockTransaction:
    timestamp: str
    trid: str
    ticker: str
    side: str
    quantity: int
    price: float
    total_amount: float
    fee: float

CORPUS_PATH = Path("software") / "LightStock" / "corpus"

class StockSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.time_machine = TimeMachine(rng=self.rng)
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

            self.stocks: Dict[str, Stock] = self.init_stocks() # {tocker: Stock}
            self.market_open = self.rng.choice([True, True, False]) # 模拟非交易时段

            self.trading_balance = self.rng.randint(10000, 50000)
            self.savings_balance = self.rng.randint(50000, 150000)
            self.frozen_margin = 0.0
            self.user_tier: Literal["Basic", "VIP"] = self.rng.choice(["Basic", "VIP"]) # VIP 才能做空和止损
            self.day_trades_remaining = self.rng.randint(1, 3)

            self.portfolio: Dict[str, Position] = {} # {ticker : position}
            self.pending_orders: List[PendingOrder] = []
            self.trade_history: List[StockTransaction] = []
            self.watchlist: Set[str] = set()
            self.price_alerts: Dict[str, float] = {}

            self.fee_rate = 0.002 * self.rng.uniform(0.5, 1.5)
            self.vip_fee = 8000

            self.__mock_environment()
            self.password_verified = False
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightStock')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    @staticmethod
    def require_market_open(func):
        def wrapper(self: 'StockSession', *args, **kwargs):
            if not self.market_open:
                return {
                    "status": "failed",
                    "output": "The market is currently closed for trading"
                }
            return func(self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def require_vip(func):
        def wrapper(self: 'StockSession', *args, **kwargs):
            if self.user_tier != "VIP":
                return {
                    "status": "failed",
                    "output": "This operation need VIP"
                }
            return func(self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def require_password(func):
        def wrapper(self: 'StockSession', *args, **kwargs):
            if not self.password_verified:
                return {
                    "status": "failed",
                    "output": "Please enter the trading password first"
                }
            self.password_verified = False
            return func(self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def require_trade_cnt(func):
        def wrapper(self: 'StockSession', *args, **kwargs):
            if self.user_tier != "VIP" and self.day_trades_remaining == 0:
                return {
                    "status": "failed",
                    "output": "Daily trade limit reached. No remaining quota for today. Please upgrade to VIP to unlock unlimited trading."
                }
            return func(self, *args, **kwargs)
        
        return wrapper

    def init_stocks(self):
        stocks: Dict[str, Stock] = {}
        with open(CORPUS_PATH / "stock.yaml") as f:
            _stocks = yaml.safe_load(f)["stocks"]
            for _stock in _stocks:
                ticker = _stock["ticker"]
                name = _stock["name"]
                price = round(_stock["price"] * self.rng.uniform(0.8, 1.6), 2)
                sector = _stock["sector"]
                description = _stock["description"]
                pe_ratio = round(_stock["pe_ratio"] * self.rng.uniform(0.9, 1.1), 2)
                market_cap = round(float(_stock["market_cap"][:-1]) * self.rng.uniform(0.9, 1.4), 2).__str__() + _stock["market_cap"][-1]

                stock = Stock(
                    ticker=ticker, name=name, price=price, sector=sector,
                    description=description, pe_ratio=pe_ratio,
                    market_cap=market_cap
                )

                stocks[ticker] = stock
        
        return stocks

    def __mock_environment(self):
        if self.rng.uniform(0, 1) < 0.5:
            return
        tickers = self.rng.choices(list(self.stocks.keys()), k=self.rng.randint(1, 3))
        for ticker in tickers:
            self.day_trades_remaining += 1
            self.wait_trade_password()
            self.place_market_order(ticker, side="buy", quantity=self.rng.randint(1, 15))
        
        limit_stock = self.rng.choice(list(self.stocks.values()))
        self.day_trades_remaining += 1
        self.wait_trade_password()
        self.place_limit_order(ticker=limit_stock.ticker, side="buy", quantity=self.rng.randint(10, 100), limit_price=round(limit_stock.price * self.rng.uniform(0.85, 0.97), 2))
        

    def get_session_dict(self):
        portfolio = [asdict(pos) for pos in self.portfolio.values()]
        portfolio.sort(key=lambda x: x["ticker"])

        pending_orders = [asdict(order) for order in self.pending_orders]
        pending_orders.sort(key=lambda x: (x["ticker"], x["side"], x["quantity"]))

        trade_history = [asdict(trade) for trade in self.trade_history]
        trade_history.sort(key=lambda x: (x["ticker"], x["side"], x["quantity"]))

        return {
            "user": {
                "tier": self.user_tier,
                "trading_balance": self.trading_balance,
                "savings_balance": self.savings_balance,
                "frozen_margin": self.frozen_margin
            },
            "stocks": {
                "portfolio": portfolio,
                "pending_orders": pending_orders,
                "trade_history": trade_history,
                "watch_list": sorted(list(self.watchlist)),
                "price_alerts": self.price_alerts
            }
        }

    def uuid(self, prefix: str):
        return f"{prefix}_{uuid_rng(self.rng)}"
    
    def get_account_summary(self): 
        return {
            "status": "ok",
            "output": {
                "tier": self.user_tier,
                "trading balance": self.trading_balance,
                "savings balance": self.savings_balance,
                "frozen margin": self.frozen_margin
            }
        }
    
    def list_all_sectors(self): 
        sectors = sorted(list(set(s.sector for s in self.stocks.values())))

        return {"status": "ok", "output": sectors}
    
    def list_all_tickers_by_sector(self, sector: str): 
        sector = sector.lower().strip()
        results = [s.ticker for s in self.stocks.values() if s.sector.lower() == sector]

        return {
            "status": "ok",
            "output": results
        }
    
    def search_stocks(self, query: str): 
        query = query.lower()
        results = []
        for s in self.stocks.values():
            if query in s.ticker.lower() or query in s.name.lower():
                results.append({"ticker": s.ticker, "name": s.name, "price": s.price})
        return {"status": "ok", "output": results}
    
    def get_stock_details(self, ticker: str): 
        stock = self.stocks.get(ticker.upper())
        if not stock:
            return {"status": "failed", "output": f"Ticker {ticker} not found"}
        return {"status": "ok", "output": asdict(stock)}
    
    def wait_trade_password(self): 
        self.password_verified = True
        return {
            "status": "ok",
            "output": "The user has enterred the correct password"
        }
    
    def transfer_funds(self, amount: float, direction: Literal["s2t", "t2s"]): 
        if direction == "s2t":
            if self.savings_balance < amount:
                return {"status": "failed", "output": "Insufficient savings balance."}
            self.savings_balance -= amount
            self.trading_balance += amount
        else:
            if self.trading_balance < amount:
                return {"status": "failed", "output": "Insufficient trading balance."}
            self.trading_balance -= amount
            self.savings_balance += amount

        return {"status": "ok", "output": f"Transferred {amount} successfully."}
    
    @require_market_open
    @require_password
    @require_trade_cnt
    def place_market_order(self, ticker: str, side: Literal["buy", "sell"], quantity: int): 
        """市价单：直接按当前价格成交"""
        
        ticker = ticker.upper()
        stock = self.stocks.get(ticker)
        if not stock: return {"status": "failed", "output": "Invalid ticker"}

        total_price = stock.price * quantity
        fee = round(min(self.fee_rate * total_price, 100), 2)
        
        if side == "buy":
            available_cash = self.trading_balance - self.frozen_margin
            if available_cash < (total_price + fee):
                return {"status": "failed", "output": f"Insufficient available cash. You have {self.trading_balance}$ in total, and {self.frozen_margin}$ is frozen by pending orders."}
            
            self.trading_balance -= (total_price + fee)
            # 更新持仓
            pos = self.portfolio.get(ticker, Position(ticker, 0, 0))
            new_qty = pos.quantity + quantity
            new_avg = (pos.avg_price * pos.quantity + total_price) / new_qty
            self.portfolio[ticker] = Position(ticker, new_qty, round(new_avg, 2))
        
        else: # Sell
            pos = self.portfolio.get(ticker)
            # 如果没有持仓且不是 VIP，禁止做空
            if (not pos or pos.quantity < quantity) and self.user_tier != "VIP":
                return {"status": "failed", "output": "Short selling is only available for VIP users."}
            
            self.trading_balance += (total_price - fee)
            current_qty = pos.quantity if pos else 0
            self.portfolio[ticker] = Position(ticker, current_qty - quantity, pos.avg_price if pos else stock.price)

        # 记录交易
        tx = StockTransaction(self.os.step(), self.uuid("trans"), ticker, side, quantity, stock.price, total_price, fee)
        self.trade_history.append(tx)

        if self.user_tier != "VIP":
            self.day_trades_remaining -= 1

        return {"status": "ok", "output": f"Market order executed. {side} {quantity} shares of {ticker}, fee: {fee}$"}
    
    @require_market_open
    @require_password
    @require_trade_cnt
    def place_limit_order(self, ticker: str, side: Literal["buy", "sell"], quantity: int, limit_price: float): 
            
        total_cost = limit_price * quantity
        # 核心陷阱：可用余额检查
        available_cash = self.trading_balance - self.frozen_margin
        
        if side == "buy":
            if available_cash < total_cost:
                return {
                    "status": "failed", 
                    "output": f"Insufficient available cash. Total: {self.trading_balance}$, Frozen: {self.frozen_margin}$, Needed: {total_cost}$"
                }
            # 只增加冻结计数，不直接扣除总余额
            self.frozen_margin += total_cost

        oid = self.uuid("order")
        new_order = PendingOrder(oid, ticker.upper(), side, quantity, "limit", limit_price, total_cost if side == "buy" else 0)
        self.pending_orders.append(new_order)

        if self.user_tier != "VIP":
            self.day_trades_remaining -= 1

        return {"status": "ok", "output": f"Limit order {oid} placed. {total_cost} is now frozen."}
    
    @require_market_open
    @require_password
    @require_trade_cnt
    @require_vip
    def place_stop_loss_order(self, ticker: str, quantity: int, stop_price: float):
        """
        [VIP 专享] 设置一个止损单。
        当股价跌至或低于 stop_price 时，系统将自动以市价卖出。
        """
        ticker = ticker.upper()
        if ticker not in self.stocks:
            return {"status": "failed", "output": "Invalid ticker."}

        # 1. 逻辑检查：止损价格必须低于当前价格（否则下单就会被立刻触发）
        current_price = self.stocks[ticker].price
        if stop_price >= current_price:
            return {
                "status": "failed",
                "output": f"Stop price ({stop_price}) must be lower than the current price ({current_price})."
            }

        # 2. 持仓检查：你得先有这只股票才能设止损（或者至少该动作是合理的）
        pos = self.portfolio.get(ticker)
        if not pos or pos.quantity < quantity:
            return {
                "status": "failed",
                "output": f"You don't have enough shares of {ticker} to set a stop-loss. Current: {pos.quantity if pos else 0}"
            }

        # 3. 创建止损挂单
        oid = self.uuid("order")
        new_order = PendingOrder(
            oid=oid,
            ticker=ticker,
            side="sell",      # 止损通常是卖出
            quantity=quantity,
            price_type="stop_loss",
            limit_price=stop_price, # 这里的字段借用来存触发价
            frozen_margin=0.0       # 止损单卖出通常不冻结现金
        )
        
        self.pending_orders.append(new_order)

        if self.user_tier != "VIP":
            self.day_trades_remaining -= 1
        
        return {
            "status": "ok",
            "output": f"Stop-loss order {oid} for {ticker} set at {stop_price}. It will trigger automatically if the price drops."
        }

    def get_portfolio(self): 
        if not self.portfolio:
            return {"status": "ok", "output": "You currently hold no positions."}
        return {"status": "ok", "output": [asdict(p) for p in self.portfolio.values()]}

    def get_pending_orders(self): 
        if not self.pending_orders:
            return {"status": "ok", "output": "No pending orders."}
        return {"status": "ok", "output": [asdict(o) for o in self.pending_orders]}

    def cancel_order(self, oid: str): 
        for i, order in enumerate(self.pending_orders):
            if order.oid == oid:
                # 释放冻结资金
                if order.side == "buy":
                    self.trading_balance += order.frozen_margin
                    self.frozen_margin -= order.frozen_margin
                self.pending_orders.pop(i)
                return {"status": "ok", "output": f"Order {oid} cancelled successfully."}
        return {"status": "failed", "output": "Order ID not found."}

    def get_trade_history(self): 
        return {"status": "ok", "output": [asdict(t) for t in self.trade_history]}

    def toggle_watchlist(self, ticker: str): 
        ticker = ticker.upper()
        if ticker not in self.stocks: return {"status": "failed", "output": "Invalid ticker"}
        
        if ticker in self.watchlist:
            self.watchlist.remove(ticker)
            msg = f"Removed {ticker} from watchlist."
        else:
            self.watchlist.add(ticker)
            msg = f"Added {ticker} to watchlist."
        return {"status": "ok", "output": msg}

    def get_watchlist_details(self): 
        res = []
        for t in self.watchlist:
            s = self.stocks[t]
            res.append({"ticker": t, "price": s.price, "pe": s.pe_ratio})
        return {"status": "ok", "output": res}
    
    def check_vip_price(self):
        return {
            "status": "ok",
            "output": self.vip_fee
        }
    
    @require_password
    def upgrade_to_vip(self): 
        if self.user_tier == "VIP":
            return {
                "status": "failed",
                "output": "You are already a VIP member. No further upgrade is required."
            }

        fee = self.vip_fee
        available_cash = self.trading_balance - self.frozen_margin
        
        if available_cash < fee:
            if self.trading_balance >= fee:
                return {
                    "status": "failed",
                    "output": (f"Insufficient available cash to upgrade. Your total balance is {self.trading_balance}, "
                               f"and {self.frozen_margin} is frozen by pending orders. "
                               f"Please cancel some orders or transfer funds from savings.")
                }
            else:
                return {
                    "status": "failed",
                    "output": f"Insufficient funds. The VIP upgrade requires {fee}$, but your trading balance is {self.trading_balance}$."
                }

        self.trading_balance -= fee
        self.user_tier = "VIP"

        return {
            "status": "ok",
            "output": f"Congratulations! You have successfully upgraded to VIP. {fee}$ has been deducted from your balance."
        }
    
    def get_day_trades_remaining(self):
        if self.user_tier == "Basic":
            return {
                "status": "ok",
                "output": self.day_trades_remaining
            }
        else:
            return {
                "status": "ok",
                "output": "Unlimited"
            }

    def set_price_alert(self, ticker: str, price: float):
        if ticker not in self.stocks:
            return {
                "status": "failed",
                "output": f"Ticker {ticker} not found"
            }
        self.price_alerts[ticker] = price

        return {
            "status": "ok",
            "output": f"You have succussfully set one price alert: {ticker} ({price})"
        }
    
    def remove_price_alert(self, ticker: str):
        if ticker not in self.price_alerts:
            return {
                "status": "failed",
                "output": f"Ticker {ticker} not in alert table"
            }
        price = self.price_alerts.pop(ticker)

        return {
            "status": "ok",
            "output": f"You have succussfully removed one price alert: {ticker} ({price})"
        }
    
    
if __name__ == "__main__":
    stock_session = StockSession(seed=41, os_cfg=None)

    print(stock_session.get_pending_orders())
    print(stock_session.get_portfolio())
