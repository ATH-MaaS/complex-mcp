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


DEVICE_KINDS = ("light", "thermostat", "plug", "speaker", "tv", "curtain", "fan")

DEFAULT_ROOMS = [
    {"rmid": "rm_living",  "name": "Living Room", "floor": 1},
    {"rmid": "rm_bedroom", "name": "Bedroom",     "floor": 2},
    {"rmid": "rm_kitchen", "name": "Kitchen",     "floor": 1},
    {"rmid": "rm_office",  "name": "Office",      "floor": 2},
]

SEED_DEVICES = [
    ("Living Ceiling Light",  "rm_living",  "light",      True,  70, None,   "#FFE4B5"),
    ("Living TV",             "rm_living",  "tv",         False, None, None, None),
    ("Living Thermostat",     "rm_living",  "thermostat", True,  None, 22.0, None),
    ("Bedroom Lamp",          "rm_bedroom", "light",      False, 40,  None,  "#FFDDAA"),
    ("Bedroom Curtain",       "rm_bedroom", "curtain",    False, None, None, None),
    ("Kitchen Plug",          "rm_kitchen", "plug",       True,  None, None, None),
    ("Kitchen Speaker",       "rm_kitchen", "speaker",    False, None, None, None),
    ("Office Fan",            "rm_office",  "fan",        False, None, None, None),
]

SEED_SCENES = [
    ("Movie Night", [
        {"device_index": 0, "state_patch": {"on": True, "brightness": 20}},
        {"device_index": 1, "state_patch": {"on": True}},
        {"device_index": 2, "state_patch": {"on": True, "temperature": 21.0}},
    ]),
    ("Wake Up", [
        {"device_index": 3, "state_patch": {"on": True, "brightness": 60}},
        {"device_index": 4, "state_patch": {"on": True}},
        {"device_index": 6, "state_patch": {"on": True}},
    ]),
    ("Away", [
        {"device_index": 0, "state_patch": {"on": False}},
        {"device_index": 1, "state_patch": {"on": False}},
        {"device_index": 3, "state_patch": {"on": False}},
        {"device_index": 5, "state_patch": {"on": False}},
        {"device_index": 7, "state_patch": {"on": False}},
    ]),
]

SEED_AUTOMATIONS = [
    ("Sunset Lights",    "time:18:30",          "scene:Movie Night", True),
    ("Morning Routine",  "time:07:00",          "scene:Wake Up",     True),
]


@dataclass
class Room:
    rmid: str
    name: str
    floor: int


@dataclass
class Device:
    dvid: str
    name: str
    room_id: str
    kind: str
    state: Dict = field(default_factory=dict)
    is_online: bool = True
    last_seen: str = ""


@dataclass
class Scene:
    scid: str
    name: str
    actions: List[Dict] = field(default_factory=list)


@dataclass
class Automation:
    auid: str
    name: str
    trigger: str
    action: str
    is_enabled: bool = True


