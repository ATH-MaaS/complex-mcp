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


class DocusignSession:
    """Deterministic sandbox for the DocuSign mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "docusign.yaml") as f:
                info = yaml.safe_load(f)

            self.documents: List[Dict[str, Any]] = [
                {
                    **d,
                    "page_count": int(d.get("page_count")),
                    "order": int(d.get("order")),
                }
                for d in info.get("documents", [])
            ]
            self.envelopes: List[Dict[str, Any]] = [
                {
                    **e,
                    "sent_time": (e.get("sent_time") or None),
                    "completed_time": (e.get("completed_time") or None),
                    "template_id": (e.get("template_id") or None),
                }
                for e in info.get("envelopes", [])
            ]
            self.recipients: List[Dict[str, Any]] = [
                {
                    **r,
                    "routing_order": int(r.get("routing_order")),
                    "signed_time": (r.get("signed_time") or None),
                }
                for r in info.get("recipients", [])
            ]
            self.templates: List[Dict[str, Any]] = [
                {**t, "shared": _to_bool(t.get("shared", False))} for t in info.get("templates", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightDocuSign')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"envelopes": self.envelopes}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        def blk(n):
            return ''.join(self.rng.choices(alphabet, k=n))
        return f"{blk(8)}-{blk(4)}-{blk(4)}-{blk(4)}-{blk(12)}"

    def _envelope_obj(self, e):
        return {
            "envelopeId": e["envelope_id"],
            "status": e["status"],
            "emailSubject": e["email_subject"],
            "sender": {"userName": e["sender_name"], "email": e["sender_email"]},
            "createdDateTime": e["created_time"],
            "sentDateTime": e["sent_time"],
            "completedDateTime": e["completed_time"],
            "templateId": e["template_id"],
        }

    def _recipient_obj(self, r):
        return {
            "recipientId": r["recipient_id"],
            "name": r["name"],
            "email": r["email"],
            "recipientType": r["recipient_type"],
            "status": r["status"],
            "routingOrder": r["routing_order"],
            "signedDateTime": r["signed_time"],
        }

    def _document_obj(self, d):
        return {
            "documentId": d["document_id"],
            "name": d["name"],
            "type": d["document_type"],
            "pages": d["page_count"],
            "order": d["order"],
        }

    def _template_obj(self, t):
        return {
            "templateId": t["template_id"],
            "name": t["name"],
            "description": t["description"],
            "shared": "true" if t["shared"] else "false",
            "owner": {"userName": t["owner_name"]},
            "created": t["created_time"],
        }

    def _find_envelope(self, envelope_id):
        return next((e for e in self.envelopes if e["envelope_id"] == envelope_id), None)

    # --- API methods -------------------------------------------------------
    def list_envelopes(self, status: str | None = None) -> Dict[str, Any]:
        envs = self.envelopes
        if status:
            envs = [e for e in envs if e["status"].lower() == status.lower()]
        return {"status": "ok", "output": {
            "resultSetSize": str(len(envs)),
            "totalSetSize": str(len(envs)),
            "envelopes": [self._envelope_obj(e) for e in envs],
        }}

    def get_envelope(self, envelope_id: str) -> Dict[str, Any]:
        e = self._find_envelope(envelope_id)
        if e is None:
            return {"status": "failed", "output": f"envelope {envelope_id} not found"}
        return {"status": "ok", "output": self._envelope_obj(e)}

    def create_envelope(self, email_subject: str = "", status: str = "created",
                        template_id: str | None = None, sender_name: str | None = None,
                        sender_email: str | None = None, recipients: Dict[str, Any] | None = None,
                        documents: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        status = (status or "created").lower()
        now = self._now()
        envelope_id = self.uuid()
        env = {
            "envelope_id": envelope_id,
            "status": status,
            "email_subject": email_subject or "",
            "sender_name": sender_name or "Amelia Ortega",
            "sender_email": sender_email or "amelia.ortega@orbit-labs.com",
            "created_time": now,
            "sent_time": now if status == "sent" else None,
            "completed_time": None,
            "template_id": template_id or None,
        }
        self.envelopes.append(env)

        for i, r in enumerate((recipients or {}).get("signers", []), start=1):
            self.recipients.append({
                "recipient_id": r.get("recipientId") or str(i),
                "envelope_id": envelope_id,
                "name": r.get("name", ""),
                "email": r.get("email", ""),
                "recipient_type": "signer",
                "status": "sent" if status == "sent" else "created",
                "routing_order": int(r.get("routingOrder", i)),
                "signed_time": None,
            })

        for i, d in enumerate((documents or []), start=1):
            self.documents.append({
                "document_id": d.get("documentId") or str(i),
                "envelope_id": envelope_id,
                "name": d.get("name", f"document-{i}.pdf"),
                "document_type": "content",
                "page_count": int(d.get("pages", 1)),
                "order": i,
            })
        return {"status": "ok", "output": {
            "envelopeId": envelope_id, "status": status,
            "statusDateTime": now, "uri": f"/envelopes/{envelope_id}",
        }}

    def update_envelope(self, envelope_id: str, status: str) -> Dict[str, Any]:
        e = self._find_envelope(envelope_id)
        if e is None:
            return {"status": "failed", "output": f"envelope {envelope_id} not found"}
        status = status.lower()
        e["status"] = status
        now = self._now()
        if status == "sent" and not e["sent_time"]:
            e["sent_time"] = now
        if status == "completed":
            e["completed_time"] = now
        return {"status": "ok", "output": {
            "envelopeId": envelope_id, "status": status, "statusDateTime": now,
        }}

    def list_recipients(self, envelope_id: str) -> Dict[str, Any]:
        if self._find_envelope(envelope_id) is None:
            return {"status": "failed", "output": f"envelope {envelope_id} not found"}
        signers = [r for r in self.recipients if r["envelope_id"] == envelope_id]
        signers = sorted(signers, key=lambda r: r["routing_order"])
        return {"status": "ok", "output": {
            "signers": [self._recipient_obj(r) for r in signers],
            "recipientCount": str(len(signers)),
        }}

    def list_documents(self, envelope_id: str) -> Dict[str, Any]:
        if self._find_envelope(envelope_id) is None:
            return {"status": "failed", "output": f"envelope {envelope_id} not found"}
        docs = [d for d in self.documents if d["envelope_id"] == envelope_id]
        docs = sorted(docs, key=lambda d: d["order"])
        return {"status": "ok", "output": {
            "envelopeId": envelope_id,
            "envelopeDocuments": [self._document_obj(d) for d in docs],
        }}

    def list_templates(self) -> Dict[str, Any]:
        return {"status": "ok", "output": {
            "resultSetSize": str(len(self.templates)),
            "envelopeTemplates": [self._template_obj(t) for t in self.templates],
        }}


if __name__ == "__main__":
    s = DocusignSession(seed=12)
    print(s.list_envelopes())
    print(s.list_templates())
