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


def _choices(raw) -> List[str]:
    return [c.strip() for c in (raw or "").split("|") if c.strip()]


class TypeformSession:
    """Deterministic sandbox for the Typeform API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "typeform.yaml") as f:
                info = yaml.safe_load(f)

            self.forms: List[Dict[str, Any]] = [
                {
                    **r,
                    "is_public": _to_bool(r["is_public"]),
                    "response_count": _to_int(r["response_count"]),
                }
                for r in info.get("forms", [])
            ]
            self.fields: List[Dict[str, Any]] = [
                {
                    **r,
                    "required": _to_bool(r["required"]),
                    "choices": _choices(r["choices"]),
                    "order": _to_int(r["order"]),
                }
                for r in info.get("fields", [])
            ]
            self.responses: List[Dict[str, Any]] = [
                {**r, "completed": _to_bool(r["completed"])} for r in info.get("responses", [])
            ]
            self.answers: List[Dict[str, Any]] = [dict(r) for r in info.get("answers", [])]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightTypeform')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"forms": self.forms, "responses": self.responses}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=10))

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.uuid()}"

    def _field_obj(self, f):
        obj = {
            "id": f["field_id"],
            "title": f["title"],
            "ref": f["ref"],
            "type": f["field_type"],
            "required": f["required"],
        }
        if f["field_type"] == "multiple_choice":
            obj["properties"] = {"choices": [{"label": c} for c in f["choices"]]}
        return obj

    def _form_obj(self, form):
        fields = sorted([f for f in self.fields if f["form_id"] == form["form_id"]],
                        key=lambda f: f["order"])
        return {
            "id": form["form_id"],
            "title": form["title"],
            "language": form["language"],
            "workspace": {"href": f"https://api.typeform.com/workspaces/{form['workspace']}"},
            "settings": {"is_public": form["is_public"]},
            "fields": [self._field_obj(f) for f in fields],
            "_links": {"display": f"https://orbitlabs.typeform.com/to/{form['form_id']}"},
            "created_at": form["created_time"],
            "last_updated_at": form["last_updated_time"],
        }

    def _coerce_answer_value(self, field_type, raw):
        if field_type == "rating":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return raw
        return raw

    def _answer_obj(self, a):
        field_type = a["field_type"]
        value = self._coerce_answer_value(field_type, a["answer"])
        obj = {
            "field": {"id": a["field_id"], "type": field_type, "ref": a["ref"]},
            "type": field_type,
        }
        if field_type == "multiple_choice":
            obj["choice"] = {"label": value}
        elif field_type == "rating":
            obj["number"] = value
        elif field_type == "email":
            obj["email"] = value
        else:
            obj["text"] = value
        return obj

    def _response_obj(self, r):
        answers = [self._answer_obj(a) for a in self.answers if a["response_id"] == r["response_id"]]
        return {
            "response_id": r["response_id"],
            "landed_at": r["landed_time"],
            "submitted_at": r["submitted_time"],
            "answers": answers,
        }

    def _find_form(self, form_id):
        return next((f for f in self.forms if f["form_id"] == form_id), None)

    # --- Forms -------------------------------------------------------------
    def list_forms(self) -> Dict[str, Any]:
        items = [{
            "id": f["form_id"],
            "title": f["title"],
            "last_updated_at": f["last_updated_time"],
            "_links": {"display": f"https://orbitlabs.typeform.com/to/{f['form_id']}"},
        } for f in self.forms]
        return {"status": "ok", "output": {
            "total_items": len(items),
            "page_count": 1,
            "items": items,
        }}

    def get_form(self, form_id: str) -> Dict[str, Any]:
        form = self._find_form(form_id)
        if form is None:
            return {"status": "failed", "output": f"form {form_id} not found"}
        return {"status": "ok", "output": self._form_obj(form)}

    def create_form(self, title: str, workspace: str = "ws-orbit-labs", language: str = "en",
                    is_public: bool = False, fields: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        form_id = self._new_id("frm")
        now = self._now()
        form = {
            "form_id": form_id,
            "title": title if title is not None else "Untitled form",
            "workspace": workspace or "ws-orbit-labs",
            "language": language or "en",
            "is_public": bool(is_public),
            "response_count": 0,
            "created_time": now,
            "last_updated_time": now,
        }
        self.forms.append(form)
        for i, f in enumerate(fields or [], start=1):
            self.fields.append({
                "field_id": self._new_id("fld"),
                "form_id": form_id,
                "title": f.get("title", ""),
                "field_type": f.get("type", "short_text"),
                "ref": f.get("ref", f"field_{i}"),
                "required": bool(f.get("required", False)),
                "choices": [c.get("label") if isinstance(c, dict) else c
                            for c in (f.get("properties", {}) or {}).get("choices", [])],
                "order": i,
            })
        return {"status": "ok", "output": self._form_obj(form)}

    def update_form(self, form_id: str, title: str | None = None, language: str | None = None,
                    is_public: bool | None = None) -> Dict[str, Any]:
        form = self._find_form(form_id)
        if form is None:
            return {"status": "failed", "output": f"form {form_id} not found"}
        if title is not None:
            form["title"] = title
        if language is not None:
            form["language"] = language
        if is_public is not None:
            form["is_public"] = bool(is_public)
        form["last_updated_time"] = self._now()
        return {"status": "ok", "output": self._form_obj(form)}

    def delete_form(self, form_id: str) -> Dict[str, Any]:
        form = self._find_form(form_id)
        if form is None:
            return {"status": "failed", "output": f"form {form_id} not found"}
        self.forms.remove(form)
        response_ids = [r["response_id"] for r in self.responses if r["form_id"] == form_id]
        self.fields[:] = [f for f in self.fields if f["form_id"] != form_id]
        self.responses[:] = [r for r in self.responses if r["form_id"] != form_id]
        self.answers[:] = [a for a in self.answers if a["response_id"] not in response_ids]
        return {"status": "ok", "output": {"deleted": True, "id": form_id}}

    # --- Responses ---------------------------------------------------------
    def list_responses(self, form_id: str, completed: bool | None = None) -> Dict[str, Any]:
        if self._find_form(form_id) is None:
            return {"status": "failed", "output": f"form {form_id} not found"}
        resp = [r for r in self.responses if r["form_id"] == form_id]
        if completed is not None:
            resp = [r for r in resp if r["completed"] == completed]
        return {"status": "ok", "output": {
            "total_items": len(resp),
            "page_count": 1,
            "items": [self._response_obj(r) for r in resp],
        }}

    # --- Insights ----------------------------------------------------------
    def insights_summary(self, form_id: str) -> Dict[str, Any]:
        form = self._find_form(form_id)
        if form is None:
            return {"status": "failed", "output": f"form {form_id} not found"}
        resp = [r for r in self.responses if r["form_id"] == form_id]
        total = len(resp)
        completed = len([r for r in resp if r["completed"]])
        fields = sorted([f for f in self.fields if f["form_id"] == form_id],
                        key=lambda f: f["order"])
        field_summaries = []
        for f in fields:
            answers = [a for a in self.answers if a["field_id"] == f["field_id"]]
            summary = {
                "field": {"id": f["field_id"], "title": f["title"], "type": f["field_type"]},
                "answer_count": len(answers),
            }
            if f["field_type"] == "rating":
                values = []
                for a in answers:
                    try:
                        values.append(int(a["answer"]))
                    except (TypeError, ValueError):
                        pass
                summary["average"] = round(sum(values) / len(values), 2) if values else None
            elif f["field_type"] == "multiple_choice":
                counts = {}
                for a in answers:
                    counts[a["answer"]] = counts.get(a["answer"], 0) + 1
                summary["choices"] = counts
            field_summaries.append(summary)
        completion_rate = round(completed / total, 2) if total else 0.0
        return {"status": "ok", "output": {
            "form": {"id": form_id, "title": form["title"]},
            "total_responses": total,
            "completed_responses": completed,
            "completion_rate": completion_rate,
            "fields": field_summaries,
        }}


if __name__ == "__main__":
    s = TypeformSession(seed=12)
    print(s.list_forms())
    print(s.get_form("frm-csat-01"))
