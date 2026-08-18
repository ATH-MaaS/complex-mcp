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


SEED_ALBUMS = [
    ("Family",  "Family gatherings and holidays.", False),
    ("Travel",  "Trips near and far.",             True),
    ("Nature",  "Landscapes and wildlife.",        False),
]

SEED_PHOTOS = [
    (1, "Christmas Morning",   "IMG_0001.jpg", -14, ["family", "holiday"], "Home",              {"camera": "Sony A7 IV",  "iso": 400,  "aperture": "f/2.8", "shutter": "1/60",  "focal_length": "35mm"},  1),
    (1, "Grandma's Birthday",  "IMG_0002.jpg", -30, ["family", "party"],   "Home",              {"camera": "Sony A7 IV",  "iso": 800,  "aperture": "f/4.0", "shutter": "1/125", "focal_length": "50mm"},  1),
    (1, "Kids on the Sofa",    "IMG_0003.jpg", -7,  ["family", "kids"],    "Home",              {"camera": "iPhone 15",   "iso": 200,  "aperture": "f/1.8", "shutter": "1/60",  "focal_length": "26mm"},  3),
    (2, "Kyoto Sunrise",       "IMG_0101.jpg", -40, ["travel", "japan"],   "Kyoto, Japan",      {"camera": "Fujifilm X-T5","iso": 100,  "aperture": "f/8.0", "shutter": "1/250", "focal_length": "23mm"},  None),
    (2, "Roman Colosseum",     "IMG_0102.jpg", -60, ["travel", "italy"],   "Rome, Italy",       {"camera": "Fujifilm X-T5","iso": 200,  "aperture": "f/11",  "shutter": "1/500", "focal_length": "18mm"},  None),
    (2, "Paris Cafe",          "IMG_0103.jpg", -55, ["travel", "france"],  "Paris, France",     {"camera": "Fujifilm X-T5","iso": 800,  "aperture": "f/2.0", "shutter": "1/125", "focal_length": "35mm"},  2),
    (2, "Iceland Aurora",      "IMG_0104.jpg", -20, ["travel", "iceland"], "Vik, Iceland",      {"camera": "Sony A7 IV",  "iso": 3200, "aperture": "f/1.4", "shutter": "8s",    "focal_length": "24mm"},  None),
    (3, "Redwood Forest",      "IMG_0201.jpg", -10, ["nature", "forest"],  "Muir Woods, CA",    {"camera": "Sony A7 IV",  "iso": 400,  "aperture": "f/5.6", "shutter": "1/60",  "focal_length": "28mm"},  None),
    (3, "Snowy Owl",           "IMG_0202.jpg", -5,  ["nature", "wildlife"],"Yellowstone, WY",   {"camera": "Nikon Z9",    "iso": 1600, "aperture": "f/5.6", "shutter": "1/1000","focal_length": "400mm"}, None),
    (3, "Mountain Lake",       "IMG_0203.jpg", -2,  ["nature", "landscape"],"Banff, Canada",    {"camera": "Fujifilm X-T5","iso": 100,  "aperture": "f/8.0", "shutter": "1/125", "focal_length": "16mm"},  None),
]

SEED_FACE_GROUPS = ["Mom", "Dad", "Kids"]

SEED_SHARE_LINKS = [
    (2, 30, 12),
    (1, 7,  3),
]


@dataclass
class Album:
    alid: str
    name: str
    description: str
    cover_photo_id: str
    created_at: str
    is_shared: bool


@dataclass
class Photo:
    pid: str
    album_id: str
    title: str
    filename: str
    taken_at: str
    tags: List[str] = field(default_factory=list)
    location: str = ""
    exif: Dict[str, object] = field(default_factory=dict)
    face_group_id: Optional[str] = None


@dataclass
class FaceGroup:
    fgid: str
    name: str
    photo_count: int = 0


@dataclass
class ShareLink:
    slid: str
    album_id: str
    url: str
    expires_at: str
    view_count: int = 0


