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


def _to_int(v):
    if v is None or v == "":
        return None
    return int(v)


class RingSession:
    """Deterministic sandbox for the Ring mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables/documents so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "ring.yaml") as f:
                info = yaml.safe_load(f)

            # devices / location / active_dings are documents (kept as loaded).
            self.devices: Dict[str, Any] = info.get("devices", {}) or {}
            self.location: Dict[str, Any] = info.get("location", {}) or {}
            self.active_dings: List[Dict[str, Any]] = list(info.get("active_dings", []) or [])

            # events: coerce string columns like the source _coerce_events.
            self.events: List[Dict[str, Any]] = [
                {
                    "id": int(e["id"]),
                    "doorbot_id": int(e["doorbot_id"]),
                    "device_id": e["device_id"],
                    "kind": e["kind"],
                    "created_at": e["created_at"],
                    "answered": _to_bool(e["answered"]),
                    "favorite": _to_bool(e["favorite"]),
                    "recording": {"status": e["recording_status"]},
                    "snapshot_url": e["snapshot_url"],
                    "duration_seconds": _to_int(e.get("duration_seconds")),
                    "cv_properties": (str(e.get("cv_properties") or "") or None),
                }
                for e in info.get("events", [])
            ]

            # shared_users: coerce user_id to int.
            self.shared_users: List[Dict[str, Any]] = [
                {
                    "user_id": int(u["user_id"]),
                    "first_name": u["first_name"],
                    "last_name": u["last_name"],
                    "email": u["email"],
                    "role": u["role"],
                    "device_access": u["device_access"],
                    "shared_at": u["shared_at"],
                }
                for u in info.get("shared_users", [])
            ]

            # motion_zones: coerce and synth composite pk device_id@zone_id.
            self.motion_zones: List[Dict[str, Any]] = [
                {
                    "device_id": int(z["device_id"]),
                    "zone_id": z["zone_id"],
                    "zone_name": z["zone_name"],
                    "sensitivity": int(z["sensitivity"]),
                    "enabled": _to_bool(z["enabled"]),
                    "coordinates": z["coordinates"],
                    "_pk": f"{int(z['device_id'])}@{z['zone_id']}",
                }
                for z in info.get("motion_zones", [])
            ]

            # notification_prefs: coerce and synth composite pk device_id/channel.
            self.notification_prefs: List[Dict[str, Any]] = []
            for p in info.get("notification_prefs", []):
                device_id = int(p["device_id"])
                channel = p.get("channel") or "push"
                self.notification_prefs.append({
                    "_pk": f"{device_id}/{channel}",
                    "device_id": device_id,
                    "channel": channel,
                    "motion_alerts": _to_bool(p["motion_alerts"]) if p.get("motion_alerts") else None,
                    "ding_alerts": _to_bool(p["ding_alerts"]) if p.get("ding_alerts") else None,
                    "person_alerts": _to_bool(p["person_alerts"]) if p.get("person_alerts") else None,
                    "package_alerts": _to_bool(p["package_alerts"]) if p.get("package_alerts") else None,
                })
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightRing')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"devices": self.devices, "events": self.events}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _find_device(self, device_id: int):
        for category in ["doorbots", "stickup_cams", "chimes"]:
            for dev in self.devices.get(category, []):
                if dev["id"] == device_id:
                    return dev, category
        return None, None

    def _notif_get(self, pk):
        for p in self.notification_prefs:
            if p["_pk"] == pk:
                return p
        return None

    def _notification_prefs_rows(self):
        return [{k: v for k, v in p.items() if k != "_pk"} for p in self.notification_prefs]

    # --- API methods -------------------------------------------------------
    def list_devices(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.devices}

    def get_device(self, device_id: int) -> Dict[str, Any]:
        device, category = self._find_device(device_id)
        if not device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        return {"status": "ok", "output": {"type": "device", "device_type": category, "device": device}}

    def get_device_health(self, device_id: int) -> Dict[str, Any]:
        device, category = self._find_device(device_id)
        if not device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        health = {
            "device_id": device_id,
            "firmware_version": device.get("firmware_version"),
            "battery_life": device.get("battery_life"),
            "wifi_signal_strength": device.get("wifi_signal_strength", -45),
            "wifi_signal_category": device.get("wifi_signal_category", "good"),
            "alerts": device.get("alerts", {}),
            "external_connection": device.get("external_connection", False),
        }
        return {"status": "ok", "output": {"type": "device_health", "device_health": health}}

    def update_device_settings(self, device_id: int, motion_sensitivity: int | None = None,
                               motion_detection_enabled: bool | None = None,
                               people_detection_enabled: bool | None = None,
                               package_detection_enabled: bool | None = None,
                               led_status: str | None = None,
                               light_schedule_enabled: bool | None = None,
                               light_on_duration_seconds: int | None = None) -> Dict[str, Any]:
        data = {}
        if motion_sensitivity is not None:
            data["motion_sensitivity"] = motion_sensitivity
        if motion_detection_enabled is not None:
            data["motion_detection_enabled"] = motion_detection_enabled
        if people_detection_enabled is not None:
            data["people_detection_enabled"] = people_detection_enabled
        if package_detection_enabled is not None:
            data["package_detection_enabled"] = package_detection_enabled
        if led_status is not None:
            data["led_status"] = led_status
        if light_schedule_enabled is not None:
            data["light_schedule_enabled"] = light_schedule_enabled
        if light_on_duration_seconds is not None:
            data["light_on_duration_seconds"] = light_on_duration_seconds

        updatable = {
            "motion_sensitivity", "motion_detection_enabled", "people_detection_enabled",
            "package_detection_enabled", "led_status", "light_schedule_enabled",
            "light_on_duration_seconds",
        }
        device, category = self._find_device(device_id)
        if not device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        settings = device.get("settings", {})
        for k, v in data.items():
            if k in updatable:
                settings[k] = v
            elif k == "led_status":
                device["led_status"] = v
        device["settings"] = settings
        return {"status": "ok", "output": {"type": "device", "device_type": category, "device": device}}

    def get_location(self, location_id: str) -> Dict[str, Any]:
        loc = self.location
        if location_id != loc["location_id"]:
            return {"status": "failed", "output": f"Location {location_id} not found"}
        return {"status": "ok", "output": {"type": "location", "location": loc}}

    def list_location_devices(self, location_id: str) -> Dict[str, Any]:
        loc = self.location
        if location_id != loc["location_id"]:
            return {"status": "failed", "output": f"Location {location_id} not found"}
        return {"status": "ok", "output": self.devices}

    def get_location_mode(self, location_id: str) -> Dict[str, Any]:
        loc = self.location
        if location_id != loc["location_id"]:
            return {"status": "failed", "output": f"Location {location_id} not found"}
        return {"status": "ok", "output": {"type": "mode", "mode": loc["mode"], "location_id": location_id}}

    def set_location_mode(self, location_id: str, mode: str) -> Dict[str, Any]:
        loc = self.location
        if location_id != loc["location_id"]:
            return {"status": "failed", "output": f"Location {location_id} not found"}
        valid_modes = ["home", "away", "disarmed"]
        if mode not in valid_modes:
            return {"status": "failed", "output": f"Invalid mode '{mode}'. Must be one of: {valid_modes}"}
        loc["mode"] = mode
        loc["updated_at"] = self._now()
        return {"status": "ok", "output": {"type": "mode", "mode": mode, "location_id": location_id}}

    def list_active_dings(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self.active_dings}

    def list_device_events(self, device_id: int, kind: str | None = None, date_from: str | None = None,
                           date_to: str | None = None, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        results = [e for e in self.events if e["doorbot_id"] == device_id]
        if kind:
            results = [e for e in results if e["kind"] == kind]
        if date_from:
            results = [e for e in results if e["created_at"] >= date_from]
        if date_to:
            results = [e for e in results if e["created_at"] <= date_to]
        results = sorted(results, key=lambda x: x["created_at"], reverse=True)
        total = len(results)
        page_results = results[offset: offset + limit]
        return {"status": "ok", "output": {
            "type": "events",
            "count": len(page_results),
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": page_results,
        }}

    def get_event(self, event_id: int) -> Dict[str, Any]:
        for e in self.events:
            if e["id"] == event_id:
                return {"status": "ok", "output": {"type": "event", "event": e}}
        return {"status": "failed", "output": f"Event {event_id} not found"}

    def get_event_recording(self, event_id: int) -> Dict[str, Any]:
        e = None
        for row in self.events:
            if row["id"] == event_id:
                e = row
                break
        if not e:
            return {"status": "failed", "output": f"Event {event_id} not found"}
        if e["recording"]["status"] != "ready":
            return {"status": "failed", "output": f"Recording not available for event {event_id}"}
        location_id = self.location["location_id"]
        url = f"https://ring-recordings.s3.amazonaws.com/{location_id}/{e['device_id']}/{event_id}.mp4"
        return {"status": "ok", "output": {"type": "recording", "event_id": event_id, "recording_url": url}}

    def list_recordings(self, device_id: int, date_from: str | None = None,
                        date_to: str | None = None) -> Dict[str, Any]:
        events = [e for e in self.events
                  if e["doorbot_id"] == device_id and e["recording"]["status"] == "ready"]
        if date_from:
            events = [e for e in events if e["created_at"] >= date_from]
        if date_to:
            events = [e for e in events if e["created_at"] <= date_to]
        events = sorted(events, key=lambda x: x["created_at"], reverse=True)
        location_id = self.location["location_id"]
        recordings = []
        for e in events:
            recordings.append({
                "event_id": e["id"],
                "doorbot_id": e["doorbot_id"],
                "device_id": e["device_id"],
                "kind": e["kind"],
                "created_at": e["created_at"],
                "duration_seconds": e["duration_seconds"],
                "recording_url": f"https://ring-recordings.s3.amazonaws.com/{location_id}/{e['device_id']}/{e['id']}.mp4",
            })
        return {"status": "ok", "output": {"type": "recordings", "count": len(recordings), "results": recordings}}

    def list_shared_users(self, location_id: str) -> Dict[str, Any]:
        if location_id != "loc_martinez_001":
            return {"status": "failed", "output": f"Location {location_id} not found"}
        rows = self.shared_users
        return {"status": "ok", "output": {"type": "shared_users", "count": len(rows), "results": rows}}

    def get_shared_user(self, location_id: str, user_id: int) -> Dict[str, Any]:
        if location_id != "loc_martinez_001":
            return {"status": "failed", "output": f"Location {location_id} not found"}
        for u in self.shared_users:
            if u["user_id"] == user_id:
                return {"status": "ok", "output": {"type": "shared_user", "shared_user": u}}
        return {"status": "failed", "output": f"User {user_id} not found"}

    def get_chime_settings(self, device_id: int) -> Dict[str, Any]:
        device, category = self._find_device(device_id)
        if not device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if category != "chimes":
            return {"status": "failed", "output": f"Device {device_id} is not a chime"}
        return {"status": "ok", "output": {"type": "chime_settings", "settings": device.get("settings", {})}}

    def link_chime_to_doorbell(self, device_id: int, doorbell_id: int) -> Dict[str, Any]:
        doorbell, _ = self._find_device(doorbell_id)
        if not doorbell:
            chime_check, _ = self._find_device(device_id)
            if not chime_check:
                return {"status": "failed", "output": f"Device {device_id} not found"}
            return {"status": "failed", "output": f"Doorbell {doorbell_id} not found"}

        chime_check, chime_cat = self._find_device(device_id)
        if not chime_check:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if chime_cat != "chimes":
            return {"status": "failed", "output": f"Device {device_id} is not a chime"}

        chime = chime_check
        linked = chime.get("settings", {}).get("linked_doorbots", [])
        if doorbell_id not in linked:
            linked.append(doorbell_id)
        chime.setdefault("settings", {})["linked_doorbots"] = linked
        return {"status": "ok", "output": {"type": "chime_settings", "settings": chime.get("settings", {})}}

    def unlink_chime_from_doorbell(self, device_id: int, doorbell_id: int) -> Dict[str, Any]:
        chime_check, chime_cat = self._find_device(device_id)
        if not chime_check:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if chime_cat != "chimes":
            return {"status": "failed", "output": f"Device {device_id} is not a chime"}

        chime = chime_check
        linked = chime.get("settings", {}).get("linked_doorbots", [])
        if doorbell_id in linked:
            linked.remove(doorbell_id)
        chime.setdefault("settings", {})["linked_doorbots"] = linked
        return {"status": "ok", "output": {"type": "chime_settings", "settings": chime.get("settings", {})}}

    def list_motion_zones(self, device_id: int) -> Dict[str, Any]:
        device, _ = self._find_device(device_id)
        if not device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        zones = [z for z in self.motion_zones if z["device_id"] == device_id]
        public = [{k: v for k, v in z.items() if k != "_pk"} for z in zones]
        return {"status": "ok", "output": {"type": "motion_zones", "count": len(public), "results": public}}

    def list_notification_prefs(self) -> Dict[str, Any]:
        rows = self._notification_prefs_rows()
        return {"status": "ok", "output": {"type": "notification_prefs", "count": len(rows), "results": rows}}

    def get_notification_pref(self, device_id: int, channel: str = "push") -> Dict[str, Any]:
        pk = f"{device_id}/{channel}"
        p = self._notif_get(pk)
        if p:
            return {"status": "ok", "output": {"type": "notification_pref",
                    "notification_pref": {k: v for k, v in p.items() if k != "_pk"}}}
        return {"status": "failed", "output": f"Notification preferences for device {device_id} not found"}

    def update_notification_pref(self, device_id: int, motion_alerts: bool | None = None,
                                 ding_alerts: bool | None = None, person_alerts: bool | None = None,
                                 package_alerts: bool | None = None, channel: str = "push") -> Dict[str, Any]:
        pk = f"{device_id}/{channel}"
        p = self._notif_get(pk)
        if not p:
            return {"status": "failed", "output": f"Notification preferences for device {device_id} not found"}
        data = {}
        if motion_alerts is not None:
            data["motion_alerts"] = motion_alerts
        if ding_alerts is not None:
            data["ding_alerts"] = ding_alerts
        if person_alerts is not None:
            data["person_alerts"] = person_alerts
        if package_alerts is not None:
            data["package_alerts"] = package_alerts
        updatable = {"motion_alerts", "ding_alerts", "person_alerts", "package_alerts"}
        for k, v in data.items():
            if k in updatable:
                p[k] = v
        return {"status": "ok", "output": {"type": "notification_pref",
                "notification_pref": {k: v for k, v in p.items() if k != "_pk"}}}

    def activate_siren(self, device_id: int, duration_seconds: int = 30) -> Dict[str, Any]:
        pre_device, _ = self._find_device(device_id)
        if not pre_device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if "siren_status" not in pre_device:
            return {"status": "failed", "output": f"Device {device_id} does not have a siren"}
        pre_device.setdefault("siren_status", {})["seconds_remaining"] = duration_seconds
        return {"status": "ok", "output": {"type": "siren", "device_id": device_id,
                "siren_status": pre_device.get("siren_status", {})}}

    def deactivate_siren(self, device_id: int) -> Dict[str, Any]:
        pre_device, _ = self._find_device(device_id)
        if not pre_device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if "siren_status" not in pre_device:
            return {"status": "failed", "output": f"Device {device_id} does not have a siren"}
        pre_device.setdefault("siren_status", {})["seconds_remaining"] = 0
        return {"status": "ok", "output": {"type": "siren", "device_id": device_id,
                "siren_status": pre_device.get("siren_status", {})}}

    def toggle_floodlight(self, device_id: int, on: bool) -> Dict[str, Any]:
        pre_device, _ = self._find_device(device_id)
        if not pre_device:
            return {"status": "failed", "output": f"Device {device_id} not found"}
        if "floodlight_status" not in pre_device:
            return {"status": "failed", "output": f"Device {device_id} does not have a floodlight"}
        pre_device.setdefault("floodlight_status", {})["on"] = on
        return {"status": "ok", "output": {"type": "floodlight", "device_id": device_id,
                "floodlight_status": pre_device.get("floodlight_status", {})}}


if __name__ == "__main__":
    s = RingSession(seed=12)
    print(s.list_devices())
    print(s.list_active_dings())
