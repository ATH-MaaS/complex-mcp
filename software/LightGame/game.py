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


PLATFORMS = ("pc", "playstation", "xbox", "switch", "mobile")
GENRES = ("rpg", "fps", "strategy", "puzzle", "sports", "action", "adventure", "simulation")

SEED_GAMES = [
    ("Elden Ring",          "pc",          "rpg",       -180, True,   4200, -1),
    ("Halo Infinite",       "xbox",        "fps",       -120, True,    900, -3),
    ("Civilization VI",     "pc",          "strategy",  -300, True,   2400, -14),
    ("Zelda: TotK",         "switch",      "adventure", -240, False,  1500, -60),
    ("Candy Crush",         "mobile",      "puzzle",     -90, True,    600, -2),
]

SEED_ACHIEVEMENTS = [
    (0, "Tarnished Rise",     "Defeat the first main boss",       10, True,  -170),
    (0, "Legend of the Lands","Complete the main quest",          50, False, None),
    (1, "First Blood",        "Get your first kill",               5, True,  -119),
    (1, "Spartan Elite",      "Reach level 50 multiplayer",       40, False, None),
    (2, "One More Turn",      "Play 100 turns in a single game",  15, True,  -299),
    (2, "Domination",         "Win a domination victory",         30, True,  -260),
    (3, "Sky's the Limit",    "Solve the first shrine",           10, True,  -239),
    (4, "Sweet Streak",       "Reach a 10-combo",                  5, True,   -89),
]

SEED_PLAY_SESSIONS = [
    (0,  -1,  120),
    (0,  -7,   90),
    (1,  -3,   60),
    (2, -14,  180),
    (2, -30,  240),
    (4,  -2,   30),
]

SEED_WISHLIST = [
    ("Starfield",        "pc",          -30, 59.99),
    ("Spider-Man 3",     "playstation", -14, 69.99),
    ("Pokemon Scarlet",  "switch",       -7, 49.99),
]


@dataclass
class Game:
    gid: str
    title: str
    platform: str
    genre: str
    added_at: str
    is_installed: bool = False
    playtime_minutes: int = 0
    last_played_at: str = ""


@dataclass
class Achievement:
    achid: str
    game_id: str
    name: str
    description: str
    points: int
    unlocked_at: str
    is_unlocked: bool


@dataclass
class PlaySession:
    psid: str
    game_id: str
    started_at: str
    ended_at: str
    duration_minutes: int


@dataclass
class Wishlist:
    wlid: str
    title: str
    platform: str
    added_at: str
    price: float


