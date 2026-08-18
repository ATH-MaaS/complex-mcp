from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightCloudflareSession
except ImportError:
    from software.LightCloudflare.session import LightCloudflareSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightCloudflare")

session_dict: Dict[str, LightCloudflareSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightCloudflareSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.cloudflare_session.get_session_dict(),
    }


@mcp.tool
async def list_zones(session_id: str, name: str | None = None, status: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.list_zones(name, status)


@mcp.tool
async def get_zone(zone_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.get_zone(zone_id)


@mcp.tool
async def list_dns_records(zone_id: str, session_id: str, type: str | None = None, name: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.list_dns_records(zone_id, type, name)


@mcp.tool
async def get_dns_record(zone_id: str, record_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.get_dns_record(zone_id, record_id)


@mcp.tool
async def create_dns_record(zone_id: str, type: str, name: str, content: str, session_id: str, ttl: int = 1, proxied: bool = False, priority: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.create_dns_record(zone_id, type, name, content, ttl, proxied, priority)


@mcp.tool
async def update_dns_record(zone_id: str, record_id: str, session_id: str, type: str | None = None, name: str | None = None, content: str | None = None, ttl: int | None = None, proxied: bool | None = None, priority: int | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.update_dns_record(zone_id, record_id, type, name, content, ttl, proxied, priority)


@mcp.tool
async def delete_dns_record(zone_id: str, record_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.delete_dns_record(zone_id, record_id)


@mcp.tool
async def list_firewall_rules(zone_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.cloudflare_session.list_firewall_rules(zone_id)
