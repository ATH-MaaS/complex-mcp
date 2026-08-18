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


ORDER_STATUSES = ("placed", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled")
DEFAULT_CURRENCY = "USD"
DELIVERY_FEE = 3.50

SEED_RESTAURANTS = [
    ("Sakura Sushi",     "japanese", 4.7, 30, 15.00),
    ("Bella Napoli",     "italian",  4.5, 40, 20.00),
    ("Taco Fiesta",      "mexican",  4.3, 25, 12.00),
    ("Golden Wok",       "chinese",  4.4, 35, 18.00),
]

SEED_MENU = [
    ("Sakura Sushi",  "Salmon Nigiri (6pc)",  "Fresh Atlantic salmon over sushi rice.",       14.50, "sushi",  True),
    ("Sakura Sushi",  "Spicy Tuna Roll",      "Tuna, sriracha mayo, cucumber.",                9.75,  "roll",   True),
    ("Sakura Sushi",  "Miso Soup",            "Traditional white miso with tofu and scallion.", 3.50, "soup",   True),

    ("Bella Napoli",  "Margherita Pizza",     "Tomato, mozzarella di bufala, basil.",         16.00, "pizza",  True),
    ("Bella Napoli",  "Spaghetti Carbonara",  "Guanciale, egg yolk, pecorino, black pepper.", 17.50, "pasta",  True),
    ("Bella Napoli",  "Tiramisu",             "Espresso-soaked ladyfingers, mascarpone.",      8.00, "dessert",True),

    ("Taco Fiesta",   "Al Pastor Tacos (3)",  "Marinated pork, pineapple, cilantro, onion.",  11.00, "taco",   True),
    ("Taco Fiesta",   "Chicken Burrito",      "Grilled chicken, rice, beans, cheese, salsa.", 12.50, "burrito",True),
    ("Taco Fiesta",   "Chips & Guacamole",    "Fresh avocado guacamole with warm chips.",      6.75, "side",   True),

    ("Golden Wok",    "Kung Pao Chicken",     "Wok chicken with peanuts, chili, scallion.",   14.25, "entree", True),
    ("Golden Wok",    "Vegetable Fried Rice", "Wok rice with peas, carrots, egg, scallion.",   9.50, "rice",   True),
    ("Golden Wok",    "Pork Dumplings (8)",   "Pan-seared pork and chive dumplings.",         10.75, "dimsum", False),
]

SEED_ORDERS = [
    ("Sakura Sushi",  "self",   [("Salmon Nigiri (6pc)", 1), ("Miso Soup", 1)],      "delivered",         -240, -180, 3.00, "123 Main St"),
    ("Bella Napoli",  "self",   [("Margherita Pizza", 1), ("Tiramisu", 1)],           "out_for_delivery",  -30,  None,  4.00, "123 Main St"),
    ("Taco Fiesta",   "friend", [("Al Pastor Tacos (3)", 2), ("Chips & Guacamole", 1)], "preparing",       -10,  None,  2.50, "9 Elm Ave"),
    ("Golden Wok",    "self",   [("Kung Pao Chicken", 1), ("Vegetable Fried Rice", 1)], "confirmed",       -3,   None,  3.50, "500 Market St"),
    ("Sakura Sushi",  "friend", [("Spicy Tuna Roll", 3)],                              "placed",           0,    None,  2.00, "9 Elm Ave"),
]


@dataclass
class Restaurant:
    restid: str
    name: str
    cuisine: str
    rating: float
    delivery_time_min: int
    min_order: float


@dataclass
class MenuItem:
    miid: str
    restaurant_id: str
    name: str
    description: str
    price: float
    currency: str
    category: str
    available: bool = True


@dataclass
class Order:
    oid: str
    restaurant_id: str
    customer: str
    items: List[Dict]
    subtotal: float
    delivery_fee: float
    tip: float
    total: float
    currency: str
    status: str
    placed_at: str
    delivered_at: str = ""
    address: str = ""


class FoodSession:
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
            self.restaurants: Dict[str, Restaurant] = {}
            self.menu_items: Dict[str, MenuItem] = {}
            self.orders: Dict[str, Order] = {}
            self._rest_name_to_id: Dict[str, str] = {}
            self._menu_name_to_id: Dict[str, str] = {}
            self._seed_restaurants()
            self._seed_menu()
            self._seed_orders()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightFood')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_restaurants(self) -> None:
        for name, cuisine, rating, dt_min, min_order in SEED_RESTAURANTS:
            r = Restaurant(
                restid="rest_" + self.uuid()[:8],
                name=name,
                cuisine=cuisine,
                rating=rating,
                delivery_time_min=dt_min,
                min_order=min_order,
            )
            self.restaurants[r.restid] = r
            self._rest_name_to_id[name] = r.restid

    def _seed_menu(self) -> None:
        for rname, iname, desc, price, category, available in SEED_MENU:
            restid = self._rest_name_to_id.get(rname)
            if restid is None:
                continue
            mi = MenuItem(
                miid="mi_" + self.uuid()[:8],
                restaurant_id=restid,
                name=iname,
                description=desc,
                price=price,
                currency=DEFAULT_CURRENCY,
                category=category,
                available=available,
            )
            self.menu_items[mi.miid] = mi
            self._menu_name_to_id[f"{rname}::{iname}"] = mi.miid

    def _seed_orders(self) -> None:
        for rname, customer, items_spec, status, placed_off, delivered_off, tip, address in SEED_ORDERS:
            restid = self._rest_name_to_id.get(rname)
            if restid is None:
                continue
            items: List[Dict] = []
            subtotal = 0.0
            for iname, qty in items_spec:
                miid = self._menu_name_to_id.get(f"{rname}::{iname}")
                if miid is None:
                    continue
                mi = self.menu_items[miid]
                items.append({"miid": miid, "quantity": qty, "price": mi.price})
                subtotal += mi.price * qty
            subtotal = round(subtotal, 2)
            total = round(subtotal + DELIVERY_FEE + tip, 2)
            placed_at = (self._today + timedelta(minutes=placed_off)).isoformat(timespec="minutes")
            delivered_at = (self._today + timedelta(minutes=delivered_off)).isoformat(timespec="minutes") if delivered_off is not None else ""
            o = Order(
                oid="ord_" + self.uuid()[:8],
                restaurant_id=restid,
                customer=customer,
                items=items,
                subtotal=subtotal,
                delivery_fee=DELIVERY_FEE,
                tip=tip,
                total=total,
                currency=DEFAULT_CURRENCY,
                status=status,
                placed_at=placed_at,
                delivered_at=delivered_at,
                address=address,
            )
            self.orders[o.oid] = o

    def get_session_dict(self) -> Dict:
        return {
            "restaurants": {rid: asdict(r) for rid, r in self.restaurants.items()},
            "menu_items":  {mid: asdict(m) for mid, m in self.menu_items.items()},
            "orders":      {oid: asdict(o) for oid, o in self.orders.items()},
        }

    def _order_summary(self, o: Order) -> Dict:
        return {
            "oid": o.oid,
            "restaurant_id": o.restaurant_id,
            "customer": o.customer,
            "status": o.status,
            "total": o.total,
            "currency": o.currency,
            "placed_at": o.placed_at,
            "items_count": sum(int(it.get("quantity", 0)) for it in o.items),
        }

    def list_restaurants(self, cuisine: Optional[str] = None) -> Dict:
        items = list(self.restaurants.values())
        if cuisine:
            items = [r for r in items if r.cuisine.lower() == cuisine.lower()]
        items.sort(key=lambda r: -r.rating)
        return {"status": "ok", "output": [asdict(r) for r in items]}

    def get_restaurant(self, restid: str) -> Dict:
        r = self.restaurants.get(restid)
        if not r:
            return {"status": "failed", "output": f"restaurant {restid} not found"}
        return {"status": "ok", "output": asdict(r)}

    def list_menu(self, restaurant_id: str, category: Optional[str] = None) -> Dict:
        if restaurant_id not in self.restaurants:
            return {"status": "failed", "output": f"restaurant {restaurant_id} not found"}
        items = [m for m in self.menu_items.values() if m.restaurant_id == restaurant_id]
        if category:
            items = [m for m in items if m.category == category]
        items.sort(key=lambda m: (m.category, m.name))
        return {"status": "ok", "output": [asdict(m) for m in items]}

    def get_menu_item(self, miid: str) -> Dict:
        m = self.menu_items.get(miid)
        if not m:
            return {"status": "failed", "output": f"menu item {miid} not found"}
        return {"status": "ok", "output": asdict(m)}

    def add_menu_item(self, restaurant_id: str, name: str, description: str,
                      price: float, category: str, available: bool = True,
                      currency: str = DEFAULT_CURRENCY) -> Dict:
        if restaurant_id not in self.restaurants:
            return {"status": "failed", "output": f"restaurant {restaurant_id} not found"}
        m = MenuItem(
            miid="mi_" + self.uuid()[:8],
            restaurant_id=restaurant_id,
            name=name,
            description=description,
            price=price,
            currency=currency,
            category=category,
            available=available,
        )
        self.menu_items[m.miid] = m
        return {"status": "ok", "output": asdict(m)}

    def update_menu_item(self, miid: str,
                         name: Optional[str] = None,
                         description: Optional[str] = None,
                         price: Optional[float] = None,
                         category: Optional[str] = None,
                         available: Optional[bool] = None) -> Dict:
        m = self.menu_items.get(miid)
        if not m:
            return {"status": "failed", "output": f"menu item {miid} not found"}
        for k, v in {"name": name, "description": description, "price": price,
                     "category": category, "available": available}.items():
            if v is not None:
                setattr(m, k, v)
        return {"status": "ok", "output": asdict(m)}

    def list_orders(self, status: Optional[str] = None, customer: Optional[str] = None) -> Dict:
        items = list(self.orders.values())
        if status:
            if status not in ORDER_STATUSES:
                return {"status": "failed", "output": f"status must be one of {ORDER_STATUSES}"}
            items = [o for o in items if o.status == status]
        if customer:
            items = [o for o in items if o.customer == customer]
        items.sort(key=lambda o: o.placed_at, reverse=True)
        return {"status": "ok", "output": [self._order_summary(o) for o in items]}

    def get_order(self, oid: str) -> Dict:
        o = self.orders.get(oid)
        if not o:
            return {"status": "failed", "output": f"order {oid} not found"}
        return {"status": "ok", "output": asdict(o)}

    def place_order(self, restaurant_id: str, customer: str,
                    items: List[Dict], address: str, tip: float = 0.0) -> Dict:
        rest = self.restaurants.get(restaurant_id)
        if not rest:
            return {"status": "failed", "output": f"restaurant {restaurant_id} not found"}
        if not items:
            return {"status": "failed", "output": "items must not be empty"}
        resolved: List[Dict] = []
        subtotal = 0.0
        for entry in items:
            miid = entry.get("miid")
            qty = int(entry.get("quantity", 0))
            mi = self.menu_items.get(miid or "")
            if not mi:
                return {"status": "failed", "output": f"menu item {miid} not found"}
            if mi.restaurant_id != restaurant_id:
                return {"status": "failed", "output": f"menu item {miid} not from restaurant {restaurant_id}"}
            if not mi.available:
                return {"status": "failed", "output": f"menu item {miid} not available"}
            if qty <= 0:
                return {"status": "failed", "output": f"quantity for {miid} must be positive"}
            resolved.append({"miid": miid, "quantity": qty, "price": mi.price})
            subtotal += mi.price * qty
        subtotal = round(subtotal, 2)
        if subtotal < rest.min_order:
            return {"status": "failed", "output": f"subtotal {subtotal} below min_order {rest.min_order}"}
        total = round(subtotal + DELIVERY_FEE + tip, 2)
        o = Order(
            oid="ord_" + self.uuid()[:8],
            restaurant_id=restaurant_id,
            customer=customer,
            items=resolved,
            subtotal=subtotal,
            delivery_fee=DELIVERY_FEE,
            tip=tip,
            total=total,
            currency=DEFAULT_CURRENCY,
            status="placed",
            placed_at=self._now(),
            address=address,
        )
        self.orders[o.oid] = o
        return {"status": "ok", "output": self._order_summary(o)}

    def _transition_order(self, oid: str, allowed_from: set, new_status: str,
                          set_delivered: bool = False) -> Dict:
        o = self.orders.get(oid)
        if not o:
            return {"status": "failed", "output": f"order {oid} not found"}
        if o.status not in allowed_from:
            return {"status": "failed", "output": f"order {oid} cannot go to {new_status} from {o.status}"}
        o.status = new_status
        if set_delivered:
            o.delivered_at = self._now()
        return {"status": "ok", "output": self._order_summary(o)}

    def cancel_order(self, oid: str) -> Dict:
        return self._transition_order(oid, {"placed", "confirmed"}, "cancelled")

    def confirm_order(self, oid: str) -> Dict:
        return self._transition_order(oid, {"placed"}, "confirmed")

    def start_preparation(self, oid: str) -> Dict:
        return self._transition_order(oid, {"confirmed"}, "preparing")

    def mark_out_for_delivery(self, oid: str) -> Dict:
        return self._transition_order(oid, {"preparing"}, "out_for_delivery")

    def mark_delivered(self, oid: str) -> Dict:
        return self._transition_order(oid, {"out_for_delivery"}, "delivered", set_delivered=True)

    def search_restaurants(self, query: str) -> Dict:
        q = query.lower()
        items = [r for r in self.restaurants.values()
                 if q in r.name.lower() or q in r.cuisine.lower()]
        items.sort(key=lambda r: -r.rating)
        return {"status": "ok", "output": [asdict(r) for r in items]}

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s: 0 for s in ORDER_STATUSES}
        revenue = 0.0
        for o in self.orders.values():
            by_status[o.status] = by_status.get(o.status, 0) + 1
            if o.status != "cancelled":
                revenue += o.total
        return {
            "status": "ok",
            "output": {
                "restaurants": len(self.restaurants),
                "menu_items": len(self.menu_items),
                "orders": len(self.orders),
                "by_status": by_status,
                "revenue": round(revenue, 2),
            },
        }