class PhotoSession:
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
            self.albums: Dict[str, Album] = {}
            self.photos: Dict[str, Photo] = {}
            self.face_groups: Dict[str, FaceGroup] = {}
            self.share_links: Dict[str, ShareLink] = {}
            self._album_index: List[str] = []
            self._face_index: List[str] = []
            self._seed_albums()
            self._seed_face_groups()
            self._seed_photos()
            self._seed_share_links()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightPhoto')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _seed_albums(self) -> None:
        for name, desc, shared in SEED_ALBUMS:
            a = Album(
                alid=self.uuid(),
                name=name,
                description=desc,
                cover_photo_id="",
                created_at=self._now(),
                is_shared=shared,
            )
            self.albums[a.alid] = a
            self._album_index.append(a.alid)

    def _seed_face_groups(self) -> None:
        for name in SEED_FACE_GROUPS:
            fg = FaceGroup(fgid=self.uuid(), name=name, photo_count=0)
            self.face_groups[fg.fgid] = fg
            self._face_index.append(fg.fgid)

    def _seed_photos(self) -> None:
        for al_idx, title, filename, day_off, tags, location, exif, face_idx in SEED_PHOTOS:
            alid = self._album_index[al_idx - 1]
            fgid = self._face_index[face_idx - 1] if face_idx else None
            p = Photo(
                pid=self.uuid(),
                album_id=alid,
                title=title,
                filename=filename,
                taken_at=(self._today + timedelta(days=day_off)).isoformat(timespec="minutes"),
                tags=list(tags),
                location=location,
                exif=dict(exif),
                face_group_id=fgid,
            )
            self.photos[p.pid] = p
            if fgid:
                self.face_groups[fgid].photo_count += 1
            if not self.albums[alid].cover_photo_id:
                self.albums[alid].cover_photo_id = p.pid

    def _seed_share_links(self) -> None:
        for al_idx, days_valid, views in SEED_SHARE_LINKS:
            alid = self._album_index[al_idx - 1]
            slid = self.uuid()
            sl = ShareLink(
                slid=slid,
                album_id=alid,
                url=f"https://share.example.com/{slid[:12]}",
                expires_at=(self._today + timedelta(days=days_valid)).isoformat(timespec="minutes"),
                view_count=views,
            )
            self.share_links[sl.slid] = sl
            self.albums[alid].is_shared = True

    def get_session_dict(self) -> Dict:
        return {
            "albums": {alid: asdict(a) for alid, a in self.albums.items()},
            "photos": {pid: asdict(p) for pid, p in self.photos.items()},
            "face_groups": {fgid: asdict(fg) for fgid, fg in self.face_groups.items()},
            "share_links": {slid: asdict(sl) for slid, sl in self.share_links.items()},
        }

    def _photo_summary(self, p: Photo) -> Dict:
        return {
            "pid": p.pid,
            "album_id": p.album_id,
            "title": p.title,
            "filename": p.filename,
            "taken_at": p.taken_at,
            "tags": list(p.tags),
            "location": p.location,
            "face_group_id": p.face_group_id,
        }

    def list_albums(self) -> Dict:
        items = list(self.albums.values())
        items.sort(key=lambda a: a.name.lower())
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def get_album(self, alid: str) -> Dict:
        a = self.albums.get(alid)
        if not a:
            return {"status": "failed", "output": f"album {alid} not found"}
        photo_count = sum(1 for p in self.photos.values() if p.album_id == alid)
        out = asdict(a)
        out["photo_count"] = photo_count
        return {"status": "ok", "output": out}

    def create_album(self, name: str, description: str = "") -> Dict:
        a = Album(
            alid=self.uuid(),
            name=name,
            description=description,
            cover_photo_id="",
            created_at=self._now(),
            is_shared=False,
        )
        self.albums[a.alid] = a
        return {"status": "ok", "output": asdict(a)}

    def delete_album(self, alid: str) -> Dict:
        if alid not in self.albums:
            return {"status": "failed", "output": f"album {alid} not found"}
        del self.albums[alid]
        removed_photos = [pid for pid, p in self.photos.items() if p.album_id == alid]
        for pid in removed_photos:
            p = self.photos.pop(pid)
            if p.face_group_id and p.face_group_id in self.face_groups:
                self.face_groups[p.face_group_id].photo_count = max(
                    0, self.face_groups[p.face_group_id].photo_count - 1
                )
        removed_links = [slid for slid, sl in self.share_links.items() if sl.album_id == alid]
        for slid in removed_links:
            del self.share_links[slid]
        return {"status": "ok", "output": {
            "alid": alid,
            "removed_photos": len(removed_photos),
            "removed_share_links": len(removed_links),
        }}

    def update_album(self, alid: str,
                     name: Optional[str] = None,
                     description: Optional[str] = None,
                     cover_photo_id: Optional[str] = None) -> Dict:
        a = self.albums.get(alid)
        if not a:
            return {"status": "failed", "output": f"album {alid} not found"}
        if name is not None:
            a.name = name
        if description is not None:
            a.description = description
        if cover_photo_id is not None:
            if cover_photo_id not in self.photos or self.photos[cover_photo_id].album_id != alid:
                return {"status": "failed", "output": f"photo {cover_photo_id} not in album {alid}"}
            a.cover_photo_id = cover_photo_id
        return {"status": "ok", "output": asdict(a)}

    def list_photos(self, album_id: Optional[str] = None,
                    tag: Optional[str] = None,
                    face_group_id: Optional[str] = None) -> Dict:
        items = list(self.photos.values())
        if album_id:
            items = [p for p in items if p.album_id == album_id]
        if tag:
            items = [p for p in items if tag in p.tags]
        if face_group_id:
            items = [p for p in items if p.face_group_id == face_group_id]
        items.sort(key=lambda p: p.taken_at, reverse=True)
        return {"status": "ok", "output": [self._photo_summary(p) for p in items]}

    def get_photo(self, pid: str) -> Dict:
        p = self.photos.get(pid)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        return {"status": "ok", "output": asdict(p)}

    def add_photo(self, album_id: str, title: str, filename: str,
                  taken_at: Optional[str] = None,
                  tags: Optional[List[str]] = None,
                  location: str = "",
                  exif: Optional[Dict[str, object]] = None) -> Dict:
        if album_id not in self.albums:
            return {"status": "failed", "output": f"album {album_id} not found"}
        p = Photo(
            pid=self.uuid(),
            album_id=album_id,
            title=title,
            filename=filename,
            taken_at=taken_at or self._now(),
            tags=list(tags) if tags else [],
            location=location,
            exif=dict(exif) if exif else {},
            face_group_id=None,
        )
        self.photos[p.pid] = p
        if not self.albums[album_id].cover_photo_id:
            self.albums[album_id].cover_photo_id = p.pid
        return {"status": "ok", "output": self._photo_summary(p)}

    def delete_photo(self, pid: str) -> Dict:
        p = self.photos.pop(pid, None)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        if p.face_group_id and p.face_group_id in self.face_groups:
            self.face_groups[p.face_group_id].photo_count = max(
                0, self.face_groups[p.face_group_id].photo_count - 1
            )
        a = self.albums.get(p.album_id)
        if a and a.cover_photo_id == pid:
            replacement = next((x.pid for x in self.photos.values() if x.album_id == p.album_id), "")
            a.cover_photo_id = replacement
        return {"status": "ok", "output": {"pid": pid, "deleted": True}}

    def add_tag(self, pid: str, tag: str) -> Dict:
        p = self.photos.get(pid)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        if tag not in p.tags:
            p.tags.append(tag)
        return {"status": "ok", "output": self._photo_summary(p)}

    def remove_tag(self, pid: str, tag: str) -> Dict:
        p = self.photos.get(pid)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        if tag in p.tags:
            p.tags.remove(tag)
        return {"status": "ok", "output": self._photo_summary(p)}

    def move_to_album(self, pid: str, album_id: str) -> Dict:
        p = self.photos.get(pid)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        if album_id not in self.albums:
            return {"status": "failed", "output": f"album {album_id} not found"}
        old_album = self.albums.get(p.album_id)
        p.album_id = album_id
        if old_album and old_album.cover_photo_id == pid:
            replacement = next((x.pid for x in self.photos.values() if x.album_id == old_album.alid and x.pid != pid), "")
            old_album.cover_photo_id = replacement
        if not self.albums[album_id].cover_photo_id:
            self.albums[album_id].cover_photo_id = pid
        return {"status": "ok", "output": self._photo_summary(p)}

    def list_face_groups(self) -> Dict:
        items = list(self.face_groups.values())
        items.sort(key=lambda fg: fg.name.lower())
        return {"status": "ok", "output": [asdict(fg) for fg in items]}

    def create_face_group(self, name: str) -> Dict:
        fg = FaceGroup(fgid=self.uuid(), name=name, photo_count=0)
        self.face_groups[fg.fgid] = fg
        return {"status": "ok", "output": asdict(fg)}

    def assign_face(self, pid: str, fgid: str) -> Dict:
        p = self.photos.get(pid)
        if not p:
            return {"status": "failed", "output": f"photo {pid} not found"}
        if fgid not in self.face_groups:
            return {"status": "failed", "output": f"face group {fgid} not found"}
        if p.face_group_id and p.face_group_id in self.face_groups:
            self.face_groups[p.face_group_id].photo_count = max(
                0, self.face_groups[p.face_group_id].photo_count - 1
            )
        p.face_group_id = fgid
        self.face_groups[fgid].photo_count += 1
        return {"status": "ok", "output": self._photo_summary(p)}

    def create_share_link(self, album_id: str, expires_at: str) -> Dict:
        if album_id not in self.albums:
            return {"status": "failed", "output": f"album {album_id} not found"}
        slid = self.uuid()
        sl = ShareLink(
            slid=slid,
            album_id=album_id,
            url=f"https://share.example.com/{slid[:12]}",
            expires_at=expires_at,
            view_count=0,
        )
        self.share_links[sl.slid] = sl
        self.albums[album_id].is_shared = True
        return {"status": "ok", "output": asdict(sl)}

    def list_share_links(self, album_id: Optional[str] = None) -> Dict:
        items = list(self.share_links.values())
        if album_id:
            items = [sl for sl in items if sl.album_id == album_id]
        items.sort(key=lambda sl: sl.expires_at)
        return {"status": "ok", "output": [asdict(sl) for sl in items]}

    def get_stats(self) -> Dict:
        by_album: Dict[str, int] = {alid: 0 for alid in self.albums}
        by_tag: Dict[str, int] = {}
        for p in self.photos.values():
            by_album[p.album_id] = by_album.get(p.album_id, 0) + 1
            for t in p.tags:
                by_tag[t] = by_tag.get(t, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total_albums": len(self.albums),
                "total_photos": len(self.photos),
                "total_face_groups": len(self.face_groups),
                "total_share_links": len(self.share_links),
                "by_album": by_album,
                "by_tag": by_tag,
            },
        }
