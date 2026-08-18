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


class OpenweatherSession:
    """Deterministic sandbox for the OpenWeather API mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "openweather.yaml") as f:
                info = yaml.safe_load(f)

            self.cities: List[Dict[str, Any]] = [
                {
                    "id": int(r["id"]),
                    "name": r["name"],
                    "country": r["country"],
                    "state": (str(r.get("state") or "") or None),
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "timezone": int(r["timezone"]),
                }
                for r in info.get("cities", [])
            ]
            self.current: List[Dict[str, Any]] = [
                {
                    "city_id": int(r["city_id"]),
                    "weather_id": int(r["weather_id"]),
                    "weather_main": r["weather_main"],
                    "weather_description": r["weather_description"],
                    "weather_icon": r["weather_icon"],
                    "temp": float(r["temp"]),
                    "feels_like": float(r["feels_like"]),
                    "temp_min": float(r["temp_min"]),
                    "temp_max": float(r["temp_max"]),
                    "pressure": int(r["pressure"]),
                    "humidity": int(r["humidity"]),
                    "wind_speed": float(r["wind_speed"]),
                    "wind_deg": int(r["wind_deg"]),
                    "clouds": int(r["clouds"]),
                    "visibility": int(r["visibility"]),
                    "dt": int(r["dt"]),
                }
                for r in info.get("current_weather", [])
            ]
            self.forecast: List[Dict[str, Any]] = [
                {
                    "city_id": int(r["city_id"]),
                    "dt": int(r["dt"]),
                    "dt_txt": r["dt_txt"],
                    "temp": float(r["temp"]),
                    "feels_like": float(r["feels_like"]),
                    "temp_min": float(r["temp_min"]),
                    "temp_max": float(r["temp_max"]),
                    "pressure": int(r["pressure"]),
                    "humidity": int(r["humidity"]),
                    "weather_id": int(r["weather_id"]),
                    "weather_main": r["weather_main"],
                    "weather_description": r["weather_description"],
                    "weather_icon": r["weather_icon"],
                    "wind_speed": float(r["wind_speed"]),
                    "wind_deg": int(r["wind_deg"]),
                    "clouds": int(r["clouds"]),
                    "pop": float(r["pop"]),
                }
                for r in info.get("forecast", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightOpenWeather')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"cities": self.cities}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _find_city_by_name(self, q):
        if not q:
            return None
        name = q.split(",")[0].strip().lower()
        for c in self.cities:
            if c["name"].lower() == name:
                return c
        for c in self.cities:
            if name in c["name"].lower():
                return c
        return None

    def _find_city_by_coords(self, lat, lon):
        best = None
        best_d = None
        for c in self.cities:
            d = (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2
            if best_d is None or d < best_d:
                best_d = d
                best = c
        return best

    def _current_for(self, city_id):
        for w in self.current:
            if w["city_id"] == city_id:
                return w
        return None

    def _weather_block(self, rec):
        return [{
            "id": rec["weather_id"],
            "main": rec["weather_main"],
            "description": rec["weather_description"],
            "icon": rec["weather_icon"],
        }]

    def _current_payload(self, city, w):
        return {
            "coord": {"lon": city["lon"], "lat": city["lat"]},
            "weather": self._weather_block(w),
            "base": "stations",
            "main": {
                "temp": w["temp"],
                "feels_like": w["feels_like"],
                "temp_min": w["temp_min"],
                "temp_max": w["temp_max"],
                "pressure": w["pressure"],
                "humidity": w["humidity"],
            },
            "visibility": w["visibility"],
            "wind": {"speed": w["wind_speed"], "deg": w["wind_deg"]},
            "clouds": {"all": w["clouds"]},
            "dt": w["dt"],
            "sys": {"country": city["country"]},
            "timezone": city["timezone"],
            "id": city["id"],
            "name": city["name"],
            "cod": 200,
        }

    def _forecast_item(self, rec):
        return {
            "dt": rec["dt"],
            "main": {
                "temp": rec["temp"],
                "feels_like": rec["feels_like"],
                "temp_min": rec["temp_min"],
                "temp_max": rec["temp_max"],
                "pressure": rec["pressure"],
                "humidity": rec["humidity"],
            },
            "weather": self._weather_block(rec),
            "clouds": {"all": rec["clouds"]},
            "wind": {"speed": rec["wind_speed"], "deg": rec["wind_deg"]},
            "pop": rec["pop"],
            "dt_txt": rec["dt_txt"],
        }

    # --- Current weather ---------------------------------------------------
    def get_current_weather(self, q: str | None = None, lat: float | None = None,
                            lon: float | None = None) -> Dict[str, Any]:
        if q:
            city = self._find_city_by_name(q)
        elif lat is not None and lon is not None:
            city = self._find_city_by_coords(lat, lon)
        else:
            return {"status": "failed", "output": "Nothing to geocode"}
        if not city:
            return {"status": "failed", "output": "city not found"}
        w = self._current_for(city["id"])
        if not w:
            return {"status": "failed", "output": "city not found"}
        return {"status": "ok", "output": self._current_payload(city, w)}

    # --- Forecast ----------------------------------------------------------
    def get_forecast(self, q: str | None = None, lat: float | None = None,
                     lon: float | None = None) -> Dict[str, Any]:
        if q:
            city = self._find_city_by_name(q)
        elif lat is not None and lon is not None:
            city = self._find_city_by_coords(lat, lon)
        else:
            return {"status": "failed", "output": "Nothing to geocode"}
        if not city:
            return {"status": "failed", "output": "city not found"}
        rows = [r for r in self.forecast if r["city_id"] == city["id"]]
        rows.sort(key=lambda r: r["dt"])
        items = [self._forecast_item(r) for r in rows]
        return {"status": "ok", "output": {
            "cod": "200",
            "message": 0,
            "cnt": len(items),
            "list": items,
            "city": {
                "id": city["id"],
                "name": city["name"],
                "coord": {"lat": city["lat"], "lon": city["lon"]},
                "country": city["country"],
                "timezone": city["timezone"],
            },
        }}

    # --- Geocoding ---------------------------------------------------------
    def geocode_direct(self, q: str, limit: int = 5) -> Dict[str, Any]:
        name = (q or "").split(",")[0].strip().lower()
        matches = [c for c in self.cities if name and name in c["name"].lower()]
        out = []
        for c in matches[:limit]:
            out.append({
                "name": c["name"],
                "lat": c["lat"],
                "lon": c["lon"],
                "country": c["country"],
                "state": c["state"],
            })
        return {"status": "ok", "output": out}


if __name__ == "__main__":
    s = OpenweatherSession(seed=12)
    print(s.geocode_direct("London"))
    print(s.get_current_weather(q="London"))
