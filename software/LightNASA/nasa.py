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


class NasaSession:
    """Deterministic sandbox for the NASA Open APIs mock, ported from the FastAPI service."""

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "nasa.yaml") as f:
                info = yaml.safe_load(f)

            self.apod: List[Dict[str, Any]] = []
            for r in info.get("apod", []):
                entry = {
                    "date": r["date"],
                    "title": r["title"],
                    "explanation": r["explanation"],
                    "url": r["url"],
                    "media_type": r["media_type"],
                    "service_version": "v1",
                }
                if r.get("hdurl"):
                    entry["hdurl"] = r["hdurl"]
                if r.get("copyright"):
                    entry["copyright"] = r["copyright"]
                self.apod.append(entry)

            self.rover_photos: List[Dict[str, Any]] = [
                {
                    "id": int(r["id"]),
                    "rover": r["rover"],
                    "sol": int(r["sol"]),
                    "camera": r["camera"],
                    "camera_full_name": r["camera_full_name"],
                    "img_src": r["img_src"],
                    "earth_date": r["earth_date"],
                }
                for r in info.get("rover_photos", [])
            ]

            self.rovers: List[Dict[str, Any]] = [
                {
                    "name": r["name"],
                    "status": r["status"],
                    "landing_date": r["landing_date"],
                    "launch_date": r["launch_date"],
                    "max_sol": int(r["max_sol"]),
                    "max_date": r["max_date"],
                    "total_photos": int(r["total_photos"]),
                }
                for r in info.get("rovers", [])
            ]

            self.neos: List[Dict[str, Any]] = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "close_approach_date": r["close_approach_date"],
                    "absolute_magnitude_h": float(r["absolute_magnitude_h"]),
                    "est_diameter_min_km": float(r["est_diameter_min_km"]),
                    "est_diameter_max_km": float(r["est_diameter_max_km"]),
                    "is_potentially_hazardous": _to_bool(r["is_potentially_hazardous"]),
                    "miss_distance_km": float(r["miss_distance_km"]),
                    "relative_velocity_kph": float(r["relative_velocity_kph"]),
                    "orbiting_body": r["orbiting_body"],
                }
                for r in info.get("neos", [])
            ]

            self.epic: List[Dict[str, Any]] = [
                {
                    "identifier": r["identifier"],
                    "image": r["image"],
                    "caption": r["caption"],
                    "date": r["date"],
                    "centroid_coordinates": {
                        "lat": float(r["centroid_lat"]),
                        "lon": float(r["centroid_lon"]),
                    },
                }
                for r in info.get("epic", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightNASA')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"apod": self.apod, "neos": self.neos}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def _rover(self, name):
        return next((r for r in self.rovers if r["name"].lower() == (name or "").lower()), None)

    def _neo_view(self, n):
        return {
            "id": n["id"],
            "neo_reference_id": n["id"],
            "name": n["name"],
            "absolute_magnitude_h": n["absolute_magnitude_h"],
            "estimated_diameter": {
                "kilometers": {
                    "estimated_diameter_min": n["est_diameter_min_km"],
                    "estimated_diameter_max": n["est_diameter_max_km"],
                }
            },
            "is_potentially_hazardous_asteroid": n["is_potentially_hazardous"],
            "close_approach_data": [
                {
                    "close_approach_date": n["close_approach_date"],
                    "relative_velocity": {"kilometers_per_hour": f"{n['relative_velocity_kph']}"},
                    "miss_distance": {"kilometers": f"{n['miss_distance_km']}"},
                    "orbiting_body": n["orbiting_body"],
                }
            ],
        }

    # --- APOD --------------------------------------------------------------
    def get_apod(self, date: str | None = None, start_date: str | None = None,
                 end_date: str | None = None) -> Dict[str, Any]:
        if start_date or end_date:
            lo = start_date or min(a["date"] for a in self.apod)
            hi = end_date or max(a["date"] for a in self.apod)
            return {"status": "ok", "output": [a for a in self.apod if lo <= a["date"] <= hi]}
        if date:
            a = next((x for x in self.apod if x["date"] == date), None)
            if not a:
                return {"status": "failed", "output": f"No APOD entry for {date}"}
            return {"status": "ok", "output": a}
        return {"status": "ok", "output": max(self.apod, key=lambda x: x["date"])}

    # --- Mars rover photos -------------------------------------------------
    def get_rover_manifest(self, rover: str) -> Dict[str, Any]:
        r = self._rover(rover)
        if not r:
            return {"status": "failed", "output": f"Rover {rover} not found"}
        photos_for_rover = [p for p in self.rover_photos if p["rover"].lower() == r["name"].lower()]
        by_sol = {}
        for p in photos_for_rover:
            by_sol.setdefault(p["sol"], {"sol": p["sol"], "earth_date": p["earth_date"], "total_photos": 0, "cameras": set()})
            by_sol[p["sol"]]["total_photos"] += 1
            by_sol[p["sol"]]["cameras"].add(p["camera"])
        photos = []
        for sol in sorted(by_sol):
            item = by_sol[sol]
            photos.append({
                "sol": item["sol"],
                "earth_date": item["earth_date"],
                "total_photos": item["total_photos"],
                "cameras": sorted(item["cameras"]),
            })
        return {"status": "ok", "output": {
            "photo_manifest": {
                "name": r["name"],
                "landing_date": r["landing_date"],
                "launch_date": r["launch_date"],
                "status": r["status"],
                "max_sol": r["max_sol"],
                "max_date": r["max_date"],
                "total_photos": r["total_photos"],
                "photos": photos,
            }
        }}

    def get_rover_photos(self, rover: str, sol: int | None = None, camera: str | None = None,
                         earth_date: str | None = None) -> Dict[str, Any]:
        r = self._rover(rover)
        if not r:
            return {"status": "failed", "output": f"Rover {rover} not found"}
        photos = [p for p in self.rover_photos if p["rover"].lower() == r["name"].lower()]
        if sol is not None:
            photos = [p for p in photos if p["sol"] == int(sol)]
        if earth_date:
            photos = [p for p in photos if p["earth_date"] == earth_date]
        if camera:
            photos = [p for p in photos if p["camera"].lower() == camera.lower()]
        rover_summary = {
            "name": r["name"],
            "landing_date": r["landing_date"],
            "launch_date": r["launch_date"],
            "status": r["status"],
        }
        result = []
        for p in photos:
            result.append({
                "id": p["id"],
                "sol": p["sol"],
                "camera": {"name": p["camera"], "full_name": p["camera_full_name"]},
                "img_src": p["img_src"],
                "earth_date": p["earth_date"],
                "rover": rover_summary,
            })
        return {"status": "ok", "output": {"photos": result}}

    # --- NeoWs -------------------------------------------------------------
    def get_neo_feed(self, start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
        lo = start_date or min(n["close_approach_date"] for n in self.neos)
        hi = end_date or lo
        matches = [n for n in self.neos if lo <= n["close_approach_date"] <= hi]
        by_date = {}
        for n in matches:
            by_date.setdefault(n["close_approach_date"], []).append(self._neo_view(n))
        return {"status": "ok", "output": {
            "element_count": len(matches),
            "near_earth_objects": by_date,
        }}

    def get_neo(self, neo_id: str) -> Dict[str, Any]:
        n = next((x for x in self.neos if x["id"] == str(neo_id)), None)
        if not n:
            return {"status": "failed", "output": f"NEO {neo_id} not found"}
        return {"status": "ok", "output": self._neo_view(n)}

    # --- EPIC --------------------------------------------------------------
    def get_epic_natural(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.epic)}


if __name__ == "__main__":
    s = NasaSession(seed=12)
    print(s.get_apod())
    print(s.get_epic_natural())
