from typing import Dict, List, Optional
from pathlib import Path
import random
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


DOC_STATUSES = ("draft", "sent", "partially_signed", "completed", "cancelled", "expired")
REQ_STATUSES = ("pending", "signed", "declined", "expired")

SEED_DOCUMENTS = [
    ("NDA - Acme Corp",        "nda_acme.pdf",          "alice@corp.com",  "sent",              3, -10),
    ("Contractor Agreement",   "contractor_bob.pdf",    "alice@corp.com",  "partially_signed", 12, -20),
    ("Employment Offer",       "offer_carol.pdf",       "alice@corp.com",  "completed",         5, -30),
    ("Vendor MSA",             "vendor_msa.pdf",        "alice@corp.com",  "draft",            22, -2),
]

SEED_REQUESTS = [
    (0, "bob@vendor.com",      "pending",   -10, None),
    (1, "bob@corp.com",        "signed",    -20, -18),
    (1, "carol@corp.com",      "pending",   -20, None),
    (2, "carol@newhire.com",   "signed",    -30, -28),
    (2, "dan@corp.com",        "signed",    -30, -27),
]

SEED_SIGNATURES = [
    (1, 1, 120, 400, "hash_bob_1"),
    (3, 3, 100, 380, "hash_carol_3"),
    (4, 4,  80, 350, "hash_dan_4"),
]

SEED_AUDIT = [
    (0, "alice@corp.com", "uploaded",       -10, "uploaded document"),
    (0, "alice@corp.com", "sent",           -10, "sent to bob@vendor.com"),
    (1, "alice@corp.com", "uploaded",       -20, "uploaded document"),
    (1, "bob@corp.com",   "signed",         -18, "signed page 1"),
    (2, "alice@corp.com", "uploaded",       -30, "uploaded document"),
    (2, "alice@corp.com", "completed",      -27, "all signers completed"),
]


@dataclass
class Document:
    docid: str
    title: str
    filename: str
    uploaded_by: str
    uploaded_at: str
    page_count: int
    status: str


@dataclass
class SignatureRequest:
    srid: str
    document_id: str
    signer: str
    sent_at: str
    signed_at: str
    status: str


@dataclass
class Signature:
    sigid: str
    request_id: str
    page: int
    x: int
    y: int
    image_hash: str
    signed_at: str


@dataclass
class AuditEvent:
    aeid: str
    document_id: str
    actor: str
    action: str
    timestamp: str
    details: str = ""