class HomeSession:
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
            self.rooms: Dict[str, Room] = {r["rmid"]: Room(**r) for r in DEFAULT_ROOMS}
            self.devices: Dict[str, Device] = {}
            self.scenes: Dict[str, Scene] = {}
            self.automations: Dict[str, Automation] = {}
            self._seed_devices()
            self._seed_scenes()
            self._seed_automations()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightHome')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _default_state(self, kind: str, on: bool, brightness, temperature, color) -> Dict:
        return {
            "on": bool(on),
            "brightness": brightness,
            "temperature": temperature,
            "color": color,
        }

    def _seed_devices(self) -> None:
        self._seed_dvids: List[str] = []
        for name, room_id, kind, on, brightness, temperature, color in SEED_DEVICES:
            d = Device(
                dvid=self.uuid(),
                name=name,
                room_id=room_id,
                kind=kind,
                state=self._default_state(kind, on, brightness, temperature, color),
                is_online=True,
                last_seen=self._now(),
            )
            self.devices[d.dvid] = d
            self._seed_dvids.append(d.dvid)

    def _seed_scenes(self) -> None:
        for name, actions in SEED_SCENES:
            resolved = []
            for a in actions:
                idx = a["device_index"]
                if idx < len(self._seed_dvids):
                    resolved.append({
                        "dvid": self._seed_dvids[idx],
                        "state_patch": dict(a["state_patch"]),
                    })
            s = Scene(scid=self.uuid(), name=name, actions=resolved)
            self.scenes[s.scid] = s

    def _seed_automations(self) -> None:
        for name, trigger, action, enabled in SEED_AUTOMATIONS:
            a = Automation(
                auid=self.uuid(),
                name=name,
                trigger=trigger,
                action=action,
                is_enabled=enabled,
            )
            self.automations[a.auid] = a

    def get_session_dict(self) -> Dict:
        return {
            "rooms": {rmid: asdict(r) for rmid, r in self.rooms.items()},
            "devices": {dvid: asdict(d) for dvid, d in self.devices.items()},
            "scenes": {scid: asdict(s) for scid, s in self.scenes.items()},
            "automations": {auid: asdict(a) for auid, a in self.automations.items()},
        }

    def _device_summary(self, d: Device) -> Dict:
        return {
            "dvid": d.dvid,
            "name": d.name,
            "room_id": d.room_id,
            "kind": d.kind,
            "state": dict(d.state),
            "is_online": d.is_online,
            "last_seen": d.last_seen,
        }

    def list_rooms(self) -> Dict:
        return {"status": "ok", "output": [asdict(r) for r in self.rooms.values()]}

    def add_room(self, name: str, floor: int) -> Dict:
        rmid = "rm_" + self.uuid()[:8]
        r = Room(rmid=rmid, name=name, floor=floor)
        self.rooms[rmid] = r
        return {"status": "ok", "output": asdict(r)}

    def list_devices(self, room_id: Optional[str] = None, kind: Optional[str] = None) -> Dict:
        items = list(self.devices.values())
        if room_id:
            items = [d for d in items if d.room_id == room_id]
        if kind:
            items = [d for d in items if d.kind == kind]
        items.sort(key=lambda d: d.name)
        return {"status": "ok", "output": [self._device_summary(d) for d in items]}

    def get_device(self, dvid: str) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        return {"status": "ok", "output": asdict(d)}

    def add_device(self, name: str, room_id: str, kind: str,
                   brightness: Optional[int] = None,
                   temperature: Optional[float] = None,
                   color: Optional[str] = None) -> Dict:
        if room_id not in self.rooms:
            return {"status": "failed", "output": f"room {room_id} not found"}
        if kind not in DEVICE_KINDS:
            return {"status": "failed", "output": f"kind must be one of {DEVICE_KINDS}"}
        d = Device(
            dvid=self.uuid(),
            name=name,
            room_id=room_id,
            kind=kind,
            state=self._default_state(kind, False, brightness, temperature, color),
            is_online=True,
            last_seen=self._now(),
        )
        self.devices[d.dvid] = d
        return {"status": "ok", "output": self._device_summary(d)}

    def remove_device(self, dvid: str) -> Dict:
        d = self.devices.pop(dvid, None)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        for s in self.scenes.values():
            s.actions = [a for a in s.actions if a.get("dvid") != dvid]
        return {"status": "ok", "output": {"dvid": dvid, "deleted": True}}

    def turn_on(self, dvid: str) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        d.state["on"] = True
        d.last_seen = self._now()
        return {"status": "ok", "output": self._device_summary(d)}

    def turn_off(self, dvid: str) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        d.state["on"] = False
        d.last_seen = self._now()
        return {"status": "ok", "output": self._device_summary(d)}

    def set_brightness(self, dvid: str, brightness: int) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        if not (0 <= brightness <= 100):
            return {"status": "failed", "output": "brightness must be 0..100"}
        d.state["brightness"] = brightness
        d.last_seen = self._now()
        return {"status": "ok", "output": self._device_summary(d)}

    def set_temperature(self, dvid: str, temperature: float) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        d.state["temperature"] = float(temperature)
        d.last_seen = self._now()
        return {"status": "ok", "output": self._device_summary(d)}

    def set_color(self, dvid: str, color: str) -> Dict:
        d = self.devices.get(dvid)
        if not d:
            return {"status": "failed", "output": f"device {dvid} not found"}
        d.state["color"] = color
        d.last_seen = self._now()
        return {"status": "ok", "output": self._device_summary(d)}

    def list_scenes(self) -> Dict:
        return {"status": "ok", "output": [asdict(s) for s in self.scenes.values()]}

    def get_scene(self, scid: str) -> Dict:
        s = self.scenes.get(scid)
        if not s:
            return {"status": "failed", "output": f"scene {scid} not found"}
        return {"status": "ok", "output": asdict(s)}

    def create_scene(self, name: str, actions: List[Dict]) -> Dict:
        cleaned: List[Dict] = []
        for a in actions or []:
            dvid = a.get("dvid")
            patch = a.get("state_patch") or {}
            if dvid not in self.devices:
                return {"status": "failed", "output": f"device {dvid} not found"}
            cleaned.append({"dvid": dvid, "state_patch": dict(patch)})
        s = Scene(scid=self.uuid(), name=name, actions=cleaned)
        self.scenes[s.scid] = s
        return {"status": "ok", "output": asdict(s)}

    def activate_scene(self, scid: str) -> Dict:
        s = self.scenes.get(scid)
        if not s:
            return {"status": "failed", "output": f"scene {scid} not found"}
        applied = 0
        for a in s.actions:
            d = self.devices.get(a.get("dvid"))
            if not d:
                continue
            for k, v in (a.get("state_patch") or {}).items():
                d.state[k] = v
            d.last_seen = self._now()
            applied += 1
        return {"status": "ok", "output": {"scid": scid, "applied": applied}}

    def list_automations(self) -> Dict:
        return {"status": "ok", "output": [asdict(a) for a in self.automations.values()]}

    def toggle_automation(self, auid: str) -> Dict:
        a = self.automations.get(auid)
        if not a:
            return {"status": "failed", "output": f"automation {auid} not found"}
        a.is_enabled = not a.is_enabled
        return {"status": "ok", "output": asdict(a)}

    def get_stats(self) -> Dict:
        by_kind: Dict[str, int] = {k: 0 for k in DEVICE_KINDS}
        by_room: Dict[str, int] = {rmid: 0 for rmid in self.rooms}
        on_count = 0
        online_count = 0
        for d in self.devices.values():
            by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
            by_room[d.room_id] = by_room.get(d.room_id, 0) + 1
            if d.state.get("on"):
                on_count += 1
            if d.is_online:
                online_count += 1
        return {
            "status": "ok",
            "output": {
                "rooms": len(self.rooms),
                "devices": len(self.devices),
                "scenes": len(self.scenes),
                "automations": len(self.automations),
                "devices_on": on_count,
                "devices_online": online_count,
                "by_kind": by_kind,
                "by_room": by_room,
            },
        }
