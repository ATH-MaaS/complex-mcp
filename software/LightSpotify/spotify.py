import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from copy import deepcopy
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"

_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class SpotifySession:
    """Deterministic sandbox for the Spotify Web API mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "spotify.yaml") as f:
                info = yaml.safe_load(f)

            self.artists: List[Dict[str, Any]] = [
                {
                    **a,
                    "genres": [g.strip() for g in str(a.get("genres") or "").split(",") if g.strip()],
                    "followers": _to_int(a.get("followers", 0)),
                    "popularity": _to_int(a.get("popularity", 0)),
                }
                for a in info.get("artists", [])
            ]
            self.albums: List[Dict[str, Any]] = [
                {**a, "total_tracks": _to_int(a.get("total_tracks", 0))}
                for a in info.get("albums", [])
            ]
            self.tracks: List[Dict[str, Any]] = [
                {
                    **t,
                    "duration_ms": _to_int(t.get("duration_ms", 0)),
                    "popularity": _to_int(t.get("popularity", 0)),
                    "explicit": _to_bool(t.get("explicit", False)),
                    "track_number": _to_int(t.get("track_number", 0)),
                }
                for t in info.get("tracks", [])
            ]
            self.playlists: List[Dict[str, Any]] = [
                {
                    **p,
                    "public": _to_bool(p.get("public", False)),
                    "collaborative": _to_bool(p.get("collaborative", False)),
                }
                for p in info.get("playlists", [])
            ]
            self.playlist_tracks: List[Dict[str, Any]] = [
                {**pt, "position": _to_int(pt.get("position", 0))}
                for pt in info.get("playlist_tracks", [])
            ]
            self.user: Dict[str, Any] = info.get("user", {})

            self._playback_state = {
                "is_playing": False,
                "device": {"id": "device-web-001", "name": "Web Player", "type": "Computer", "volume_percent": 65},
                "shuffle_state": False,
                "repeat_state": "off",
                "progress_ms": 0,
                "item": None,
            }
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSpotify')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"playlists": self.playlists, "playlist_tracks": self.playlist_tracks}

    # --- helpers -----------------------------------------------------------
    def uuid(self) -> str:
        return "".join(self.rng.choice(_BASE62) for _ in range(22))

    def _now_iso(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _artist_brief(self, artist_id):
        a = next((x for x in self.artists if x["artist_id"] == artist_id), None)
        if not a:
            return None
        return {"id": a["artist_id"], "name": a["name"]}

    def _album_brief(self, album_id):
        al = next((x for x in self.albums if x["album_id"] == album_id), None)
        if not al:
            return None
        return {"id": al["album_id"], "name": al["name"], "release_date": al["release_date"]}

    def _track_obj(self, t):
        return {
            "id": t["track_id"],
            "name": t["name"],
            "duration_ms": t["duration_ms"],
            "popularity": t["popularity"],
            "explicit": t["explicit"],
            "track_number": t["track_number"],
            "artist": self._artist_brief(t["artist_id"]),
            "album": self._album_brief(t["album_id"]),
            "uri": f"spotify:track:{t['track_id']}",
        }

    def _playlist_obj(self, p, with_tracks=False):
        obj = {
            "id": p["playlist_id"],
            "name": p["name"],
            "description": p["description"],
            "owner": {"id": p["owner_id"]},
            "public": p["public"],
            "collaborative": p["collaborative"],
            "uri": f"spotify:playlist:{p['playlist_id']}",
        }
        pts = sorted(
            [pt for pt in self.playlist_tracks if pt["playlist_id"] == p["playlist_id"]],
            key=lambda x: x["position"],
        )
        obj["tracks"] = {"total": len(pts)}
        if with_tracks:
            items = []
            for pt in pts:
                t = next((x for x in self.tracks if x["track_id"] == pt["track_id"]), None)
                if t:
                    items.append({"added_at": pt["added_at"], "track": self._track_obj(t)})
            obj["tracks"] = {"total": len(items), "items": items}
        return obj

    # --- user --------------------------------------------------------------
    def get_me(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.user}

    def list_my_playlists(self) -> Dict[str, Any]:
        items = [self._playlist_obj(p) for p in self.playlists
                 if p["owner_id"] == self.user["id"]]
        return {"status": "ok", "output": {"items": items, "total": len(items)}}

    # --- playlists ---------------------------------------------------------
    def get_playlist(self, playlist_id: str) -> Dict[str, Any]:
        for p in self.playlists:
            if p["playlist_id"] == playlist_id:
                return {"status": "ok", "output": self._playlist_obj(p, with_tracks=True)}
        return {"status": "failed", "output": f"Playlist {playlist_id} not found"}

    def get_playlist_tracks(self, playlist_id: str) -> Dict[str, Any]:
        p = next((x for x in self.playlists if x["playlist_id"] == playlist_id), None)
        if not p:
            return {"status": "failed", "output": f"Playlist {playlist_id} not found"}
        obj = self._playlist_obj(p, with_tracks=True)
        return {"status": "ok", "output": {"total": obj["tracks"]["total"], "items": obj["tracks"]["items"]}}

    def create_playlist(self, user_id: str, name: str, description: str = "",
                        public: bool = True, collaborative: bool = False) -> Dict[str, Any]:
        playlist_id = self.uuid()
        playlist = {
            "playlist_id": playlist_id,
            "name": name,
            "description": description,
            "owner_id": user_id,
            "public": bool(public),
            "collaborative": bool(collaborative),
        }
        self.playlists.append(playlist)
        return {"status": "ok", "output": self._playlist_obj(playlist, with_tracks=True)}

    def add_tracks(self, playlist_id: str, uris: List[str]) -> Dict[str, Any]:
        p = next((x for x in self.playlists if x["playlist_id"] == playlist_id), None)
        if not p:
            return {"status": "failed", "output": f"Playlist {playlist_id} not found"}
        existing = [pt for pt in self.playlist_tracks if pt["playlist_id"] == playlist_id]
        next_pos = max((pt["position"] for pt in existing), default=-1) + 1
        added = 0
        for uri in uris:
            track_id = uri.split(":")[-1] if ":" in uri else uri
            if not any(t["track_id"] == track_id for t in self.tracks):
                continue
            self.playlist_tracks.append({
                "playlist_id": playlist_id,
                "track_id": track_id,
                "position": next_pos,
                "added_at": self._now_iso(),
            })
            next_pos += 1
            added += 1
        return {"status": "ok", "output": {"playlist_id": playlist_id, "added": added,
                                           "snapshot_id": self.uuid()}}

    # --- search ------------------------------------------------------------
    def search(self, q: str, type: str | None = None) -> Dict[str, Any]:
        types = [t.strip() for t in type.split(",")] if type else None
        if not types:
            types = ["track", "album", "artist"]
        query = (q or "").lower()
        result = {}
        if "track" in types:
            hits = [self._track_obj(t) for t in self.tracks if query in t["name"].lower()]
            result["tracks"] = {"items": hits, "total": len(hits)}
        if "album" in types:
            hits = [{
                "id": a["album_id"], "name": a["name"], "album_type": a["album_type"],
                "release_date": a["release_date"], "total_tracks": a["total_tracks"],
                "artist": self._artist_brief(a["artist_id"]),
            } for a in self.albums if query in a["name"].lower()]
            result["albums"] = {"items": hits, "total": len(hits)}
        if "artist" in types:
            hits = [{
                "id": a["artist_id"], "name": a["name"], "genres": a["genres"],
                "followers": a["followers"], "popularity": a["popularity"],
            } for a in self.artists if query in a["name"].lower()]
            result["artists"] = {"items": hits, "total": len(hits)}
        return {"status": "ok", "output": result}

    # --- playback ----------------------------------------------------------
    def get_player(self) -> Dict[str, Any]:
        return {"status": "ok", "output": deepcopy(self._playback_state)}

    def start_playback(self, uris: List[str] | None = None,
                       context_uri: str | None = None) -> Dict[str, Any]:
        item = None
        if uris:
            track_id = uris[0].split(":")[-1]
            t = next((x for x in self.tracks if x["track_id"] == track_id), None)
            if t:
                item = self._track_obj(t)
        elif context_uri and context_uri.startswith("spotify:playlist:"):
            pid = context_uri.split(":")[-1]
            pts = sorted(
                [pt for pt in self.playlist_tracks if pt["playlist_id"] == pid],
                key=lambda x: x["position"],
            )
            if pts:
                t = next((x for x in self.tracks if x["track_id"] == pts[0]["track_id"]), None)
                if t:
                    item = self._track_obj(t)
        self._playback_state["is_playing"] = True
        self._playback_state["progress_ms"] = 0
        if item is not None:
            self._playback_state["item"] = item
        return {"status": "ok", "output": deepcopy(self._playback_state)}


if __name__ == "__main__":
    s = SpotifySession(seed=12)
    print(s.get_me())
    print(s.list_my_playlists())
