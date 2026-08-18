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

# Ordered hiring pipeline stages used to advance applications.
STAGES = ["Application Review", "Interview", "Offer", "Hired"]


def _opt_int(v, default=0) -> int:
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _opt_str_or_none(v):
    if v is None:
        return None
    s = str(v)
    return s or None


class GreenhouseSession:
    """Deterministic sandbox for the Greenhouse Harvest API mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "greenhouse.yaml") as f:
                info = yaml.safe_load(f)

            # candidates + applications: no coercion beyond copy
            self.candidates: List[Dict[str, Any]] = [dict(r) for r in info.get("candidates", [])]
            self.applications: List[Dict[str, Any]] = [dict(r) for r in info.get("applications", [])]
            # jobs: closed_at empty-string coerces to None
            self.jobs: List[Dict[str, Any]] = [
                {**dict(r), "closed_at": _opt_str_or_none(r.get("closed_at", "")) if str(r.get("closed_at", "")) != "" else None}
                for r in info.get("jobs", [])
            ]
            # scorecards: rating coerced string -> int (default 0)
            self.scorecards: List[Dict[str, Any]] = [
                {**dict(r), "rating": _opt_int(r.get("rating"), default=0)}
                for r in info.get("scorecards", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGreenhouse')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {
            "candidates": self.candidates,
            "jobs": self.jobs,
            "applications": self.applications,
            "scorecards": self.scorecards,
        }

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=8))

    def _new_id(self, prefix) -> str:
        return f"{prefix}-{self.uuid()}"

    def _find(self, store, obj_id):
        return next((x for x in store if x["id"] == obj_id), None)

    # --- Candidates --------------------------------------------------------
    def list_candidates(self) -> Dict[str, Any]:
        return {"status": "ok", "output": list(self.candidates)}

    def get_candidate(self, candidate_id: str) -> Dict[str, Any]:
        c = self._find(self.candidates, candidate_id)
        if not c:
            return {"status": "failed", "output": f"Candidate {candidate_id} not found"}
        return {"status": "ok", "output": c}

    def create_candidate(self, first_name: str, last_name: str, email: str | None = None,
                         phone: str | None = None, company: str | None = None,
                         title: str | None = None, source: str | None = None) -> Dict[str, Any]:
        if not first_name or not last_name:
            return {"status": "failed", "output": "first_name and last_name are required"}
        c = {
            "id": self._new_id("cand"),
            "first_name": first_name,
            "last_name": last_name,
            "email": email or "",
            "phone": phone or "",
            "company": company or "",
            "title": title or "",
            "source": source or "API",
            "created_at": self._now(),
        }
        self.candidates.append(c)
        return {"status": "ok", "output": c}

    # --- Jobs --------------------------------------------------------------
    def list_jobs(self, status: str | None = None) -> Dict[str, Any]:
        results = list(self.jobs)
        if status:
            results = [j for j in results if j["status"] == status]
        return {"status": "ok", "output": results}

    def get_job(self, job_id: str) -> Dict[str, Any]:
        j = self._find(self.jobs, job_id)
        if not j:
            return {"status": "failed", "output": f"Job {job_id} not found"}
        return {"status": "ok", "output": j}

    # --- Applications ------------------------------------------------------
    def list_applications(self, job_id: str | None = None, candidate_id: str | None = None,
                          status: str | None = None) -> Dict[str, Any]:
        results = list(self.applications)
        if job_id:
            results = [a for a in results if a["job_id"] == job_id]
        if candidate_id:
            results = [a for a in results if a["candidate_id"] == candidate_id]
        if status:
            results = [a for a in results if a["status"] == status]
        return {"status": "ok", "output": results}

    def get_application(self, application_id: str) -> Dict[str, Any]:
        a = self._find(self.applications, application_id)
        if not a:
            return {"status": "failed", "output": f"Application {application_id} not found"}
        return {"status": "ok", "output": a}

    def advance_application(self, application_id: str) -> Dict[str, Any]:
        a = self._find(self.applications, application_id)
        if not a:
            return {"status": "failed", "output": f"Application {application_id} not found"}
        if a["status"] != "active":
            return {"status": "failed", "output": f"Application {application_id} is not active"}
        current = a.get("current_stage")
        try:
            idx = STAGES.index(current)
        except ValueError:
            idx = 0
        if idx >= len(STAGES) - 1:
            a["current_stage"] = "Hired"
            a["status"] = "hired"
        else:
            a["current_stage"] = STAGES[idx + 1]
            if a["current_stage"] == "Hired":
                a["status"] = "hired"
        a["last_activity_at"] = self._now()
        return {"status": "ok", "output": a}

    def reject_application(self, application_id: str, reason: str | None = None) -> Dict[str, Any]:
        a = self._find(self.applications, application_id)
        if not a:
            return {"status": "failed", "output": f"Application {application_id} not found"}
        a["status"] = "rejected"
        a["rejection_reason"] = reason or "Not a fit"
        a["last_activity_at"] = self._now()
        return {"status": "ok", "output": a}

    # --- Scorecards --------------------------------------------------------
    def list_scorecards(self, application_id: str | None = None,
                        candidate_id: str | None = None) -> Dict[str, Any]:
        results = list(self.scorecards)
        if application_id:
            results = [s for s in results if s["application_id"] == application_id]
        if candidate_id:
            results = [s for s in results if s["candidate_id"] == candidate_id]
        return {"status": "ok", "output": results}


if __name__ == "__main__":
    s = GreenhouseSession(seed=12)
    print(s.list_candidates())
    print(s.list_jobs(status="open"))