class GameSession:
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
            self.games: Dict[str, Game] = {}
            self.achievements: Dict[str, Achievement] = {}
            self.play_sessions: Dict[str, PlaySession] = {}
            self.wishlist: Dict[str, Wishlist] = {}
            self._game_order: List[str] = []
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGame')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _shift(self, days: int = 0, minutes: int = 0) -> str:
        return (self._today + timedelta(days=days, minutes=minutes)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        for title, platform, genre, added_offset, installed, playtime, last_offset in SEED_GAMES:
            g = Game(
                gid="gm_" + self.uuid()[:10],
                title=title,
                platform=platform,
                genre=genre,
                added_at=self._shift(days=added_offset),
                is_installed=installed,
                playtime_minutes=playtime,
                last_played_at=self._shift(days=last_offset),
            )
            self.games[g.gid] = g
            self._game_order.append(g.gid)
        for game_idx, name, desc, points, unlocked, unlock_offset in SEED_ACHIEVEMENTS:
            gid = self._game_order[game_idx]
            a = Achievement(
                achid="ac_" + self.uuid()[:10],
                game_id=gid,
                name=name,
                description=desc,
                points=points,
                unlocked_at=self._shift(days=unlock_offset) if unlock_offset is not None else "",
                is_unlocked=unlocked,
            )
            self.achievements[a.achid] = a
        for game_idx, start_offset, duration in SEED_PLAY_SESSIONS:
            gid = self._game_order[game_idx]
            start = self._shift(days=start_offset)
            end = self._shift(days=start_offset, minutes=duration)
            p = PlaySession(
                psid="ps_" + self.uuid()[:10],
                game_id=gid,
                started_at=start,
                ended_at=end,
                duration_minutes=duration,
            )
            self.play_sessions[p.psid] = p
        for title, platform, added_offset, price in SEED_WISHLIST:
            w = Wishlist(
                wlid="wl_" + self.uuid()[:10],
                title=title,
                platform=platform,
                added_at=self._shift(days=added_offset),
                price=price,
            )
            self.wishlist[w.wlid] = w

    def get_session_dict(self) -> Dict:
        return {
            "games":         {gid: asdict(g) for gid, g in self.games.items()},
            "achievements":  {aid: asdict(a) for aid, a in self.achievements.items()},
            "play_sessions": {pid: asdict(p) for pid, p in self.play_sessions.items()},
            "wishlist":      {wid: asdict(w) for wid, w in self.wishlist.items()},
        }

    def _game_summary(self, g: Game) -> Dict:
        return {
            "gid": g.gid,
            "title": g.title,
            "platform": g.platform,
            "genre": g.genre,
            "is_installed": g.is_installed,
            "playtime_minutes": g.playtime_minutes,
            "last_played_at": g.last_played_at,
        }

    def list_games(self, platform: Optional[str] = None,
                   genre: Optional[str] = None,
                   is_installed: Optional[bool] = None) -> Dict:
        items = list(self.games.values())
        if platform:
            items = [g for g in items if g.platform == platform]
        if genre:
            items = [g for g in items if g.genre == genre]
        if is_installed is not None:
            items = [g for g in items if g.is_installed == is_installed]
        items.sort(key=lambda g: g.title.lower())
        return {"status": "ok", "output": [self._game_summary(g) for g in items]}

    def get_game(self, gid: str) -> Dict:
        g = self.games.get(gid)
        if not g:
            return {"status": "failed", "output": f"game {gid} not found"}
        return {"status": "ok", "output": asdict(g)}

    def add_game(self, title: str, platform: str = "pc", genre: str = "action",
                 is_installed: bool = False) -> Dict:
        if platform not in PLATFORMS:
            return {"status": "failed", "output": f"platform must be one of {PLATFORMS}"}
        if genre not in GENRES:
            return {"status": "failed", "output": f"genre must be one of {GENRES}"}
        g = Game(
            gid="gm_" + self.uuid()[:10],
            title=title,
            platform=platform,
            genre=genre,
            added_at=self._now(),
            is_installed=is_installed,
            playtime_minutes=0,
            last_played_at="",
        )
        self.games[g.gid] = g
        return {"status": "ok", "output": self._game_summary(g)}

    def delete_game(self, gid: str) -> Dict:
        g = self.games.pop(gid, None)
        if not g:
            return {"status": "failed", "output": f"game {gid} not found"}
        removed_ach = [aid for aid, a in self.achievements.items() if a.game_id == gid]
        for aid in removed_ach:
            del self.achievements[aid]
        removed_ps = [pid for pid, p in self.play_sessions.items() if p.game_id == gid]
        for pid in removed_ps:
            del self.play_sessions[pid]
        return {"status": "ok", "output": {"gid": gid, "deleted": True,
                                            "removed_achievements": len(removed_ach),
                                            "removed_play_sessions": len(removed_ps)}}

    def install_game(self, gid: str) -> Dict:
        g = self.games.get(gid)
        if not g:
            return {"status": "failed", "output": f"game {gid} not found"}
        g.is_installed = True
        return {"status": "ok", "output": self._game_summary(g)}

    def uninstall_game(self, gid: str) -> Dict:
        g = self.games.get(gid)
        if not g:
            return {"status": "failed", "output": f"game {gid} not found"}
        g.is_installed = False
        return {"status": "ok", "output": self._game_summary(g)}

    def list_achievements(self, game_id: Optional[str] = None,
                          is_unlocked: Optional[bool] = None) -> Dict:
        items = list(self.achievements.values())
        if game_id:
            items = [a for a in items if a.game_id == game_id]
        if is_unlocked is not None:
            items = [a for a in items if a.is_unlocked == is_unlocked]
        items.sort(key=lambda a: (a.game_id, a.name.lower()))
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def unlock_achievement(self, achid: str) -> Dict:
        a = self.achievements.get(achid)
        if not a:
            return {"status": "failed", "output": f"achievement {achid} not found"}
        if a.is_unlocked:
            return {"status": "failed", "output": f"achievement {achid} already unlocked"}
        a.is_unlocked = True
        a.unlocked_at = self._now()
        return {"status": "ok", "output": asdict(a)}

    def list_play_sessions(self, game_id: Optional[str] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> Dict:
        items = list(self.play_sessions.values())
        if game_id:
            items = [p for p in items if p.game_id == game_id]
        if start_date:
            items = [p for p in items if p.started_at >= start_date]
        if end_date:
            items = [p for p in items if p.started_at <= end_date]
        items.sort(key=lambda p: p.started_at)
        return {"status": "ok", "output": [asdict(p) for p in items]}

    def start_play(self, game_id: str) -> Dict:
        g = self.games.get(game_id)
        if not g:
            return {"status": "failed", "output": f"game {game_id} not found"}
        p = PlaySession(
            psid="ps_" + self.uuid()[:10],
            game_id=game_id,
            started_at=self._now(),
            ended_at="",
            duration_minutes=0,
        )
        self.play_sessions[p.psid] = p
        g.last_played_at = p.started_at
        return {"status": "ok", "output": asdict(p)}

    def end_play(self, psid: str, duration_minutes: int) -> Dict:
        p = self.play_sessions.get(psid)
        if not p:
            return {"status": "failed", "output": f"play session {psid} not found"}
        if p.ended_at:
            return {"status": "failed", "output": f"play session {psid} already ended"}
        duration = max(0, int(duration_minutes))
        try:
            start_dt = datetime.fromisoformat(p.started_at)
            end_dt = start_dt + timedelta(minutes=duration)
            p.ended_at = end_dt.isoformat(timespec="minutes")
        except ValueError:
            p.ended_at = self._now()
        p.duration_minutes = duration
        g = self.games.get(p.game_id)
        if g:
            g.playtime_minutes += duration
            g.last_played_at = p.ended_at or self._now()
        return {"status": "ok", "output": asdict(p)}

    def get_total_playtime(self, game_id: str) -> Dict:
        g = self.games.get(game_id)
        if not g:
            return {"status": "failed", "output": f"game {game_id} not found"}
        session_total = sum(p.duration_minutes for p in self.play_sessions.values() if p.game_id == game_id)
        return {
            "status": "ok",
            "output": {
                "gid": game_id,
                "title": g.title,
                "playtime_minutes": g.playtime_minutes,
                "session_total_minutes": session_total,
            },
        }

    def list_wishlist(self) -> Dict:
        items = list(self.wishlist.values())
        items.sort(key=lambda w: w.added_at, reverse=True)
        return {"status": "ok", "output": [asdict(w) for w in items]}

    def add_to_wishlist(self, title: str, platform: str = "pc", price: float = 0.0) -> Dict:
        if platform not in PLATFORMS:
            return {"status": "failed", "output": f"platform must be one of {PLATFORMS}"}
        w = Wishlist(
            wlid="wl_" + self.uuid()[:10],
            title=title,
            platform=platform,
            added_at=self._now(),
            price=float(price),
        )
        self.wishlist[w.wlid] = w
        return {"status": "ok", "output": asdict(w)}

    def remove_from_wishlist(self, wlid: str) -> Dict:
        w = self.wishlist.pop(wlid, None)
        if not w:
            return {"status": "failed", "output": f"wishlist item {wlid} not found"}
        return {"status": "ok", "output": {"wlid": wlid, "removed": True}}

    def search_games(self, query: str) -> Dict:
        q = query.lower()
        items = [
            g for g in self.games.values()
            if q in g.title.lower() or q in g.platform.lower() or q in g.genre.lower()
        ]
        items.sort(key=lambda g: g.title.lower())
        return {"status": "ok", "output": [self._game_summary(g) for g in items]}

    def get_stats(self) -> Dict:
        by_platform: Dict[str, int] = {p: 0 for p in PLATFORMS}
        by_genre: Dict[str, int] = {g: 0 for g in GENRES}
        installed = 0
        total_playtime = 0
        for g in self.games.values():
            by_platform[g.platform] = by_platform.get(g.platform, 0) + 1
            by_genre[g.genre] = by_genre.get(g.genre, 0) + 1
            if g.is_installed:
                installed += 1
            total_playtime += g.playtime_minutes
        total_points_available = sum(a.points for a in self.achievements.values())
        total_points_unlocked = sum(a.points for a in self.achievements.values() if a.is_unlocked)
        return {
            "status": "ok",
            "output": {
                "total_games": len(self.games),
                "installed_games": installed,
                "total_achievements": len(self.achievements),
                "unlocked_achievements": sum(1 for a in self.achievements.values() if a.is_unlocked),
                "total_play_sessions": len(self.play_sessions),
                "total_playtime_minutes": total_playtime,
                "total_wishlist": len(self.wishlist),
                "achievement_points_unlocked": total_points_unlocked,
                "achievement_points_available": total_points_available,
                "by_platform": by_platform,
                "by_genre": by_genre,
            },
        }
