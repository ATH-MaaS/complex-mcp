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


def _to_int(v, default=0) -> int:
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_str(v):
    s = "" if v is None else str(v)
    return s or None


class TwilioSession:
    """Deterministic sandbox for the Twilio mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "twilio.yaml") as f:
                info = yaml.safe_load(f)

            self.account: Dict[str, Any] = info.get("account", {})
            self.phone_numbers: List[Dict[str, Any]] = [
                {
                    **p,
                    "sms_enabled": _to_bool(p.get("sms_enabled", False)),
                    "voice_enabled": _to_bool(p.get("voice_enabled", False)),
                    "mms_enabled": _to_bool(p.get("mms_enabled", False)),
                    "capabilities_fax": _to_bool(p.get("capabilities_fax", False)),
                }
                for p in info.get("phone_numbers", [])
            ]
            self.messages: List[Dict[str, Any]] = [
                {
                    **m,
                    "num_segments": _to_int(m.get("num_segments"), 0),
                    "price": _to_float(m.get("price")),
                    "error_code": (int(m["error_code"]) if str(m.get("error_code", "")).strip() != "" else None),
                    "date_sent": (_opt_str(m.get("date_sent"))),
                }
                for m in info.get("messages", [])
            ]
            self.calls: List[Dict[str, Any]] = [
                {
                    **c,
                    "duration": _to_int(c.get("duration"), 0),
                    "price": _to_float(c.get("price")),
                    "answered_by": (_opt_str(c.get("answered_by"))),
                    "start_time": (_opt_str(c.get("start_time"))),
                    "end_time": (_opt_str(c.get("end_time"))),
                }
                for c in info.get("calls", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTwilio')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"messages": self.messages, "calls": self.calls}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=32))

    def _new_sid(self, prefix: str) -> str:
        return f"{prefix}{self.uuid()}"

    def _account_sid(self) -> str:
        return self.account["sid"]

    def _serialize_message(self, m):
        return {
            "sid": m["sid"],
            "account_sid": self._account_sid(),
            "from": m["from_number"],
            "to": m["to_number"],
            "body": m["body"],
            "status": m["status"],
            "direction": m["direction"],
            "num_segments": str(m["num_segments"]),
            "price": str(m["price"]) if m["price"] is not None else None,
            "price_unit": m["price_unit"],
            "error_code": m["error_code"],
            "date_sent": m["date_sent"],
            "date_created": m["date_created"],
            "uri": f"/2010-04-01/Accounts/{self._account_sid()}/Messages/{m['sid']}.json",
        }

    def _serialize_call(self, c):
        return {
            "sid": c["sid"],
            "account_sid": self._account_sid(),
            "from": c["from_number"],
            "to": c["to_number"],
            "status": c["status"],
            "direction": c["direction"],
            "duration": str(c["duration"]),
            "price": str(c["price"]) if c["price"] is not None else None,
            "price_unit": c["price_unit"],
            "answered_by": c["answered_by"],
            "start_time": c["start_time"],
            "end_time": c["end_time"],
            "date_created": c["date_created"],
            "uri": f"/2010-04-01/Accounts/{self._account_sid()}/Calls/{c['sid']}.json",
        }

    def _serialize_phone_number(self, p):
        return {
            "sid": p["sid"],
            "account_sid": self._account_sid(),
            "phone_number": p["phone_number"],
            "friendly_name": p["friendly_name"],
            "iso_country": p["iso_country"],
            "capabilities": {
                "sms": p["sms_enabled"],
                "voice": p["voice_enabled"],
                "mms": p["mms_enabled"],
                "fax": p["capabilities_fax"],
            },
            "date_created": p["date_created"],
        }

    # --- Messages ----------------------------------------------------------
    def list_messages(self, to: str | None = None, from_: str | None = None,
                      status: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        results = list(self.messages)
        if to:
            results = [m for m in results if m["to_number"] == to]
        if from_:
            results = [m for m in results if m["from_number"] == from_]
        if status:
            results = [m for m in results if m["status"] == status]
        results.sort(key=lambda m: m["date_created"], reverse=True)
        results = results[:page_size]
        return {"status": "ok", "output": {
            "messages": [self._serialize_message(m) for m in results],
            "page": 0,
            "page_size": page_size,
            "uri": f"/2010-04-01/Accounts/{self._account_sid()}/Messages.json",
        }}

    def get_message(self, sid: str) -> Dict[str, Any]:
        for m in self.messages:
            if m["sid"] == sid:
                return {"status": "ok", "output": self._serialize_message(m)}
        return {"status": "failed", "output": f"Message {sid} not found"}

    def create_message(self, to: str, from_: str, body: str = "") -> Dict[str, Any]:
        if not to or not from_:
            return {"status": "failed", "output": "Both 'To' and 'From' are required"}
        segments = max(1, (len(body) + 159) // 160) if body else 1
        msg = {
            "sid": self._new_sid("SM"),
            "from_number": from_,
            "to_number": to,
            "body": body or "",
            "status": "queued",
            "direction": "outbound-api",
            "num_segments": segments,
            "price": None,
            "price_unit": "USD",
            "error_code": None,
            "date_sent": None,
            "date_created": self._now(),
        }
        self.messages.append(msg)
        return {"status": "ok", "output": self._serialize_message(msg)}

    # --- Calls -------------------------------------------------------------
    def list_calls(self, to: str | None = None, from_: str | None = None,
                   status: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        results = list(self.calls)
        if to:
            results = [c for c in results if c["to_number"] == to]
        if from_:
            results = [c for c in results if c["from_number"] == from_]
        if status:
            results = [c for c in results if c["status"] == status]
        results.sort(key=lambda c: c["date_created"], reverse=True)
        results = results[:page_size]
        return {"status": "ok", "output": {
            "calls": [self._serialize_call(c) for c in results],
            "page": 0,
            "page_size": page_size,
            "uri": f"/2010-04-01/Accounts/{self._account_sid()}/Calls.json",
        }}

    def create_call(self, to: str, from_: str) -> Dict[str, Any]:
        if not to or not from_:
            return {"status": "failed", "output": "Both 'To' and 'From' are required"}
        call = {
            "sid": self._new_sid("CA"),
            "from_number": from_,
            "to_number": to,
            "status": "queued",
            "direction": "outbound-api",
            "duration": 0,
            "price": None,
            "price_unit": "USD",
            "answered_by": None,
            "start_time": None,
            "end_time": None,
            "date_created": self._now(),
        }
        self.calls.append(call)
        return {"status": "ok", "output": self._serialize_call(call)}

    # --- Incoming phone numbers --------------------------------------------
    def list_phone_numbers(self, phone_number: str | None = None, page_size: int = 50) -> Dict[str, Any]:
        results = list(self.phone_numbers)
        if phone_number:
            results = [p for p in results if p["phone_number"] == phone_number]
        results = results[:page_size]
        return {"status": "ok", "output": {
            "incoming_phone_numbers": [self._serialize_phone_number(p) for p in results],
            "page": 0,
            "page_size": page_size,
            "uri": f"/2010-04-01/Accounts/{self._account_sid()}/IncomingPhoneNumbers.json",
        }}

    # --- Lookup ------------------------------------------------------------
    def lookup(self, phone_number: str) -> Dict[str, Any]:
        owned = next((p for p in self.phone_numbers if p["phone_number"] == phone_number), None)
        country = owned["iso_country"] if owned else ("GB" if phone_number.startswith("+44") else "US")
        return {"status": "ok", "output": {
            "phone_number": phone_number,
            "national_format": phone_number,
            "country_code": country,
            "valid": phone_number.startswith("+") and len(phone_number) >= 8,
            "caller_name": owned["friendly_name"] if owned else None,
            "url": f"/v1/PhoneNumbers/{phone_number}",
        }}


if __name__ == "__main__":
    s = TwilioSession(seed=12)
    print(s.list_messages())
    print(s.list_phone_numbers())
