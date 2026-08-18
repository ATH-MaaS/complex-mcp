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


def _to_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _genre_ids(s) -> List[int]:
    return [int(x) for x in str(s or "").split(";") if x]


class TmdbSession:
    """Deterministic sandbox for The Movie Database (TMDB) v3 API mock, ported from the FastAPI service.

    State is loaded from the corpus at init.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "tmdb.yaml") as f:
                info = yaml.safe_load(f)

            self.genres: List[Dict[str, Any]] = [
                {"id": _to_int(r["id"]), "name": r["name"]} for r in info.get("genres", [])
            ]
            self.movies: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r["id"]),
                    "title": r["title"],
                    "original_title": r["title"],
                    "overview": r["overview"],
                    "release_date": r["release_date"],
                    "vote_average": _to_float(r["vote_average"]),
                    "vote_count": _to_int(r["vote_count"]),
                    "genre_ids": _genre_ids(r["genre_ids"]),
                    "popularity": _to_float(r["popularity"]),
                    "original_language": r["original_language"],
                    "media_type": "movie",
                    "adult": False,
                }
                for r in info.get("movies", [])
            ]
            self.people: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r["id"]),
                    "name": r["name"],
                    "known_for_department": r["known_for_department"],
                    "gender": _to_int(r["gender"]),
                    "popularity": _to_float(r["popularity"]),
                }
                for r in info.get("people", [])
            ]
            self.credits: List[Dict[str, Any]] = [
                {
                    "movie_id": _to_int(r["movie_id"]),
                    "person_id": _to_int(r["person_id"]),
                    "credit_type": r["credit_type"],
                    "character": r["character"],
                    "job": r["job"],
                    "order": _to_int(r["order"]),
                }
                for r in info.get("credits", [])
            ]
            self.tv: List[Dict[str, Any]] = [
                {
                    "id": _to_int(r["id"]),
                    "name": r["name"],
                    "original_name": r["name"],
                    "overview": r["overview"],
                    "first_air_date": r["first_air_date"],
                    "vote_average": _to_float(r["vote_average"]),
                    "vote_count": _to_int(r["vote_count"]),
                    "genre_ids": _genre_ids(r["genre_ids"]),
                    "popularity": _to_float(r["popularity"]),
                    "number_of_seasons": _to_int(r["number_of_seasons"]),
                    "number_of_episodes": _to_int(r["number_of_episodes"]),
                    "media_type": "tv",
                }
                for r in info.get("tv", [])
            ]
            self._people_by_id = {p["id"]: p for p in self.people}
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTMDB')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"movies": self.movies, "tv": self.tv}

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _page(results, page=1, page_size=20):
        page = max(1, page)
        start = (page - 1) * page_size
        sliced = results[start: start + page_size]
        total = len(results)
        return {
            "page": page,
            "results": sliced,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "total_results": total,
        }

    # --- search ------------------------------------------------------------
    def search_movie(self, query: str, page: int = 1) -> Dict[str, Any]:
        q = (query or "").lower()
        matches = [m for m in self.movies if q in m["title"].lower()]
        matches.sort(key=lambda m: m["popularity"], reverse=True)
        return {"status": "ok", "output": self._page(matches, page=page)}

    # --- movies ------------------------------------------------------------
    def movie_popular(self, page: int = 1) -> Dict[str, Any]:
        movies = sorted(self.movies, key=lambda m: m["popularity"], reverse=True)
        return {"status": "ok", "output": self._page(movies, page=page)}

    def get_movie(self, movie_id: int) -> Dict[str, Any]:
        m = next((x for x in self.movies if x["id"] == movie_id), None)
        if not m:
            return {"status": "failed", "output": f"movie {movie_id} not found"}
        genre_lookup = {g["id"]: g["name"] for g in self.genres}
        out = dict(m)
        out["genres"] = [{"id": gid, "name": genre_lookup.get(gid, "Unknown")} for gid in m["genre_ids"]]
        return {"status": "ok", "output": out}

    def movie_credits(self, movie_id: int) -> Dict[str, Any]:
        if not any(x["id"] == movie_id for x in self.movies):
            return {"status": "failed", "output": f"movie {movie_id} not found"}
        cast, crew = [], []
        for c in self.credits:
            if c["movie_id"] != movie_id:
                continue
            person = self._people_by_id.get(c["person_id"], {})
            base = {
                "id": c["person_id"],
                "name": person.get("name", "Unknown"),
                "known_for_department": person.get("known_for_department", ""),
                "popularity": person.get("popularity", 0.0),
            }
            if c["credit_type"] == "cast":
                cast.append({**base, "character": c["character"], "order": c["order"]})
            else:
                crew.append({**base, "job": c["job"], "department": person.get("known_for_department", "")})
        cast.sort(key=lambda c: c["order"])
        return {"status": "ok", "output": {"id": movie_id, "cast": cast, "crew": crew}}

    # --- tv ----------------------------------------------------------------
    def get_tv(self, tv_id: int) -> Dict[str, Any]:
        t = next((x for x in self.tv if x["id"] == tv_id), None)
        if not t:
            return {"status": "failed", "output": f"tv {tv_id} not found"}
        genre_lookup = {g["id"]: g["name"] for g in self.genres}
        out = dict(t)
        out["genres"] = [{"id": gid, "name": genre_lookup.get(gid, "Unknown")} for gid in t["genre_ids"]]
        return {"status": "ok", "output": out}

    # --- genres ------------------------------------------------------------
    def genre_movie_list(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"genres": self.genres}}

    # --- trending ----------------------------------------------------------
    def trending_all_week(self, page: int = 1) -> Dict[str, Any]:
        combined = list(self.movies) + list(self.tv)
        combined.sort(key=lambda x: x["popularity"], reverse=True)
        return {"status": "ok", "output": self._page(combined, page=page)}


if __name__ == "__main__":
    s = TmdbSession(seed=12)
    print(s.movie_popular())
    print(s.genre_movie_list())
