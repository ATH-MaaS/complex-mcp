from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightRingSession
except ImportError:
    from software.LightRing.session import LightRingSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightRing")

session_dict: Dict[str, LightRingSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightRingSession(os_cfg=os_cfg, seed=seed)
	session_dict[session.session_id] = session
	logger.info(f"A new user logged in! [{session.session_id}]")
	return {
		"status": "ok",
		"session_id": session.session_id,
		"session_info": {
			"status": "ok",
			"output": {}
        }
    }


@mcp.tool
async def logout(session_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	del session_dict[session_id]
	logger.info(f"A user logged out! [{session_id}]")
	return {
        "status": "ok",
        "output": session.ring_session.get_session_dict(),
    }


@mcp.tool
async def list_devices(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_devices()


@mcp.tool
async def get_device(device_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_device(device_id)


@mcp.tool
async def get_device_health(device_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_device_health(device_id)


@mcp.tool
async def update_device_settings(device_id: int, session_id: str, motion_sensitivity: int | None = None, motion_detection_enabled: bool | None = None, people_detection_enabled: bool | None = None, package_detection_enabled: bool | None = None, led_status: str | None = None, light_schedule_enabled: bool | None = None, light_on_duration_seconds: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.update_device_settings(device_id, motion_sensitivity, motion_detection_enabled, people_detection_enabled, package_detection_enabled, led_status, light_schedule_enabled, light_on_duration_seconds)


@mcp.tool
async def get_location(location_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_location(location_id)


@mcp.tool
async def list_location_devices(location_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_location_devices(location_id)


@mcp.tool
async def get_location_mode(location_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_location_mode(location_id)


@mcp.tool
async def set_location_mode(location_id: str, mode: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.set_location_mode(location_id, mode)


@mcp.tool
async def list_active_dings(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_active_dings()


@mcp.tool
async def list_device_events(device_id: int, session_id: str, kind: str | None = None, date_from: str | None = None, date_to: str | None = None, limit: int = 20, offset: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_device_events(device_id, kind, date_from, date_to, limit, offset)


@mcp.tool
async def get_event(event_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_event(event_id)


@mcp.tool
async def get_event_recording(event_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_event_recording(event_id)


@mcp.tool
async def list_recordings(device_id: int, session_id: str, date_from: str | None = None, date_to: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_recordings(device_id, date_from, date_to)


@mcp.tool
async def list_shared_users(location_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_shared_users(location_id)


@mcp.tool
async def get_shared_user(location_id: str, user_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_shared_user(location_id, user_id)


@mcp.tool
async def get_chime_settings(device_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_chime_settings(device_id)


@mcp.tool
async def link_chime_to_doorbell(device_id: int, doorbell_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.link_chime_to_doorbell(device_id, doorbell_id)


@mcp.tool
async def unlink_chime_from_doorbell(device_id: int, doorbell_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.unlink_chime_from_doorbell(device_id, doorbell_id)


@mcp.tool
async def list_motion_zones(device_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_motion_zones(device_id)


@mcp.tool
async def list_notification_prefs(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.list_notification_prefs()


@mcp.tool
async def get_notification_pref(device_id: int, session_id: str, channel: str = "push"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.get_notification_pref(device_id, channel)


@mcp.tool
async def update_notification_pref(device_id: int, session_id: str, motion_alerts: bool | None = None, ding_alerts: bool | None = None, person_alerts: bool | None = None, package_alerts: bool | None = None, channel: str = "push"):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.update_notification_pref(device_id, motion_alerts, ding_alerts, person_alerts, package_alerts, channel)


@mcp.tool
async def activate_siren(device_id: int, session_id: str, duration_seconds: int = 30):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.activate_siren(device_id, duration_seconds)


@mcp.tool
async def deactivate_siren(device_id: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.deactivate_siren(device_id)


@mcp.tool
async def toggle_floodlight(device_id: int, on: bool, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.ring_session.toggle_floodlight(device_id, on)
