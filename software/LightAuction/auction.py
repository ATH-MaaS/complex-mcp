from typing import Dict, List, Optional
from pathlib import Path
import random, sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed

@dataclass
class Listing:
    lid: str
    title: str
    description: str
    seller: str
    starting_price: float
    current_price: float
    end_time: str
    status: str = "active"  # active|ended|cancelled
    category: str = "general"

@dataclass
class Bid:
    bid_id: str
    listing_id: str
    bidder: str
    amount: float
    ts: str

SEED_LISTINGS = [
    ("Vintage Watch", "Rolex 1972", "seller_a", 500.0, 24, "collectibles"),
    ("Baseball Card", "1952 Mickey Mantle", "seller_b", 1000.0, 48, "sports"),
    ("Art Print", "Signed print", "seller_c", 100.0, 12, "art"),
]

class AuctionSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.listings: Dict[str, Listing] = {}
            self.bids: Dict[str, Bid] = {}
            self.watchlist: List[str] = []
            self._seed()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightAuction')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _seed(self):
        base = datetime(2026, 1, 5, 12, 0, 0)
        for title, desc, seller, price, hours, cat in SEED_LISTINGS:
            end = (base + timedelta(hours=hours)).isoformat(timespec="minutes")
            L = Listing(lid=self.uuid(), title=title, description=desc, seller=seller,
                        starting_price=price, current_price=price, end_time=end, category=cat)
            self.listings[L.lid] = L

    def get_session_dict(self):
        return {
            "listings": {k: asdict(v) for k, v in self.listings.items()},
            "bids": {k: asdict(v) for k, v in self.bids.items()},
            "watchlist": list(self.watchlist),
        }

    def list_listings(self, status: Optional[str] = None, category: Optional[str] = None):
        out = []
        for L in self.listings.values():
            if status and L.status != status: continue
            if category and L.category != category: continue
            out.append(asdict(L))
        return {"status": "ok", "output": out}

    def get_listing(self, lid: str):
        L = self.listings.get(lid)
        if not L: return {"status": "failed", "output": f"listing {lid} not found"}
        return {"status": "ok", "output": asdict(L)}

    def create_listing(self, title: str, description: str, seller: str, starting_price: float, end_time: str, category: str = "general"):
        L = Listing(lid=self.uuid(), title=title, description=description, seller=seller,
                    starting_price=starting_price, current_price=starting_price, end_time=end_time, category=category)
        self.listings[L.lid] = L
        return {"status": "ok", "output": asdict(L)}

    def cancel_listing(self, lid: str):
        L = self.listings.get(lid)
        if not L: return {"status": "failed", "output": f"listing {lid} not found"}
        L.status = "cancelled"
        return {"status": "ok", "output": asdict(L)}

    def end_listing(self, lid: str):
        L = self.listings.get(lid)
        if not L: return {"status": "failed", "output": f"listing {lid} not found"}
        L.status = "ended"
        return {"status": "ok", "output": asdict(L)}

    def place_bid(self, listing_id: str, bidder: str, amount: float):
        L = self.listings.get(listing_id)
        if not L: return {"status": "failed", "output": "listing not found"}
        if L.status != "active": return {"status": "failed", "output": "listing not active"}
        if amount <= L.current_price: return {"status": "failed", "output": "bid must exceed current price"}
        b = Bid(bid_id=self.uuid(), listing_id=listing_id, bidder=bidder, amount=amount,
                ts=self.os.now())
        self.bids[b.bid_id] = b
        L.current_price = amount
        return {"status": "ok", "output": asdict(b)}

    def list_bids(self, listing_id: Optional[str] = None, bidder: Optional[str] = None):
        out = []
        for b in self.bids.values():
            if listing_id and b.listing_id != listing_id: continue
            if bidder and b.bidder != bidder: continue
            out.append(asdict(b))
        return {"status": "ok", "output": out}

    def get_bid(self, bid_id: str):
        b = self.bids.get(bid_id)
        if not b: return {"status": "failed", "output": "bid not found"}
        return {"status": "ok", "output": asdict(b)}

    def highest_bid(self, listing_id: str):
        matches = [b for b in self.bids.values() if b.listing_id == listing_id]
        if not matches: return {"status": "ok", "output": None}
        top = max(matches, key=lambda b: b.amount)
        return {"status": "ok", "output": asdict(top)}

    def add_to_watchlist(self, lid: str):
        if lid not in self.listings: return {"status": "failed", "output": "listing not found"}
        if lid not in self.watchlist:
            self.watchlist.append(lid)
        return {"status": "ok", "output": list(self.watchlist)}

    def remove_from_watchlist(self, lid: str):
        if lid in self.watchlist:
            self.watchlist.remove(lid)
        return {"status": "ok", "output": list(self.watchlist)}

    def get_watchlist(self):
        items = [asdict(self.listings[l]) for l in self.watchlist if l in self.listings]
        return {"status": "ok", "output": items}

    def search_listings(self, query: str):
        q = query.lower()
        hits = [asdict(L) for L in self.listings.values() if q in L.title.lower() or q in L.description.lower()]
        return {"status": "ok", "output": hits}

    def get_stats(self):
        active = sum(1 for L in self.listings.values() if L.status == "active")
        return {"status": "ok", "output": {
            "total_listings": len(self.listings),
            "active": active,
            "total_bids": len(self.bids),
            "watchlist_size": len(self.watchlist),
        }}