class SignSession:
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
            self.documents: Dict[str, Document] = {}
            self.requests: Dict[str, SignatureRequest] = {}
            self.signatures: Dict[str, Signature] = {}
            self.audit_events: Dict[str, AuditEvent] = {}
            self._doc_order: List[str] = []
            self._req_order: List[str] = []
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightSign')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _shift(self, days: int = 0) -> str:
        return (self._today + timedelta(days=days)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        for title, filename, uploader, status, pages, upload_offset in SEED_DOCUMENTS:
            d = Document(
                docid="doc_" + self.uuid()[:10],
                title=title,
                filename=filename,
                uploaded_by=uploader,
                uploaded_at=self._shift(days=upload_offset),
                page_count=pages,
                status=status,
            )
            self.documents[d.docid] = d
            self._doc_order.append(d.docid)
        for doc_idx, signer, status, sent_offset, signed_offset in SEED_REQUESTS:
            docid = self._doc_order[doc_idx]
            r = SignatureRequest(
                srid="sr_" + self.uuid()[:10],
                document_id=docid,
                signer=signer,
                sent_at=self._shift(days=sent_offset),
                signed_at=self._shift(days=signed_offset) if signed_offset is not None else "",
                status=status,
            )
            self.requests[r.srid] = r
            self._req_order.append(r.srid)
        for req_idx, page, x, y, image_hash in SEED_SIGNATURES:
            srid = self._req_order[req_idx]
            req = self.requests[srid]
            s = Signature(
                sigid="sig_" + self.uuid()[:10],
                request_id=srid,
                page=page,
                x=x,
                y=y,
                image_hash=image_hash,
                signed_at=req.signed_at or self._now(),
            )
            self.signatures[s.sigid] = s
        for doc_idx, actor, action, ts_offset, details in SEED_AUDIT:
            docid = self._doc_order[doc_idx]
            a = AuditEvent(
                aeid="ae_" + self.uuid()[:10],
                document_id=docid,
                actor=actor,
                action=action,
                timestamp=self._shift(days=ts_offset),
                details=details,
            )
            self.audit_events[a.aeid] = a

    def get_session_dict(self) -> Dict:
        return {
            "documents":     {d: asdict(v) for d, v in self.documents.items()},
            "requests":      {r: asdict(v) for r, v in self.requests.items()},
            "signatures":    {s: asdict(v) for s, v in self.signatures.items()},
            "audit_events":  {a: asdict(v) for a, v in self.audit_events.items()},
        }

    def _doc_summary(self, d: Document) -> Dict:
        return {
            "docid": d.docid,
            "title": d.title,
            "filename": d.filename,
            "page_count": d.page_count,
            "status": d.status,
            "uploaded_by": d.uploaded_by,
            "uploaded_at": d.uploaded_at,
        }

    def _req_summary(self, r: SignatureRequest) -> Dict:
        return {
            "srid": r.srid,
            "document_id": r.document_id,
            "signer": r.signer,
            "status": r.status,
            "sent_at": r.sent_at,
            "signed_at": r.signed_at,
        }

    def _add_audit(self, docid: str, actor: str, action: str, details: str = "") -> AuditEvent:
        a = AuditEvent(
            aeid="ae_" + self.uuid()[:10],
            document_id=docid,
            actor=actor,
            action=action,
            timestamp=self._now(),
            details=details,
        )
        self.audit_events[a.aeid] = a
        return a

    def _refresh_doc_status(self, docid: str) -> None:
        d = self.documents.get(docid)
        if not d or d.status in ("cancelled", "expired", "draft"):
            return
        reqs = [r for r in self.requests.values() if r.document_id == docid]
        if not reqs:
            return
        if all(r.status == "signed" for r in reqs):
            d.status = "completed"
        elif any(r.status == "signed" for r in reqs):
            d.status = "partially_signed"

    def list_documents(self, status: Optional[str] = None) -> Dict:
        items = list(self.documents.values())
        if status:
            items = [d for d in items if d.status == status]
        items.sort(key=lambda d: d.uploaded_at, reverse=True)
        return {"status": "ok", "output": [self._doc_summary(d) for d in items]}

    def get_document(self, docid: str) -> Dict:
        d = self.documents.get(docid)
        if not d:
            return {"status": "failed", "output": f"document {docid} not found"}
        return {"status": "ok", "output": asdict(d)}

    def upload_document(self, title: str, filename: str, page_count: int = 1,
                        uploaded_by: str = "self") -> Dict:
        d = Document(
            docid="doc_" + self.uuid()[:10],
            title=title,
            filename=filename,
            uploaded_by=uploaded_by,
            uploaded_at=self._now(),
            page_count=max(1, int(page_count)),
            status="draft",
        )
        self.documents[d.docid] = d
        self._add_audit(d.docid, uploaded_by, "uploaded", f"uploaded {filename}")
        return {"status": "ok", "output": self._doc_summary(d)}

    def delete_document(self, docid: str) -> Dict:
        d = self.documents.pop(docid, None)
        if not d:
            return {"status": "failed", "output": f"document {docid} not found"}
        removed_reqs = [sr for sr, r in self.requests.items() if r.document_id == docid]
        for sr in removed_reqs:
            del self.requests[sr]
        removed_sigs = [sg for sg, s in self.signatures.items() if s.request_id in removed_reqs]
        for sg in removed_sigs:
            del self.signatures[sg]
        return {"status": "ok", "output": {"docid": docid, "deleted": True,
                                            "removed_requests": len(removed_reqs),
                                            "removed_signatures": len(removed_sigs)}}

    def send_for_signature(self, docid: str, signers: List[str]) -> Dict:
        d = self.documents.get(docid)
        if not d:
            return {"status": "failed", "output": f"document {docid} not found"}
        if d.status not in ("draft", "sent"):
            return {"status": "failed", "output": f"document status {d.status} not sendable"}
        if not signers:
            return {"status": "failed", "output": "signers must be a non-empty list"}
        created = []
        for signer in signers:
            r = SignatureRequest(
                srid="sr_" + self.uuid()[:10],
                document_id=docid,
                signer=signer,
                sent_at=self._now(),
                signed_at="",
                status="pending",
            )
            self.requests[r.srid] = r
            created.append(self._req_summary(r))
        d.status = "sent"
        self._add_audit(docid, "self", "sent", f"sent to {', '.join(signers)}")
        return {"status": "ok", "output": {"docid": docid, "requests": created}}

    def cancel_document(self, docid: str) -> Dict:
        d = self.documents.get(docid)
        if not d:
            return {"status": "failed", "output": f"document {docid} not found"}
        d.status = "cancelled"
        for r in self.requests.values():
            if r.document_id == docid and r.status == "pending":
                r.status = "expired"
        self._add_audit(docid, "self", "cancelled", "document cancelled")
        return {"status": "ok", "output": self._doc_summary(d)}

    def list_signature_requests(self, document_id: Optional[str] = None,
                                status: Optional[str] = None) -> Dict:
        items = list(self.requests.values())
        if document_id:
            items = [r for r in items if r.document_id == document_id]
        if status:
            items = [r for r in items if r.status == status]
        items.sort(key=lambda r: r.sent_at)
        return {"status": "ok", "output": [self._req_summary(r) for r in items]}

    def get_signature_request(self, srid: str) -> Dict:
        r = self.requests.get(srid)
        if not r:
            return {"status": "failed", "output": f"request {srid} not found"}
        return {"status": "ok", "output": asdict(r)}

    def sign_document(self, request_id: str, page: int, x: int, y: int,
                      image_hash: str) -> Dict:
        r = self.requests.get(request_id)
        if not r:
            return {"status": "failed", "output": f"request {request_id} not found"}
        if r.status != "pending":
            return {"status": "failed", "output": f"request status is {r.status}"}
        r.status = "signed"
        r.signed_at = self._now()
        s = Signature(
            sigid="sig_" + self.uuid()[:10],
            request_id=request_id,
            page=int(page),
            x=int(x),
            y=int(y),
            image_hash=image_hash,
            signed_at=r.signed_at,
        )
        self.signatures[s.sigid] = s
        self._add_audit(r.document_id, r.signer, "signed",
                        f"signed page {page} at ({x},{y})")
        self._refresh_doc_status(r.document_id)
        return {"status": "ok", "output": asdict(s)}

    def decline_signature(self, request_id: str) -> Dict:
        r = self.requests.get(request_id)
        if not r:
            return {"status": "failed", "output": f"request {request_id} not found"}
        if r.status != "pending":
            return {"status": "failed", "output": f"request status is {r.status}"}
        r.status = "declined"
        r.signed_at = self._now()
        self._add_audit(r.document_id, r.signer, "declined", "signer declined")
        return {"status": "ok", "output": self._req_summary(r)}

    def list_signatures(self, document_id: Optional[str] = None) -> Dict:
        items = list(self.signatures.values())
        if document_id:
            allowed = {sr for sr, r in self.requests.items() if r.document_id == document_id}
            items = [s for s in items if s.request_id in allowed]
        items.sort(key=lambda s: s.signed_at)
        return {"status": "ok", "output": [asdict(s) for s in items]}

    def list_audit(self, document_id: Optional[str] = None) -> Dict:
        items = list(self.audit_events.values())
        if document_id:
            items = [a for a in items if a.document_id == document_id]
        items.sort(key=lambda a: a.timestamp)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def record_audit(self, document_id: str, actor: str, action: str, details: str = "") -> Dict:
        if document_id not in self.documents:
            return {"status": "failed", "output": f"document {document_id} not found"}
        a = self._add_audit(document_id, actor, action, details)
        return {"status": "ok", "output": asdict(a)}

    def list_pending_signatures(self, signer: str) -> Dict:
        items = [r for r in self.requests.values() if r.signer == signer and r.status == "pending"]
        items.sort(key=lambda r: r.sent_at)
        return {"status": "ok", "output": [self._req_summary(r) for r in items]}

    def search_documents(self, query: str) -> Dict:
        q = query.lower()
        items = [
            d for d in self.documents.values()
            if q in d.title.lower() or q in d.filename.lower() or q in d.uploaded_by.lower()
        ]
        items.sort(key=lambda d: d.uploaded_at, reverse=True)
        return {"status": "ok", "output": [self._doc_summary(d) for d in items]}

    def list_completed(self) -> Dict:
        items = [d for d in self.documents.values() if d.status == "completed"]
        items.sort(key=lambda d: d.uploaded_at, reverse=True)
        return {"status": "ok", "output": [self._doc_summary(d) for d in items]}

    def get_stats(self) -> Dict:
        by_doc_status: Dict[str, int] = {s: 0 for s in DOC_STATUSES}
        by_req_status: Dict[str, int] = {s: 0 for s in REQ_STATUSES}
        for d in self.documents.values():
            by_doc_status[d.status] = by_doc_status.get(d.status, 0) + 1
        for r in self.requests.values():
            by_req_status[r.status] = by_req_status.get(r.status, 0) + 1
        return {
            "status": "ok",
            "output": {
                "total_documents": len(self.documents),
                "total_requests": len(self.requests),
                "total_signatures": len(self.signatures),
                "total_audit_events": len(self.audit_events),
                "by_document_status": by_doc_status,
                "by_request_status": by_req_status,
            },
        }
