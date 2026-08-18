from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import random
import yaml
import math

import sys
from pathlib import Path

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.time import TimeMachine
from software.utils.core import OSConnector, DummyOSConnector, uuid_rng
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed

@dataclass
class Flight:
    fid: str
    departure: str
    arrival: str
    departure_airport: str
    arrival_airport: str
    departure_time: str
    arrival_time: str
    duration: int  # 分钟
    price: float
    seat_count: Dict[str, int] = field(default_factory=dict)  # 舱等: 剩余座位数

@dataclass
class Airport:
    aid: str
    name: str
    city: str
    code: str
    _coord: Tuple[int, int]
    star: bool = field(default=False)

@dataclass
class PassengerInfo:
    name: str
    light_talk_uid: str = field(default="empty")

@dataclass
class BookingItem:
    bid: str
    fid: str
    seat_class: str
    total_price: float
    passenger_info: PassengerInfo
    paid: bool = field(default=False)

@dataclass
class BookingRecord:
    brid: str
    timestamp: str
    total_price: float
    bookings: Dict[str, Dict[str, int]] = field(default_factory=dict) # fid: {seat_class: cnt}

@dataclass
class RefundRecord:
    rid: str
    timestamp: str
    total_price: float
    bookings: Dict[str, Dict[str, int]] = field(default_factory=dict) # fid: {seat_class: cnt}

CORPUS_PATH = Path("software") / "LightFlight" / "corpus"

