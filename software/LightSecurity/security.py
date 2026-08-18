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


SENSOR_KINDS = ("door", "window", "motion", "smoke", "water")
ACCESS_METHODS = ("keypad", "phone", "keycard", "face")
EVENT_KINDS = ("armed", "disarmed", "triggered", "resolved", "recording_started",
               "recording_stopped", "access_granted", "access_denied", "info")
SOURCE_KINDS = ("camera", "sensor", "alarm", "user", "system")

SEED_CAMERAS = [
    ("Front Door Cam", "Front Door",  True,  "1080p", True),
    ("Backyard Cam",   "Backyard",    False, "720p",  True),
    ("Living Room Cam","Living Room", False, "1080p", False),
]

SEED_SENSORS = [
    ("Front Door Sensor",   "Front Door",  "door",   True,  -1),
    ("Bedroom Window",      "Bedroom",     "window", True,  -1),
    ("Hall Motion",         "Hallway",     "motion", True,  -1),
    ("Kitchen Smoke Alarm", "Kitchen",     "smoke",  True,  -3),
    ("Basement Water",      "Basement",    "water",  False, -1),
]

SEED_ALARMS = [
    (2, "motion",  -10, "Late-night motion in hallway"),
    (3, "smoke",   -3,  "Smoke sensor tripped during cooking"),
]

SEED_EVENTS = [
    ("sensor", 0, "triggered",         -10, "Front door opened"),
    ("system", 0, "armed",             -9,  "Home armed to away mode"),
    ("sensor", 2, "triggered",         -10, "Hallway motion detected"),
    ("camera", 0, "recording_started", -8,  "Front cam started recording"),
    ("user",   0, "access_granted",    -5,  "Owner unlocked front door via face"),
    ("system", 0, "disarmed",          -5,  "Home disarmed"),
]

SEED_ACCESS_LOGS = [
    ("owner",  "unlock", -5, "face"),
    ("guest",  "unlock", -4, "keypad"),
    ("owner",  "lock",   -4, "phone"),
    ("cleaner","unlock", -2, "keycard"),
    ("owner",  "unlock", -1, "face"),
]


@dataclass
class Camera:
    caid: str
    name: str
    room: str
    is_recording: bool = False
    resolution: str = "1080p"
    night_vision: bool = True


@dataclass
class Sensor:
    seid: str
    name: str
    room: str
    kind: str
    is_active: bool = True
    last_triggered: str = ""


@dataclass
class Alarm:
    alid: str
    sensor_id: str
    triggered_at: str
    kind: str
    resolved_at: str = ""
    notes: str = ""


@dataclass
class Event:
    evid: str
    source_kind: str
    source_id: str
    kind: str
    timestamp: str
    description: str = ""


@dataclass
class AccessLog:
    aclid: str
    user: str
    action: str
    timestamp: str
    method: str


