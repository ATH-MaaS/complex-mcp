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
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class SendgridSession:
    """Deterministic sandbox for the SendGrid mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "sendgrid.yaml") as f:
                info = yaml.safe_load(f)

            self.templates: List[Dict[str, Any]] = [
                {**t, "active": _to_bool(t.get("active", False))} for t in info.get("templates", [])
            ]
            self.lists: List[Dict[str, Any]] = [
                {**l, "contact_count": _to_int(l.get("contact_count", 0))} for l in info.get("lists", [])
            ]
            self.contacts: List[Dict[str, Any]] = [
                {**c, "list_ids": [x for x in str(c.get("list_ids", "")).split(";") if x]}
                for c in info.get("contacts", [])
            ]
            self.sent_log: List[Dict[str, Any]] = [
                {**s, "opens": _to_int(s.get("opens", 0)), "clicks": _to_int(s.get("clicks", 0))}
                for s in info.get("sent_log", [])
            ]
            self.stats: List[Dict[str, Any]] = [
                {
                    "date": r["date"],
                    "requests": _to_int(r.get("requests", 0)),
                    "delivered": _to_int(r.get("delivered", 0)),
                    "opens": _to_int(r.get("opens", 0)),
                    "unique_opens": _to_int(r.get("unique_opens", 0)),
                    "clicks": _to_int(r.get("clicks", 0)),
                    "unique_clicks": _to_int(r.get("unique_clicks", 0)),
                    "bounces": _to_int(r.get("bounces", 0)),
                    "spam_reports": _to_int(r.get("spam_reports", 0)),
                    "unsubscribes": _to_int(r.get("unsubscribes", 0)),
                }
                for r in info.get("stats", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSendGrid')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"sent_log": self.sent_log, "contacts": self.contacts}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=12))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _serialize_template(self, t):
        return {
            "id": t["id"],
            "name": t["name"],
            "generation": t["generation"],
            "updated_at": t["updated_at"],
            "versions": [{
                "subject": t["subject"],
                "html_content": t["html_content"],
                "active": 1 if t["active"] else 0,
            }],
        }

    def _serialize_contact(self, c):
        return {
            "id": c["id"],
            "email": c["email"],
            "first_name": c["first_name"],
            "last_name": c["last_name"],
            "country": c["country"],
            "list_ids": c["list_ids"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
        }

    # --- Mail send ---------------------------------------------------------
    def send_mail(self, personalizations: List[Dict[str, Any]], from_email: str | None = None,
                  subject: str | None = None, content: List[Dict[str, Any]] | None = None,
                  template_id: str | None = None) -> Dict[str, Any]:
        if not personalizations:
            return {"status": "failed", "output": "personalizations is required"}
        if not from_email:
            return {"status": "failed", "output": "from.email is required"}
        if template_id and not any(t["id"] == template_id for t in self.templates):
            return {"status": "failed", "output": f"template {template_id} not found"}

        created = []
        eff_subject = subject
        if template_id:
            tmpl = next((t for t in self.templates if t["id"] == template_id), None)
            if tmpl and not eff_subject:
                eff_subject = tmpl["subject"]
        for p in personalizations:
            for to in p.get("to", []):
                entry = {
                    "message_id": self._new_id("msg"),
                    "to_email": to.get("email"),
                    "from_email": from_email,
                    "subject": eff_subject or p.get("subject") or "",
                    "template_id": template_id or "",
                    "status": "queued",
                    "opens": 0,
                    "clicks": 0,
                    "sent_at": self._now(),
                }
                self.sent_log.append(entry)
                created.append(entry["message_id"])
        return {"status": "ok", "output": {"accepted": len(created), "message_ids": created, "status": "queued"}}

    # --- Templates ---------------------------------------------------------
    def list_templates(self, generation: str | None = None) -> Dict[str, Any]:
        results = list(self.templates)
        if generation:
            results = [t for t in results if t["generation"] == generation]
        return {"status": "ok", "output": {"result": [self._serialize_template(t) for t in results]}}

    def get_template(self, template_id: str) -> Dict[str, Any]:
        for t in self.templates:
            if t["id"] == template_id:
                return {"status": "ok", "output": self._serialize_template(t)}
        return {"status": "failed", "output": f"Template {template_id} not found"}

    def create_template(self, name: str, generation: str = "dynamic", subject: str = "",
                        html_content: str = "") -> Dict[str, Any]:
        tmpl = {
            "id": self._new_id("d"),
            "name": name,
            "generation": generation,
            "subject": subject,
            "html_content": html_content,
            "active": True,
            "updated_at": self._now(),
        }
        self.templates.append(tmpl)
        return {"status": "ok", "output": self._serialize_template(tmpl)}

    # --- Marketing contacts ------------------------------------------------
    def list_contacts(self, email: str | None = None) -> Dict[str, Any]:
        results = list(self.contacts)
        if email:
            results = [c for c in results if c["email"] == email]
        return {"status": "ok", "output": {
            "result": [self._serialize_contact(c) for c in results],
            "contact_count": len(self.contacts),
        }}

    def upsert_contacts(self, contacts: List[Dict[str, Any]], list_ids: List[str] | None = None) -> Dict[str, Any]:
        list_ids = list_ids or []
        upserted = []
        for c in contacts:
            email = c.get("email")
            if not email:
                continue
            existing = next((x for x in self.contacts if x["email"] == email), None)
            if existing:
                existing["first_name"] = c.get("first_name", existing["first_name"])
                existing["last_name"] = c.get("last_name", existing["last_name"])
                existing["country"] = c.get("country", existing["country"])
                for lid in list_ids:
                    if lid not in existing["list_ids"]:
                        existing["list_ids"].append(lid)
                existing["updated_at"] = self._now()
                upserted.append(existing["id"])
            else:
                new_c = {
                    "id": self._new_id("contact"),
                    "email": email,
                    "first_name": c.get("first_name", ""),
                    "last_name": c.get("last_name", ""),
                    "country": c.get("country", ""),
                    "list_ids": list(list_ids),
                    "created_at": self._now(),
                    "updated_at": self._now(),
                }
                self.contacts.append(new_c)
                upserted.append(new_c["id"])
        return {"status": "ok", "output": {
            "job_id": self._new_id("job"), "upserted": len(upserted), "contact_ids": upserted,
        }}

    # --- Lists -------------------------------------------------------------
    def list_lists(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {"result": list(self.lists)}}

    # --- Stats -------------------------------------------------------------
    def get_stats(self, start_date: str | None = None, end_date: str | None = None) -> Dict[str, Any]:
        rows = list(self.stats)
        if start_date:
            rows = [r for r in rows if r["date"] >= start_date]
        if end_date:
            rows = [r for r in rows if r["date"] <= end_date]
        out = []
        for r in rows:
            out.append({
                "date": r["date"],
                "stats": [{
                    "metrics": {k: v for k, v in r.items() if k != "date"},
                }],
            })
        return {"status": "ok", "output": out}


if __name__ == "__main__":
    s = SendgridSession(seed=12)
    print(s.list_templates())
    print(s.list_contacts())