class FlightSession:
    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.time_machine = TimeMachine(rng=self.rng)
            self.os = OSConnector(
                session_id=os_cfg["session_id"],
                url=os_cfg["url"]
            ) if os_cfg else DummyOSConnector()

            self.airports, self.airports_in_cities = self.init_airports()
            self.flights, self.flights_by_arrival, self.flights_by_departure = self.init_flights()

            self.my_balance = self.rng.randint(15000, 60000)
            self.current_bookings: List[BookingItem] = []
            self.bookings_history: List[BookingRecord] = []
            self.refund_history: List[RefundRecord] = []
            self.passengers: List[PassengerInfo] = []
            self.__mock_booking()
            self.my_starred_airports = set()

            self.enter_password = False
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightFlight')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
    
    def uuid(self, prefix: str):
        return f"{prefix}_{uuid_rng(self.rng)}"

    def get_session_dict(self) -> Dict[str, Any]:
        bookings = [asdict(booking) for booking in self.current_bookings]
        bookings.sort(key=lambda x: x["fid"])

        passengers = [asdict(passenger) for passenger in self.passengers]

        return {
            "my_balance": self.my_balance,
            "bookings": bookings,
            "passengers": passengers
        }

    def init_airports(self) -> Tuple[List[Airport], Dict[str, str]]:
        airports_list = []
        airports_in_cities = defaultdict(list)
        with open(CORPUS_PATH / "airports.yaml") as f:
            airports = yaml.safe_load(f)["airports"]
            for airport in airports:
                aid = airport["aid"]
                name = airport["name"]
                city = airport["city"]
                code = airport["code"]
                _coord = airport["_coord"]

                airport_item = Airport(
                    aid=aid,
                    name=name,
                    city=city,
                    code=code,
                    _coord=_coord
                )
                airports_list.append(airport_item)
                airports_in_cities[city].append(name)
        
        return airports_list, airports_in_cities

    def init_flights(self) -> Tuple[Dict[str, Flight], Dict[str, List[Flight]], Dict[str, List[Flight]]]:
        def __mock_dura_price(
            coord_1: Tuple[float, float],
            coord_2: Tuple[float, float]
        ) -> Tuple[int, float]:
            lat1, lon1 = coord_1
            lat2, lon2 = coord_2
            
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            distance_km = 111 * math.sqrt(dlat**2 + (math.cos(math.radians(lat1)) * dlon)**2)
            
            flight_hours = distance_km / 800
            total_minutes = int(round(flight_hours * 60 + 45))  # 飞行时间+起降
            
            total_minutes = int(total_minutes * self.rng.uniform(0.9, 1.1))
            total_minutes = max(60, total_minutes)
            
            price_per_km = self.rng.uniform(0.8, 1.2)  # 每公里 0.8-1.2 元
            price = distance_km * price_per_km
            
            # 简单调节
            if total_minutes < 120:  # 短途
                price *= 1.5
            elif total_minutes > 360:  # 长途
                price *= 0.9
            
            # 随机波动
            price *= self.rng.uniform(0.3, 1.2)
            
            price = max(300, min(10000, price))
            price = round(price / 10) * 10
            
            return total_minutes, price

        flights: Dict[str, Flight] = {}
        flights_by_arrival: Dict[str, List[Flight]] = defaultdict(list)
        flights_by_departure: Dict[str, List[Flight]] = defaultdict(list)
        base_time = self.os.now()
        for airport in self.airports:
            target_airports = self.rng.sample(self.airports, k=self.rng.randint(5, 50))
            target_airports = self.rng.choices(target_airports, k=4 * len(target_airports))
            for target_airport in target_airports:
                dura, price = __mock_dura_price(airport._coord, target_airport._coord)
                departure_time = self.time_machine.add_secs(
                    timestamp=base_time,
                    min_secs=3600 * 4, max_secs= 3600 * 10 * 24
                )
                flight = Flight(
                    fid=self.uuid("flight"),
                    departure=airport.city,
                    arrival=target_airport.city,
                    departure_airport=airport.name,
                    arrival_airport=target_airport.name,
                    departure_time=departure_time,
                    arrival_time=self.time_machine.add_secs(
                        departure_time,
                        min_secs=dura * 60, max_secs=dura * 60
                    ),
                    duration=dura,
                    price=price, # economy
                    seat_count={
                        "economy": self.rng.randint(10, 50),
                        "business": self.rng.randint(0, 20),
                        "first": self.rng.randint(0, 7)
                    }
                )
                flights[flight.fid] = flight
                flights_by_arrival[flight.arrival].append(flight)
                flights_by_departure[flight.departure].append(flight)
        
        return flights, dict(flights_by_arrival), dict(flights_by_departure)

    def __mock_booking(self):
        if self.rng.uniform(0, 1) > 0.5:
            return
        self.add_passenger(name="Carl Lee")
        fid = self.rng.choice(list(self.flights.keys()))
        self.add_to_booking(fid, seat_class="economy", passenger_idx=0)

        
    def list_all_cities(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "output": list(self.airports_in_cities.keys())
        }

    def list_airports_by_city(self, city: str) -> Dict[str, Any]:
        if city not in self.airports_in_cities:
            return {
                "status": "failed",
                "output": f"City '{city}' not found"
            }
        return {
            "status": "ok",
            "output": self.airports_in_cities[city]
        }

    def __get_flight(self, fid: str) -> Tuple[Optional[Flight], Optional[Dict]]:
        if fid not in self.flights:
            return None, {
                "status": "failed",
                "output": f"Flight ID with {fid} not found"
            }
        
        return self.flights[fid], None

    def get_flight_details(self, fid: str) -> Dict[str, Any]:
        flight, err = self.__get_flight(fid)
        if err: return err

        flight_info = {
            "fid": flight.fid,
            "departure": f"{flight.departure}, {flight.departure_airport}",
            "arrival": f"{flight.arrival}, {flight.arrival_airport}",
            "depature_time": flight.departure_time,
            "arrival_time": flight.arrival_time,
            "duration": f"{flight.duration} min",
            "price": {
                "ecomony": flight.price,
                "business": flight.price * 2,
                "first": flight.price * 4.5
            },
            "seat_count": flight.seat_count
        }

        return {
            "status": "ok",
            "output": flight_info
        }

    def search_flights(self, departure: str, arrival: str, date: str) -> Dict[str, Any]:
        # parse input date (accept "YYYY-MM-DD" or full timestamp)
        try:
            if len(date.strip()) == 10:
                target_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            else:
                target_date = datetime.strptime(date.strip(), "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            return {
                "status": "failed",
                "output": f"Invalid date format: {date}. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
            }

        matched = []
        for flight in self.flights_by_departure.get(departure, []):
            try:
                dep_time = datetime.strptime(flight.departure_time, "%Y-%m-%d %H:%M:%S")
            except Exception:
                # skip malformed timestamps
                continue

            if dep_time.date() != target_date:
                continue

            if flight.arrival == arrival:
                matched.append(flight.fid)

        if not matched:
            return {
                "status": "failed",
                "output": f"No flights found for {departure} -> {arrival} on {date}"
            }

        return {
            "status": "ok",
            "output": matched
        }

    def check_seat_availability(self, fid: str, seat_class: str) -> Dict[str, Any]:
        flight, err = self.__get_flight(fid)
        if err: return err

        if seat_class not in flight.seat_count:
            return {
                "status": "failed",
                "output": f"Seat class `{seat_class}` not found"
            }
        
        return {
            "status": "ok",
            "output": f"Remain {flight.seat_count[seat_class]} seats"
        }
    
    def check_passengers(self):
        passengers_info = [asdict(passenger) for passenger in self.passengers]

        return {
            "status": "ok",
            "output": passengers_info
        }
    
    def add_passenger(self, name: str, light_talk_uid: str = ""):
        passenger_info = PassengerInfo(
            name=name,
            light_talk_uid=light_talk_uid if light_talk_uid else "empty"
        )
        self.passengers.append(passenger_info)

        return {
            "status": "ok",
            "output": f"You have successfully added a new passenger : {asdict(passenger_info)}, index = {len(self.passengers) - 1}"
        }
    
    def remove_passenger(self, passenger_idx: int):
        if passenger_idx >= len(self.passengers):
            return {
                "status": "failed",
                "output": "Index out of range"
            }
        passenger_info = self.passengers.pop(passenger_idx)

        return {
            "status": "ok",
            "output": f"You have succussfully removed one passenger : {asdict(passenger_info)}"
        }

    def add_to_booking(self, fid: str, seat_class: str, passenger_idx: int) -> Dict[str, Any]:
        flight, err = self.__get_flight(fid)
        if err: return err

        if flight.seat_count[seat_class] == 0:
            return {
                "status": "failed",
                "output": f"There is not enough seat count for this seat class"
            }
        
        if passenger_idx >= len(self.passengers):
            return {
                "status": "failed",
                "output": "Passenger index out of range"
            }
        
        passenger_info = self.passengers[passenger_idx]

        price_table = {
            "economy": flight.price,
            "business": 2 * flight.price,
            "first": 4.5 * flight.price
        }
        if seat_class not in price_table:
            return {
                "status": "failed",
                "output": f"Unsupported seat class `{seat_class}`"
            }
        price = price_table[seat_class]
        booking_item = BookingItem(
            bid=self.uuid(prefix="booking"),
            fid=flight.fid,
            seat_class=seat_class,
            total_price=price,
            passenger_info=passenger_info
        )

        self.current_bookings.append(booking_item)

        return {
            "status": "ok",
            "output": "You have successfully added one booking into list"
        }

    def check_bookings(self):
        bookings = [asdict(booking) for booking in self.current_bookings]
        return {
            "status": "ok",
            "output": sorted(bookings, key=lambda x: x["paid"])
        }

    def wait_payment_password(self) -> Dict[str, Any]:
        self.enter_password = True
        return {
            "status": "ok",
            "output": "The user has already entered the correct password"
        }

    def checkout_bookings(self) -> Dict[str, Any]:
        if not self.enter_password:
            return {
                "status": "failed",
                "output": "This operation need user to enter the passward first"
            }
        self.enter_password = False
        all_price = 0
        seats_cnt = defaultdict(lambda: defaultdict(int))

        for booking in self.current_bookings:
            if booking.paid:
                continue
            all_price += booking.total_price
            seats_cnt[booking.fid][booking.seat_class] += 1

        if all_price > self.my_balance:
            return {
                "status": "failed",
                "output": "Your balance is insufficient"
            }
        else:
            for booking in self.current_bookings:
                booking.paid = True
        self.my_balance -= all_price
        bookings = {fid: dict(seat_cnt) for fid, seat_cnt in seats_cnt.items()}

        booking_rec = BookingRecord(
            brid=self.uuid(prefix="booking_rec"),
            timestamp=self.os.step(),
            total_price=all_price,
            bookings=bookings
        )

        self.bookings_history.append(booking_rec)

        return {
            "status": "ok",
            "output": "You have successfully checkout all bookings"
        }

    def remove_from_booking(self, bid: str) -> Dict[str, Any]:
        for idx, booking in enumerate(self.current_bookings):
            if booking.bid != bid:
                continue
            if booking.paid:
                return {
                    "stats": "failed",
                    "output": f"The booking ({booking}) has already been paid"
                }
            self.current_bookings.pop(idx)
            return {
                "status": "ok",
                "output": f"You have successfully removed one booking"
            }
        
        return {
            "status": "failed",
            "output": f"Booking with bid={bid} not found"
        }

    def check_balance(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "output": f"$ {self.my_balance}"
        }

    def get_booking_history(self) -> Dict[str, Any]:
        booking_history = [asdict(booking_rec) for booking_rec in self.bookings_history]
        
        return {
            "status": "ok",
            "output": booking_history
        }

    def cancel_booking(self, bids: List[str]) -> Dict[str, Any]:
        total_refund = 0
        refund_bookings = defaultdict(lambda: defaultdict(int))
        removed_count = 0
        
        for bid in bids:
            found = False
            for idx, booking in enumerate(self.current_bookings):
                if booking.bid == bid:
                    found = True
                    if not booking.paid:
                        return {
                            "status": "failed",
                            "output": f"Booking {bid} has not been paid yet"
                        }
                    # Calculate 95% refund
                    refund_amount = booking.total_price * 0.95
                    total_refund += refund_amount
                    refund_bookings[booking.fid][booking.seat_class] += 1
                    self.current_bookings.pop(idx)
                    removed_count += 1
                    break
            
            if not found:
                return {
                    "status": "failed",
                    "output": f"Booking {bid} not found"
                }
        
        # Add refund record
        if removed_count > 0:
            refund_rec = RefundRecord(
                rid=self.uuid(prefix="refund_rec"),
                timestamp=self.os.step(),
                total_price=total_refund,
                bookings=dict(refund_bookings)
            )
            self.refund_history.append(refund_rec)
            self.my_balance += total_refund
        
        return {
            "status": "ok",
            "output": f"Successfully cancelled {removed_count} booking(s). Refunded ${total_refund:.2f}"
        }

    def search_airports(self, airport_name: str) -> Dict[str, Any]:
        matched = []
        airport_name_lower = airport_name.lower()
        
        for airport in self.airports:
            if airport_name_lower in airport.name.lower():
                matched.append({
                    "aid": airport.aid,
                    "name": airport.name,
                    "city": airport.city,
                    "code": airport.code
                })
        
        if not matched:
            return {
                "status": "failed",
                "output": f"No airports found matching '{airport_name}'"
            }
        
        return {
            "status": "ok",
            "output": matched
        }

    def star_airport(self, aid: str) -> Dict[str, Any]:
        # Find airport
        airport = None
        for ap in self.airports:
            if ap.aid == aid:
                airport = ap
                break
        
        if not airport:
            return {
                "status": "failed",
                "output": f"Airport with aid={aid} not found"
            }
        
        if aid in self.my_starred_airports:
            return {
                "status": "failed",
                "output": f"Airport '{airport.name}' is already starred"
            }
        
        self.my_starred_airports.add(aid)
        return {
            "status": "ok",
            "output": f"Successfully starred airport '{airport.name}'"
        }

    def unstar_airport(self, aid: str) -> Dict[str, Any]:
        # Find airport
        airport = None
        for ap in self.airports:
            if ap.aid == aid:
                airport = ap
                break
        
        if not airport:
            return {
                "status": "failed",
                "output": f"Airport with aid={aid} not found"
            }
        
        if aid not in self.my_starred_airports:
            return {
                "status": "failed",
                "output": f"Airport '{airport.name}' is not starred"
            }
        
        self.my_starred_airports.remove(aid)
        return {
            "status": "ok",
            "output": f"Successfully unstarred airport '{airport.name}'"
        }

    def get_my_starred_airports(self) -> Dict[str, Any]:
        starred = []
        for airport in self.airports:
            if airport.aid in self.my_starred_airports:
                starred.append({
                    "aid": airport.aid,
                    "name": airport.name,
                    "city": airport.city,
                    "code": airport.code
                })
        
        return {
            "status": "ok",
            "output": starred
        }
    
    def get_fids_by_arrival(self, arrival: str):
        if arrival not in self.flights_by_arrival:
            return {
                "status": "failed",
                "output": f"Arrival '{arrival}' not found"
            }
        
        flights = self.flights_by_arrival[arrival]
        fids = [flight.fid for flight in flights]

        return {
            "status": "ok",
            "output": fids
        }
    
    def get_fids_by_departure(self, departure: str):
        if departure not in self.flights_by_departure:
            return {
                "status": "failed",
                "output": f"Departure `{departure}` not found"
            }
        
        flights = self.flights_by_departure[departure]
        fids = [flight.fid for flight in flights]

        return {
            "status": "ok",
            "output": fids
        }


if __name__ == "__main__":
    flight_session = FlightSession(seed=109, os_cfg=None)
    from pprint import pprint

    pprint(flight_session.flights)