class SecuritySession:
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
            self.cameras: Dict[str, Camera] = {}
            self.sensors: Dict[str, Sensor] = {}
            self.alarms: Dict[str, Alarm] = {}
            self.events: Dict[str, Event] = {}
            self.access_logs: Dict[str, AccessLog] = {}
            self._seed_cameras()
            self._seed_sensors()
            self._seed_alarms()
            self._seed_events()
            self._seed_access_logs()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSecurity')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _ts_offset(self, hours_offset: int) -> str:
        return (self._today + timedelta(hours=hours_offset)).isoformat(timespec="minutes")

    def _seed_cameras(self) -> None:
        self._seed_caids: List[str] = []
        for name, room, is_rec, res, nv in SEED_CAMERAS:
            c = Camera(
                caid=self.uuid(),
                name=name,
                room=room,
                is_recording=is_rec,
                resolution=res,
                night_vision=nv,
            )
            self.cameras[c.caid] = c
            self._seed_caids.append(c.caid)

    def _seed_sensors(self) -> None:
        self._seed_seids: List[str] = []
        for name, room, kind, is_active, last_h in SEED_SENSORS:
            s = Sensor(
                seid=self.uuid(),
                name=name,
                room=room,
                kind=kind,
                is_active=is_active,
                last_triggered=self._ts_offset(last_h) if last_h else "",
            )
            self.sensors[s.seid] = s
            self._seed_seids.append(s.seid)

    def _seed_alarms(self) -> None:
        for sensor_idx, kind, hours_offset, notes in SEED_ALARMS:
            if sensor_idx >= len(self._seed_seids):
                continue
            a = Alarm(
                alid=self.uuid(),
                sensor_id=self._seed_seids[sensor_idx],
                triggered_at=self._ts_offset(hours_offset),
                kind=kind,
                resolved_at=self._ts_offset(hours_offset + 1),
                notes=notes,
            )
            self.alarms[a.alid] = a

    def _seed_events(self) -> None:
        for src_kind, idx, ekind, hours_offset, desc in SEED_EVENTS:
            if src_kind == "camera":
                src_id = self._seed_caids[idx] if idx < len(self._seed_caids) else ""
            elif src_kind == "sensor":
                src_id = self._seed_seids[idx] if idx < len(self._seed_seids) else ""
            else:
                src_id = "system"
            e = Event(
                evid=self.uuid(),
                source_kind=src_kind,
                source_id=src_id,
                kind=ekind,
                timestamp=self._ts_offset(hours_offset),
                description=desc,
            )
            self.events[e.evid] = e

    def _seed_access_logs(self) -> None:
        for user, action, hours_offset, method in SEED_ACCESS_LOGS:
            l = AccessLog(
                aclid=self.uuid(),
                user=user,
                action=action,
                timestamp=self._ts_offset(hours_offset),
                method=method,
            )
            self.access_logs[l.aclid] = l

    def get_session_dict(self) -> Dict:
        return {
            "cameras": {caid: asdict(c) for caid, c in self.cameras.items()},
            "sensors": {seid: asdict(s) for seid, s in self.sensors.items()},
            "alarms": {alid: asdict(a) for alid, a in self.alarms.items()},
            "events": {evid: asdict(e) for evid, e in self.events.items()},
            "access_logs": {aclid: asdict(l) for aclid, l in self.access_logs.items()},
        }

    def _log_event(self, source_kind: str, source_id: str, kind: str, description: str = "") -> Event:
        e = Event(
            evid=self.uuid(),
            source_kind=source_kind,
            source_id=source_id,
            kind=kind,
            timestamp=self._now(),
            description=description,
        )
        self.events[e.evid] = e
        return e

    def list_cameras(self) -> Dict:
        return {"status": "ok", "output": [asdict(c) for c in self.cameras.values()]}

    def get_camera(self, caid: str) -> Dict:
        c = self.cameras.get(caid)
        if not c:
            return {"status": "failed", "output": f"camera {caid} not found"}
        return {"status": "ok", "output": asdict(c)}

    def add_camera(self, name: str, room: str,
                   resolution: str = "1080p",
                   night_vision: bool = True) -> Dict:
        c = Camera(
            caid=self.uuid(),
            name=name,
            room=room,
            is_recording=False,
            resolution=resolution,
            night_vision=night_vision,
        )
        self.cameras[c.caid] = c
        return {"status": "ok", "output": asdict(c)}

    def start_recording(self, caid: str) -> Dict:
        c = self.cameras.get(caid)
        if not c:
            return {"status": "failed", "output": f"camera {caid} not found"}
        c.is_recording = True
        self._log_event("camera", caid, "recording_started", f"{c.name} started recording")
        return {"status": "ok", "output": asdict(c)}

    def stop_recording(self, caid: str) -> Dict:
        c = self.cameras.get(caid)
        if not c:
            return {"status": "failed", "output": f"camera {caid} not found"}
        c.is_recording = False
        self._log_event("camera", caid, "recording_stopped", f"{c.name} stopped recording")
        return {"status": "ok", "output": asdict(c)}

    def list_sensors(self, kind: Optional[str] = None, room: Optional[str] = None) -> Dict:
        items = list(self.sensors.values())
        if kind:
            items = [s for s in items if s.kind == kind]
        if room:
            items = [s for s in items if s.room == room]
        items.sort(key=lambda s: s.name)
        return {"status": "ok", "output": [asdict(s) for s in items]}

    def get_sensor(self, seid: str) -> Dict:
        s = self.sensors.get(seid)
        if not s:
            return {"status": "failed", "output": f"sensor {seid} not found"}
        return {"status": "ok", "output": asdict(s)}

    def arm_sensor(self, seid: str) -> Dict:
        s = self.sensors.get(seid)
        if not s:
            return {"status": "failed", "output": f"sensor {seid} not found"}
        s.is_active = True
        self._log_event("sensor", seid, "armed", f"{s.name} armed")
        return {"status": "ok", "output": asdict(s)}

    def disarm_sensor(self, seid: str) -> Dict:
        s = self.sensors.get(seid)
        if not s:
            return {"status": "failed", "output": f"sensor {seid} not found"}
        s.is_active = False
        self._log_event("sensor", seid, "disarmed", f"{s.name} disarmed")
        return {"status": "ok", "output": asdict(s)}

    def trigger_sensor(self, seid: str) -> Dict:
        s = self.sensors.get(seid)
        if not s:
            return {"status": "failed", "output": f"sensor {seid} not found"}
        s.last_triggered = self._now()
        self._log_event("sensor", seid, "triggered", f"{s.name} triggered")
        alarm = Alarm(
            alid=self.uuid(),
            sensor_id=seid,
            triggered_at=self._now(),
            kind=s.kind,
            resolved_at="",
            notes="",
        )
        self.alarms[alarm.alid] = alarm
        return {"status": "ok", "output": {"sensor": asdict(s), "alarm": asdict(alarm)}}

    def list_alarms(self, resolved: Optional[bool] = None) -> Dict:
        items = list(self.alarms.values())
        if resolved is True:
            items = [a for a in items if a.resolved_at]
        elif resolved is False:
            items = [a for a in items if not a.resolved_at]
        items.sort(key=lambda a: a.triggered_at, reverse=True)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def resolve_alarm(self, alid: str, notes: str = "") -> Dict:
        a = self.alarms.get(alid)
        if not a:
            return {"status": "failed", "output": f"alarm {alid} not found"}
        if a.resolved_at:
            return {"status": "failed", "output": f"alarm {alid} already resolved"}
        a.resolved_at = self._now()
        if notes:
            a.notes = notes
        self._log_event("alarm", alid, "resolved", notes or "alarm resolved")
        return {"status": "ok", "output": asdict(a)}

    def list_events(self, kind: Optional[str] = None, source_kind: Optional[str] = None) -> Dict:
        items = list(self.events.values())
        if kind:
            items = [e for e in items if e.kind == kind]
        if source_kind:
            items = [e for e in items if e.source_kind == source_kind]
        items.sort(key=lambda e: e.timestamp, reverse=True)
        return {"status": "ok", "output": [asdict(e) for e in items]}

    def record_event(self, source_kind: str, source_id: str, kind: str, description: str = "") -> Dict:
        if source_kind not in SOURCE_KINDS:
            return {"status": "failed", "output": f"source_kind must be one of {SOURCE_KINDS}"}
        e = self._log_event(source_kind, source_id, kind, description)
        return {"status": "ok", "output": asdict(e)}

    def list_access_logs(self, user: Optional[str] = None) -> Dict:
        items = list(self.access_logs.values())
        if user:
            items = [l for l in items if l.user == user]
        items.sort(key=lambda l: l.timestamp, reverse=True)
        return {"status": "ok", "output": [asdict(l) for l in items]}

    def record_access(self, user: str, action: str, method: str) -> Dict:
        if method not in ACCESS_METHODS:
            return {"status": "failed", "output": f"method must be one of {ACCESS_METHODS}"}
        l = AccessLog(
            aclid=self.uuid(),
            user=user,
            action=action,
            timestamp=self._now(),
            method=method,
        )
        self.access_logs[l.aclid] = l
        self._log_event("user", user, f"access_{action}", f"{user} {action} via {method}")
        return {"status": "ok", "output": asdict(l)}

    def arm_all_sensors(self) -> Dict:
        count = 0
        for s in self.sensors.values():
            if not s.is_active:
                s.is_active = True
                count += 1
        self._log_event("system", "system", "armed", f"armed {count} sensors")
        return {"status": "ok", "output": {"armed": count, "total": len(self.sensors)}}

    def disarm_all_sensors(self) -> Dict:
        count = 0
        for s in self.sensors.values():
            if s.is_active:
                s.is_active = False
                count += 1
        self._log_event("system", "system", "disarmed", f"disarmed {count} sensors")
        return {"status": "ok", "output": {"disarmed": count, "total": len(self.sensors)}}

    def get_stats(self) -> Dict:
        active_sensors = sum(1 for s in self.sensors.values() if s.is_active)
        recording_cams = sum(1 for c in self.cameras.values() if c.is_recording)
        unresolved = sum(1 for a in self.alarms.values() if not a.resolved_at)
        by_sensor_kind: Dict[str, int] = {k: 0 for k in SENSOR_KINDS}
        for s in self.sensors.values():
            by_sensor_kind[s.kind] = by_sensor_kind.get(s.kind, 0) + 1
        return {
            "status": "ok",
            "output": {
                "cameras": len(self.cameras),
                "sensors": len(self.sensors),
                "alarms": len(self.alarms),
                "events": len(self.events),
                "access_logs": len(self.access_logs),
                "active_sensors": active_sensors,
                "recording_cameras": recording_cams,
                "unresolved_alarms": unresolved,
                "by_sensor_kind": by_sensor_kind,
            },
        }
