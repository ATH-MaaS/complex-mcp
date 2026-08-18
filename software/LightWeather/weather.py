import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path("software") / "LightWeather" / "corpus"


class WeatherSession:
    """WeatherSession builds a deterministic sandbox at init using the provided seed.
    All subsequent calls read from the generated state so repeated calls within
    the same session are consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            # load corpus
            with open(CORPUS_PATH / "weather.yaml") as f:
                info = yaml.safe_load(f)

            self.conditions = {c["id"]: c for c in info.get("conditions", [])}
            self.advisories = {a["id"]: a for a in info.get("advisories", [])}
            self.cities = {c["name"]: c for c in info.get("cities", [])}
            self.stations = {s["id"]: s for s in info.get("stations", [])}
            self.climate_samples = {c["city"]: c for c in info.get("climate_samples", [])}

            # session state (deterministically generated now)
            self.base_time = self.os.now()
            self.alerts: Dict[str, Dict[str, Any]] = {}
            self.preferences: Dict[str, Any] = {}

            # Pre-generate consistent weather data per city/station
            self._current_weather: Dict[str, Dict[str, Any]] = {}
            self._daily_forecasts: Dict[str, List[Dict[str, Any]]] = {}
            self._hourly_forecasts: Dict[str, List[Dict[str, Any]]] = {}
            self._precip_probs: Dict[str, List[Dict[str, Any]]] = {}
            self._uv: Dict[str, Dict[str, Any]] = {}
            self._aqi: Dict[str, Dict[str, Any]] = {}
            self._sun_times: Dict[str, Dict[str, Any]] = {}
            self._station_obs: Dict[str, Dict[str, Any]] = {}
            self._historical: Dict[str, List[Dict[str, Any]]] = {}
            self._wind = {}

            self._generate_state()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightWeather')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
    
    def get_session_dict(self):
        return {
            "alerts": list(self.alerts.values()),
            "preferences": self.preferences
        }

    def _now_dt(self) -> datetime:
        return datetime.strptime(self.base_time, "%Y-%m-%d %H:%M:%S")

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _generate_state(self):
        now = self.base_time
        base_dt = self._now_dt()

        # per-city state
        for cname, cinfo in self.cities.items():
            sample = self.climate_samples.get(cname, {})
            avg = sample.get("avg_temp", 15)

            # current weather
            cond = self.rng.choice(list(self.conditions.values())) if self.conditions else {"id": "unknown", "name": "Unknown"}
            temp = round(avg + self.rng.uniform(-8, 8), 1)
            wind = round(self.rng.uniform(0, 80), 1)
            humidity = round(self.rng.uniform(20, 95), 1)
            self._current_weather[cname] = {
                "location": cname,
                "timestamp": now,
                "condition": cond,
                "temperature_c": temp,
                "wind_kph": wind,
                "humidity": humidity
            }

            # daily forecasts (7 days)
            dfore = []
            for d in range(7):
                date_str = (base_dt + timedelta(days=d)).strftime("%Y-%m-%d")
                dcond = self.rng.choice(list(self.conditions.values()))
                dtemp = round(avg + self.rng.uniform(-8, 8), 1)
                precip = round(max(0.0, self.rng.gauss(3, 8)), 1)
                dfore.append({"date": date_str, "condition": dcond, "temp_c": dtemp, "precip_mm": precip})
            self._daily_forecasts[cname] = dfore

            # hourly forecasts (48 hours)
            hfore = []
            for h in range(48):
                ts = (base_dt + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")
                hcond = self.rng.choice(list(self.conditions.values()))
                htemp = round(avg + self.rng.uniform(-6, 6), 1)
                pprob = round(self.rng.uniform(0, 1), 2)
                hfore.append({"timestamp": ts, "condition": hcond, "temp_c": htemp, "precip_prob": pprob})
            self._hourly_forecasts[cname] = hfore

            # precip probability short list
            probs = []
            for h in range(24):
                probs.append({"hour_offset": h, "prob": round(self.rng.uniform(0, 1), 2)})
            self._precip_probs[cname] = probs

            # UV and AQI
            uvv = round(self.rng.uniform(0, 11), 1)
            self._uv[cname] = {"uv": uvv, "level": "low" if uvv < 3 else ("moderate" if uvv < 6 else ("high" if uvv < 8 else "very high"))}
            aqi = int(max(0, min(500, int(self.rng.gauss(50, 60)))))
            self._aqi[cname] = {"aqi": aqi, "category": "Good" if aqi <= 50 else ("Moderate" if aqi <= 100 else ("Unhealthy" if aqi <= 200 else "Very Unhealthy"))}

            # sun times (mock)
            self._sun_times[cname] = {"sunrise": (base_dt + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"), "sunset": (base_dt + timedelta(hours=18)).strftime("%Y-%m-%d %H:%M:%S")}

            # historical samples
            hist = []
            for i in range(30):
                hist.append({"date": (base_dt - timedelta(days=i)).strftime("%Y-%m-%d"), "temp_c": round(avg + self.rng.uniform(-10, 10), 1), "condition": self.rng.choice(list(self.conditions.values()))})
            self._historical[cname] = hist

            winds = []
            for i in range(24 * 7):
                winds.append({"hour_offset": i + 1, "speed_kph": round(self.rng.uniform(0, 100), 1), "gust_kph": round(self.rng.uniform(0, 140), 1)})
            self._wind[cname] = winds

        # per-station observations (snapshot)
        for sid, sinfo in self.stations.items():
            obs = {
                "timestamp": now,
                "temperature_c": round(10 + self.rng.uniform(-10, 15), 1),
                "humidity": round(self.rng.uniform(10, 95), 1),
                "wind_kph": round(self.rng.uniform(0, 80), 1),
                "pressure_hpa": round(1000 + self.rng.uniform(-30, 30), 1),
                "status": self.rng.choice(["online", "offline", "maintenance"])
            }
            self._station_obs[sid] = obs

    # --- API methods read from pre-generated state ---
    def list_cities(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.cities.keys())}

    def get_current_weather(self, location: str) -> Dict[str, Any]:
        w = self._current_weather.get(location)
        if not w:
            return {"status": "failed", "output": f"Location {location} not found"}
        # update timestamp to current OS time but keep other values
        try:
            w2 = dict(w)
            w2["timestamp"] = self.os.now()
            return {"status": "ok", "output": w2}
        except Exception:
            return {"status": "ok", "output": w}

    def get_forecast(self, location: str, days: int = 3) -> Dict[str, Any]:
        if location not in self._daily_forecasts:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._daily_forecasts[location][:days]}

    def get_hourly_forecast(self, location: str, hours: int = 12) -> Dict[str, Any]:
        if location not in self._hourly_forecasts:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._hourly_forecasts[location][:hours]}

    def list_stations(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.stations.values())}

    def get_station_info(self, station_id: str) -> Dict[str, Any]:
        st = self.stations.get(station_id)
        if not st:
            return {"status": "failed", "output": f"Station {station_id} not found"}
        st2 = dict(st)
        st2["status"] = self._station_obs.get(station_id, {}).get("status", "unknown")
        return {"status": "ok", "output": st2}

    def get_station_observation(self, station_id: str) -> Dict[str, Any]:
        obs = self._station_obs.get(station_id)
        if not obs:
            return {"status": "failed", "output": f"Station {station_id} not found"}
        # refresh timestamp while keeping readings stable for session
        try:
            obs2 = dict(obs)
            obs2["timestamp"] = self.os.now()
            return {"status": "ok", "output": obs2}
        except Exception:
            return {"status": "ok", "output": obs}

    def get_historical_weather(self, location: str, start: str, end: str) -> Dict[str, Any]:
        if location not in self._historical:
            return {"status": "failed", "output": f"Location {location} not found"}
        
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d")
            end_date = datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            return {"status": "failed", "output": "Invalid date format. Use YYYY-MM-DD."}

        if start_date > end_date:
            return {"status": "failed", "output": "Start date must be before end date."}

        filtered_data = [
            entry for entry in self._historical[location]
            if start_date <= datetime.strptime(entry["date"], "%Y-%m-%d") <= end_date
        ]

        return {"status": "ok", "output": filtered_data}

    def get_weather_alerts(self, location: str) -> Dict[str, Any]:
        results = [a for a in self.alerts.values() if a.get("location") == location]
        return {"status": "ok", "output": results}

    def create_alert(self, location: str, condition: str, threshold: float) -> Dict[str, Any]:
        if location not in self.cities:
            return {"status": "failed", "output": f"Location {location} not found"}
        aid = f"alert_{self.uuid()}"
        alert = {"aid": aid, "location": location, "condition": condition, "threshold": threshold, "timestamp": self.os.now()}
        self.alerts[aid] = alert
        return {"status": "ok", "output": alert}

    def delete_alert(self, alert_id: str) -> Dict[str, Any]:
        if alert_id not in self.alerts:
            return {"status": "failed", "output": f"Alert {alert_id} not found"}
        del self.alerts[alert_id]
        return {"status": "ok", "output": f"Alert {alert_id} deleted"}

    def list_alerts(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.alerts.values())}

    def get_uv_index(self, location: str) -> Dict[str, Any]:
        if location not in self._uv:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._uv[location]}

    def get_air_quality(self, location: str) -> Dict[str, Any]:
        if location not in self._aqi:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._aqi[location]}

    def get_sun_times(self, location: str) -> Dict[str, Any]:
        if location not in self._sun_times:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._sun_times[location]}

    def convert_temperature(self, value: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
        fu = from_unit.lower()
        tu = to_unit.lower()
        if fu == tu:
            return {"status": "ok", "output": value}
        if fu == "f":
            c = (value - 32) * 5.0 / 9.0
        elif fu == "k":
            c = value - 273.15
        else:
            c = value
        if tu == "f":
            out = c * 9.0 / 5.0 + 32
        elif tu == "k":
            out = c + 273.15
        else:
            out = c
        return {"status": "ok", "output": round(out, 2)}

    def estimate_travel_weather(self, route: List[str]) -> Dict[str, Any]:
        legs = []
        for loc in route:
            if loc not in self.cities:
                legs.append({"location": loc, "status": "unknown"})
                continue
            cw = self._current_weather.get(loc)
            legs.append({"location": loc, "weather": cw})
        return {"status": "ok", "output": legs}

    def compare_climate(self, location1: str, location2: str) -> Dict[str, Any]:
        c1 = self.climate_samples.get(location1)
        c2 = self.climate_samples.get(location2)
        if not c1 or not c2:
            return {"status": "failed", "output": "One or both locations not found in climate samples"}
        diff = {"temp_diff": c1["avg_temp"] - c2["avg_temp"], "rain_diff_mm": c1["rainfall_mm"] - c2["rainfall_mm"]}
        return {"status": "ok", "output": diff}

    def get_precip_probability(self, location: str, next_hours: int = 6) -> Dict[str, Any]:
        if location not in self._precip_probs:
            return {"status": "failed", "output": f"Location {location} not found"}
        return {"status": "ok", "output": self._precip_probs[location][:next_hours]}

    def get_wind_forecast(self, location: str, hours: int = 12) -> Dict[str, Any]:
        if location not in self._wind:
            return {"status": "failed", "output": f"Location {location} not found"}
        
        return self._wind[location][:hours]

    def get_climate_summary(self, location: str, year: int = 2024) -> Dict[str, Any]:
        if location not in self.cities:
            return {"status": "failed", "output": f"Location {location} not found"}
        sample = self.climate_samples.get(location, {})
        summary = {"year": year, "avg_temp": sample.get("avg_temp", 15), "annual_rainfall_mm": sample.get("rainfall_mm", 800)}
        return {"status": "ok", "output": summary}

    def set_primary_location(self, location: str) -> Dict[str, Any]:
        if location not in self.cities:
            return {"status": "failed", "output": f"Location {location} not found"}
        self.preferences["primary_location"] = location
        return {"status": "ok", "output": f"Primary location set to {location}"}

    def get_primary_location(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.preferences.get("primary_location", None)}
    

if __name__ == "__main__":
    weather_session = WeatherSession(seed=12)

    # print(weather_session.list_cities())

    location = "New York"

    print(weather_session.get_wind_forecast(location=location))
    print(weather_session.get_wind_forecast(location=location))
