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


def _to_int(v) -> int:
    return int(str(v).strip())


class CloudflareSession:
    """Deterministic sandbox for the Cloudflare mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "cloudflare.yaml") as f:
                info = yaml.safe_load(f)

            self.zones: List[Dict[str, Any]] = [
                {
                    **z,
                    "paused": _to_bool(z.get("paused", False)),
                    "development_mode": _to_int(z.get("development_mode", 0)),
                }
                for z in info.get("zones", [])
            ]
            self.dns: List[Dict[str, Any]] = [
                {
                    **r,
                    "ttl": _to_int(r.get("ttl", 1)),
                    "proxied": _to_bool(r.get("proxied", False)),
                    "priority": _to_int(r.get("priority", 0)),
                }
                for r in info.get("dns", [])
            ]
            self.firewall: List[Dict[str, Any]] = [
                {
                    **r,
                    "paused": _to_bool(r.get("paused", False)),
                    "priority": _to_int(r.get("priority", 0)),
                }
                for r in info.get("firewall", [])
            ]
            self.page_rules: List[Dict[str, Any]] = [
                {**r, "priority": _to_int(r.get("priority", 0))} for r in info.get("page_rules", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightCloudflare')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"dns": self.dns}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=40))

    def _zone_exists(self, zone_id) -> bool:
        return any(z["id"] == zone_id for z in self.zones)

    def _serialize_zone(self, z):
        return {
            "id": z["id"],
            "name": z["name"],
            "status": z["status"],
            "paused": z["paused"],
            "type": z["type"],
            "development_mode": z["development_mode"],
            "plan": {"name": z["plan"]},
            "created_on": z["created_on"],
            "modified_on": z["modified_on"],
        }

    def _serialize_dns(self, r):
        return {
            "id": r["id"],
            "zone_id": r["zone_id"],
            "type": r["type"],
            "name": r["name"],
            "content": r["content"],
            "ttl": r["ttl"],
            "proxied": r["proxied"],
            "priority": r["priority"],
            "created_on": r["created_on"],
            "modified_on": r["modified_on"],
        }

    def _serialize_firewall(self, r):
        return {
            "id": r["id"],
            "description": r["description"],
            "action": r["action"],
            "filter": {"expression": r["expression"]},
            "paused": r["paused"],
            "priority": r["priority"],
            "created_on": r["created_on"],
        }

    # --- Zones -------------------------------------------------------------
    def list_zones(self, name: str | None = None, status: str | None = None) -> Dict[str, Any]:
        results = list(self.zones)
        if name:
            results = [z for z in results if z["name"] == name]
        if status:
            results = [z for z in results if z["status"] == status]
        return {"status": "ok", "output": [self._serialize_zone(z) for z in results]}

    def get_zone(self, zone_id: str) -> Dict[str, Any]:
        for z in self.zones:
            if z["id"] == zone_id:
                return {"status": "ok", "output": self._serialize_zone(z)}
        return {"status": "failed", "output": f"Zone {zone_id} not found"}

    # --- DNS records -------------------------------------------------------
    def list_dns_records(self, zone_id: str, type: str | None = None, name: str | None = None) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        results = [r for r in self.dns if r["zone_id"] == zone_id]
        if type:
            results = [r for r in results if r["type"] == type]
        if name:
            results = [r for r in results if r["name"] == name]
        return {"status": "ok", "output": [self._serialize_dns(r) for r in results]}

    def get_dns_record(self, zone_id: str, record_id: str) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        for r in self.dns:
            if r["zone_id"] == zone_id and r["id"] == record_id:
                return {"status": "ok", "output": self._serialize_dns(r)}
        return {"status": "failed", "output": f"DNS record {record_id} not found"}

    def create_dns_record(self, zone_id: str, type: str, name: str, content: str,
                          ttl: int = 1, proxied: bool = False, priority: int = 0) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        now = self._now()
        record = {
            "id": self.uuid(),
            "zone_id": zone_id,
            "type": type,
            "name": name,
            "content": content,
            "ttl": ttl,
            "proxied": proxied,
            "priority": priority,
            "created_on": now,
            "modified_on": now,
        }
        self.dns.append(record)
        return {"status": "ok", "output": self._serialize_dns(record)}

    def update_dns_record(self, zone_id: str, record_id: str, type: str | None = None,
                          name: str | None = None, content: str | None = None,
                          ttl: int | None = None, proxied: bool | None = None,
                          priority: int | None = None) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        for idx, r in enumerate(self.dns):
            if r["zone_id"] == zone_id and r["id"] == record_id:
                if type is not None:
                    self.dns[idx]["type"] = type
                if name is not None:
                    self.dns[idx]["name"] = name
                if content is not None:
                    self.dns[idx]["content"] = content
                if ttl is not None:
                    self.dns[idx]["ttl"] = ttl
                if proxied is not None:
                    self.dns[idx]["proxied"] = proxied
                if priority is not None:
                    self.dns[idx]["priority"] = priority
                self.dns[idx]["modified_on"] = self._now()
                return {"status": "ok", "output": self._serialize_dns(self.dns[idx])}
        return {"status": "failed", "output": f"DNS record {record_id} not found"}

    def delete_dns_record(self, zone_id: str, record_id: str) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        for idx, r in enumerate(self.dns):
            if r["zone_id"] == zone_id and r["id"] == record_id:
                self.dns.pop(idx)
                return {"status": "ok", "output": {"id": record_id}}
        return {"status": "failed", "output": f"DNS record {record_id} not found"}

    # --- Firewall rules ----------------------------------------------------
    def list_firewall_rules(self, zone_id: str) -> Dict[str, Any]:
        if not self._zone_exists(zone_id):
            return {"status": "failed", "output": f"Zone {zone_id} not found"}
        results = [r for r in self.firewall if r["zone_id"] == zone_id]
        results.sort(key=lambda r: r["priority"])
        return {"status": "ok", "output": [self._serialize_firewall(r) for r in results]}


if __name__ == "__main__":
    s = CloudflareSession(seed=12)
    print(s.list_zones())
    print(s.list_firewall_rules("zone1aaaa1111bbbb2222cccc3333dddd"))
