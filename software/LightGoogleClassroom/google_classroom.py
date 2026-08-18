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
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _to_float(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return f


class GoogleClassroomSession:
    """Deterministic sandbox for the Google Classroom mock, ported from the FastAPI service.

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

            with open(CORPUS_PATH / "google_classroom.yaml") as f:
                info = yaml.safe_load(f)

            self.courses: List[Dict[str, Any]] = self._coerce_courses(info.get("courses", []))
            self.coursework: List[Dict[str, Any]] = self._coerce_coursework(info.get("coursework", []))
            self.topics: List[Dict[str, Any]] = self._coerce_topics(info.get("topics", []))
            self.students: List[Dict[str, Any]] = self._coerce_students(info.get("students", []))
            self.teachers: List[Dict[str, Any]] = self._coerce_teachers(info.get("teachers", []))
            self.submissions: List[Dict[str, Any]] = self._coerce_submissions(info.get("submissions", []))
            self.announcements: List[Dict[str, Any]] = self._coerce_announcements(info.get("announcements", []))
            self.materials: List[Dict[str, Any]] = self._coerce_materials(info.get("materials", []))

            self._next_course_id = 5
            self._next_cw_id = 400
            self._next_topic_id = 400
            self._next_sub_id = 100
            self._next_ann_id = 20
            self._next_mat_id = 10
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightGoogleClassroom')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {
            "courses": self.courses,
            "coursework": self.coursework,
            "topics": self.topics,
            "students": self.students,
            "teachers": self.teachers,
            "submissions": self.submissions,
            "announcements": self.announcements,
            "materials": self.materials,
        }

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789"
        return ''.join(self.rng.choices(alphabet, k=16))

    # --- coercion (mirrors source _coerce_* + _mutable_store helpers) ------
    def _coerce_courses(self, rows):
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "name": r["name"],
                "section": r["section"],
                "descriptionHeading": r["descriptionHeading"],
                "description": r["description"],
                "room": r["room"],
                "ownerId": r["ownerId"],
                "courseState": r["courseState"],
                "creationTime": r["creationTime"],
                "updateTime": r["updateTime"],
                "enrollmentCode": r["enrollmentCode"],
                "alternateLink": r["alternateLink"],
                "guardiansEnabled": str(r["guardiansEnabled"]).lower() == "true",
                "calendarId": r["calendarId"],
            })
        return out

    def _coerce_coursework(self, rows):
        out = []
        for r in rows:
            cw = {
                "courseId": r["courseId"],
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "state": r["state"],
                "maxPoints": _to_float(r.get("maxPoints")),
                "workType": r["workType"],
                "topicId": (str(r["topicId"]) if r.get("topicId") not in (None,) else "") or None,
                "creationTime": r["creationTime"],
                "updateTime": r["updateTime"],
                "alternateLink": r["alternateLink"],
            }
            if r.get("dueDate_year") and r["dueDate_year"]:
                cw["dueDate"] = {
                    "year": _to_int(r["dueDate_year"]),
                    "month": _to_int(r["dueDate_month"]),
                    "day": _to_int(r["dueDate_day"]),
                }
            else:
                cw["dueDate"] = None
            if r.get("dueTime_hours") and r["dueTime_hours"]:
                cw["dueTime"] = {
                    "hours": _to_int(r["dueTime_hours"]),
                    "minutes": _to_int(r["dueTime_minutes"]),
                }
            else:
                cw["dueTime"] = None
            out.append(cw)
        return out

    def _coerce_topics(self, rows):
        return [{
            "courseId": r["courseId"],
            "topicId": r["topicId"],
            "name": r["name"],
            "updateTime": r["updateTime"],
        } for r in rows]

    def _coerce_students(self, rows):
        return [{
            "courseId": r["courseId"],
            "userId": r["userId"],
            "profile": {
                "id": r["userId"],
                "name": {"fullName": r["fullName"]},
                "emailAddress": r["emailAddress"],
                "photoUrl": r["photoUrl"],
            },
        } for r in rows]

    def _coerce_teachers(self, rows):
        return [{
            "courseId": r["courseId"],
            "userId": r["userId"],
            "profile": {
                "id": r["userId"],
                "name": {"fullName": r["fullName"]},
                "emailAddress": r["emailAddress"],
                "photoUrl": r["photoUrl"],
            },
        } for r in rows]

    def _coerce_submissions(self, rows):
        out = []
        for r in rows:
            sub = {
                "courseId": r["courseId"],
                "courseWorkId": r["courseWorkId"],
                "id": r["id"],
                "userId": r["userId"],
                "state": r["state"],
                "late": str(r["late"]).lower() == "true",
                "creationTime": r["creationTime"],
                "updateTime": r["updateTime"],
                "alternateLink": r["alternateLink"],
            }
            sub["assignedGrade"] = _to_float(r.get("assignedGrade"))
            sub["draftGrade"] = _to_float(r.get("draftGrade"))
            out.append(sub)
        return out

    def _coerce_announcements(self, rows):
        return [{
            "courseId": r["courseId"],
            "id": r["id"],
            "text": r["text"],
            "state": r["state"],
            "creationTime": r["creationTime"],
            "updateTime": r["updateTime"],
            "creatorUserId": r["creatorUserId"],
            "alternateLink": r["alternateLink"],
        } for r in rows]

    def _coerce_materials(self, rows):
        out = []
        for r in rows:
            out.append({
                "courseId": r["courseId"],
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "state": r["state"],
                "creationTime": r["creationTime"],
                "updateTime": r["updateTime"],
                "creatorUserId": r["creatorUserId"],
                "topicId": (str(r["topicId"]) if r.get("topicId") is not None else "") or None,
                "alternateLink": r["alternateLink"],
                "materials": [{"link": {"url": r["materialUrl"], "title": r["title"]}}] if r.get("materialUrl") else [],
            })
        return out

    # -----------------------------------------------------------------------
    # Courses
    # -----------------------------------------------------------------------
    def list_courses(self, course_states: str | None = None, page_size: int = 20,
                     page_token: int = 0) -> Dict[str, Any]:
        results = list(self.courses)
        if course_states:
            states = [s.strip().upper() for s in course_states.split(",")]
            results = [c for c in results if c["courseState"] in states]

        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"courses": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_course(self, course_id: str) -> Dict[str, Any]:
        for c in self.courses:
            if c["id"] == course_id:
                return {"status": "ok", "output": {"course": c}}
        return {"status": "failed", "output": f"Course {course_id} not found"}

    def create_course(self, name: str, section: str | None = None,
                      descriptionHeading: str | None = None, description: str | None = None,
                      room: str | None = None, ownerId: str | None = None) -> Dict[str, Any]:
        if name is None:
            return {"status": "failed", "output": "Missing required field: name"}
        now = self._now()
        course = {
            "id": f"course_{self._next_course_id:03d}",
            "name": name,
            "section": section if section is not None else "",
            "descriptionHeading": descriptionHeading if descriptionHeading is not None else "",
            "description": description if description is not None else "",
            "room": room if room is not None else "",
            "ownerId": ownerId if ownerId is not None else "teacher_001",
            "courseState": "ACTIVE",
            "creationTime": now,
            "updateTime": now,
            "enrollmentCode": f"code{self._next_course_id}",
            "alternateLink": f"https://classroom.google.com/c/course_{self._next_course_id:03d}",
            "guardiansEnabled": False,
            "calendarId": f"calendar_{self._next_course_id:03d}",
        }
        self.courses.append(course)
        self._next_course_id += 1
        return {"status": "ok", "output": {"course": course}}

    def update_course(self, course_id: str, name: str | None = None, section: str | None = None,
                      descriptionHeading: str | None = None, description: str | None = None,
                      room: str | None = None, courseState: str | None = None) -> Dict[str, Any]:
        data = {}
        for k, v in [("name", name), ("section", section),
                     ("descriptionHeading", descriptionHeading), ("description", description),
                     ("room", room), ("courseState", courseState)]:
            if v is not None:
                data[k] = v
        for i, c in enumerate(self.courses):
            if c["id"] == course_id:
                updatable = {"name", "section", "descriptionHeading", "description",
                             "room", "courseState", "guardiansEnabled"}
                for k, v in data.items():
                    if k in updatable:
                        self.courses[i][k] = v
                self.courses[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"course": self.courses[i]}}
        return {"status": "failed", "output": f"Course {course_id} not found"}

    def archive_course(self, course_id: str) -> Dict[str, Any]:
        for i, c in enumerate(self.courses):
            if c["id"] == course_id:
                self.courses[i]["courseState"] = "ARCHIVED"
                self.courses[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"course": self.courses[i]}}
        return {"status": "failed", "output": f"Course {course_id} not found"}

    # -----------------------------------------------------------------------
    # Course Work
    # -----------------------------------------------------------------------
    def list_coursework(self, course_id: str, topic_id: str | None = None,
                        course_work_states: str | None = None, order_by: str | None = None,
                        page_size: int = 20, page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [cw for cw in self.coursework if cw["courseId"] == course_id]

        if topic_id:
            results = [cw for cw in results if cw["topicId"] == topic_id]
        if course_work_states:
            states = [s.strip().upper() for s in course_work_states.split(",")]
            results = [cw for cw in results if cw["state"] in states]

        if order_by:
            if "updateTime" in order_by:
                reverse = "desc" in order_by.lower()
                results = sorted(results, key=lambda x: x["updateTime"], reverse=reverse)
            elif "dueDate" in order_by:
                def due_sort_key(cw):
                    if cw.get("dueDate"):
                        return f"{cw['dueDate']['year']:04d}-{cw['dueDate']['month']:02d}-{cw['dueDate']['day']:02d}"
                    return "9999-99-99"
                reverse = "desc" in order_by.lower()
                results = sorted(results, key=due_sort_key, reverse=reverse)

        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"courseWork": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_coursework(self, course_id: str, coursework_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for cw in self.coursework:
            if cw["courseId"] == course_id and cw["id"] == coursework_id:
                return {"status": "ok", "output": {"courseWork": cw}}
        return {"status": "failed", "output": f"CourseWork {coursework_id} not found in course {course_id}"}

    def create_coursework(self, course_id: str, title: str, workType: str,
                          description: str | None = None, state: str | None = None,
                          maxPoints: float | None = None, topicId: str | None = None,
                          dueDate: Dict[str, Any] | None = None,
                          dueTime: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if title is None:
            return {"status": "failed", "output": "Missing required field: title"}
        if workType is None:
            return {"status": "failed", "output": "Missing required field: workType"}

        now = self._now()
        cw = {
            "courseId": course_id,
            "id": f"cw_{self._next_cw_id}",
            "title": title,
            "description": description if description is not None else "",
            "state": state if state is not None else "PUBLISHED",
            "maxPoints": float(maxPoints) if maxPoints else None,
            "workType": workType,
            "topicId": topicId,
            "creationTime": now,
            "updateTime": now,
            "dueDate": dueDate,
            "dueTime": dueTime,
            "alternateLink": f"https://classroom.google.com/c/{course_id}/a/cw_{self._next_cw_id}",
        }
        self.coursework.append(cw)
        self._next_cw_id += 1
        return {"status": "ok", "output": {"courseWork": cw}}

    def update_coursework(self, course_id: str, coursework_id: str, title: str | None = None,
                          description: str | None = None, state: str | None = None,
                          maxPoints: float | None = None, topicId: str | None = None,
                          dueDate: Dict[str, Any] | None = None,
                          dueTime: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        data = {}
        for k, v in [("title", title), ("description", description), ("state", state),
                     ("maxPoints", maxPoints), ("topicId", topicId),
                     ("dueDate", dueDate), ("dueTime", dueTime)]:
            if v is not None:
                data[k] = v
        for i, cw in enumerate(self.coursework):
            if cw["courseId"] == course_id and cw["id"] == coursework_id:
                updatable = {"title", "description", "state", "maxPoints",
                             "dueDate", "dueTime", "topicId"}
                for k, v in data.items():
                    if k in updatable:
                        if k == "maxPoints" and v is not None:
                            self.coursework[i][k] = float(v)
                        else:
                            self.coursework[i][k] = v
                self.coursework[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"courseWork": self.coursework[i]}}
        return {"status": "failed", "output": f"CourseWork {coursework_id} not found in course {course_id}"}

    def delete_coursework(self, course_id: str, coursework_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, cw in enumerate(self.coursework):
            if cw["courseId"] == course_id and cw["id"] == coursework_id:
                self.coursework.pop(i)
                return {"status": "ok", "output": {"deleted": True}}
        return {"status": "failed", "output": f"CourseWork {coursework_id} not found in course {course_id}"}

    # -----------------------------------------------------------------------
    # Topics
    # -----------------------------------------------------------------------
    def list_topics(self, course_id: str, page_size: int = 20, page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [t for t in self.topics if t["courseId"] == course_id]
        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"topic": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_topic(self, course_id: str, topic_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for t in self.topics:
            if t["courseId"] == course_id and t["topicId"] == topic_id:
                return {"status": "ok", "output": {"topic": t}}
        return {"status": "failed", "output": f"Topic {topic_id} not found in course {course_id}"}

    def create_topic(self, course_id: str, name: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if not name:
            return {"status": "failed", "output": "Missing required field: name"}

        topic = {
            "courseId": course_id,
            "topicId": f"topic_{self._next_topic_id}",
            "name": name,
            "updateTime": self._now(),
        }
        self.topics.append(topic)
        self._next_topic_id += 1
        return {"status": "ok", "output": {"topic": topic}}

    def update_topic(self, course_id: str, topic_id: str, name: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, t in enumerate(self.topics):
            if t["courseId"] == course_id and t["topicId"] == topic_id:
                if name is not None:
                    self.topics[i]["name"] = name
                self.topics[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"topic": self.topics[i]}}
        return {"status": "failed", "output": f"Topic {topic_id} not found in course {course_id}"}

    def delete_topic(self, course_id: str, topic_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, t in enumerate(self.topics):
            if t["courseId"] == course_id and t["topicId"] == topic_id:
                self.topics.pop(i)
                return {"status": "ok", "output": {"deleted": True}}
        return {"status": "failed", "output": f"Topic {topic_id} not found in course {course_id}"}

    # -----------------------------------------------------------------------
    # Student Submissions
    # -----------------------------------------------------------------------
    def list_submissions(self, course_id: str, coursework_id: str, states: str | None = None,
                         late: bool | None = None, page_size: int = 20,
                         page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if not any(cw["courseId"] == course_id and cw["id"] == coursework_id
                   for cw in self.coursework):
            return {"status": "failed", "output": f"CourseWork {coursework_id} not found in course {course_id}"}

        results = [s for s in self.submissions
                   if s["courseId"] == course_id and s["courseWorkId"] == coursework_id]

        if states:
            state_list = [s.strip().upper() for s in states.split(",")]
            results = [s for s in results if s["state"] in state_list]
        if late is not None:
            results = [s for s in results if s["late"] == late]

        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"studentSubmissions": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_submission(self, course_id: str, coursework_id: str, submission_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for s in self.submissions:
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                return {"status": "ok", "output": {"studentSubmission": s}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    def grade_submission(self, course_id: str, coursework_id: str, submission_id: str,
                         assignedGrade: float | None = None,
                         draftGrade: float | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, s in enumerate(self.submissions):
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                if assignedGrade is not None:
                    self.submissions[i]["assignedGrade"] = float(assignedGrade)
                if draftGrade is not None:
                    self.submissions[i]["draftGrade"] = float(draftGrade)
                self.submissions[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"studentSubmission": self.submissions[i]}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    def return_submission(self, course_id: str, coursework_id: str, submission_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, s in enumerate(self.submissions):
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                self.submissions[i]["state"] = "RETURNED"
                self.submissions[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"studentSubmission": self.submissions[i]}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    def reclaim_submission(self, course_id: str, coursework_id: str, submission_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, s in enumerate(self.submissions):
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                self.submissions[i]["state"] = "RECLAIMED_BY_STUDENT"
                self.submissions[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"studentSubmission": self.submissions[i]}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    def turn_in_submission(self, course_id: str, coursework_id: str, submission_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, s in enumerate(self.submissions):
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                self.submissions[i]["state"] = "TURNED_IN"
                self.submissions[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"studentSubmission": self.submissions[i]}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    def modify_submission_attachments(self, course_id: str, coursework_id: str, submission_id: str,
                                      addAttachments: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        add_attachments = addAttachments or []
        for i, s in enumerate(self.submissions):
            if (s["courseId"] == course_id and s["courseWorkId"] == coursework_id
                    and s["id"] == submission_id):
                existing = s.get("assignmentSubmission") or {}
                attachments = list(existing.get("attachments", []))
                if isinstance(add_attachments, list):
                    attachments.extend(add_attachments)
                self.submissions[i]["assignmentSubmission"] = {"attachments": attachments}
                self.submissions[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"studentSubmission": self.submissions[i]}}
        return {"status": "failed", "output": f"Submission {submission_id} not found"}

    # -----------------------------------------------------------------------
    # Students
    # -----------------------------------------------------------------------
    def list_students(self, course_id: str, page_size: int = 30, page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [s for s in self.students if s["courseId"] == course_id]
        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"students": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_student(self, course_id: str, user_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for s in self.students:
            if s["courseId"] == course_id and s["userId"] == user_id:
                return {"status": "ok", "output": {"student": s}}
        return {"status": "failed", "output": f"Student {user_id} not found in course {course_id}"}

    def invite_student(self, course_id: str, emailAddress: str,
                       fullName: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if not emailAddress:
            return {"status": "failed", "output": "Missing required field: emailAddress"}

        email = emailAddress
        for s in self.students:
            if s["courseId"] == course_id and s["profile"]["emailAddress"] == email:
                return {"status": "failed", "output": f"Student with email {email} already enrolled in course {course_id}"}

        user_id = f"student_new_{len(self.students) + 1}"
        student = {
            "courseId": course_id,
            "userId": user_id,
            "profile": {
                "id": user_id,
                "name": {"fullName": fullName if fullName is not None else email.split("@")[0]},
                "emailAddress": email,
                "photoUrl": f"https://lh3.googleusercontent.com/a/{user_id}",
            },
        }
        self.students.append(student)
        return {"status": "ok", "output": {"student": student}}

    def remove_student(self, course_id: str, user_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, s in enumerate(self.students):
            if s["courseId"] == course_id and s["userId"] == user_id:
                self.students.pop(i)
                return {"status": "ok", "output": {"deleted": True}}
        return {"status": "failed", "output": f"Student {user_id} not found in course {course_id}"}

    # -----------------------------------------------------------------------
    # Teachers
    # -----------------------------------------------------------------------
    def list_teachers(self, course_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [t for t in self.teachers if t["courseId"] == course_id]
        return {"status": "ok", "output": {"teachers": results}}

    def get_teacher(self, course_id: str, user_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for t in self.teachers:
            if t["courseId"] == course_id and t["userId"] == user_id:
                return {"status": "ok", "output": {"teacher": t}}
        return {"status": "failed", "output": f"Teacher {user_id} not found in course {course_id}"}

    # -----------------------------------------------------------------------
    # Announcements
    # -----------------------------------------------------------------------
    def list_announcements(self, course_id: str, announcement_states: str | None = None,
                           page_size: int = 20, page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [a for a in self.announcements if a["courseId"] == course_id]

        if announcement_states:
            states = [s.strip().upper() for s in announcement_states.split(",")]
            results = [a for a in results if a["state"] in states]

        results = sorted(results, key=lambda x: x["creationTime"], reverse=True)

        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"announcements": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_announcement(self, course_id: str, announcement_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for a in self.announcements:
            if a["courseId"] == course_id and a["id"] == announcement_id:
                return {"status": "ok", "output": {"announcement": a}}
        return {"status": "failed", "output": f"Announcement {announcement_id} not found in course {course_id}"}

    def create_announcement(self, course_id: str, text: str,
                            state: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if not text:
            return {"status": "failed", "output": "Missing required field: text"}

        now = self._now()
        ann = {
            "courseId": course_id,
            "id": f"ann_{self._next_ann_id:03d}",
            "text": text,
            "state": state if state is not None else "PUBLISHED",
            "creationTime": now,
            "updateTime": now,
            "creatorUserId": "teacher_001",
            "alternateLink": f"https://classroom.google.com/c/{course_id}/p/ann_{self._next_ann_id:03d}",
        }
        self.announcements.append(ann)
        self._next_ann_id += 1
        return {"status": "ok", "output": {"announcement": ann}}

    def update_announcement(self, course_id: str, announcement_id: str, text: str | None = None,
                            state: str | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        data = {}
        for k, v in [("text", text), ("state", state)]:
            if v is not None:
                data[k] = v
        for i, a in enumerate(self.announcements):
            if a["courseId"] == course_id and a["id"] == announcement_id:
                updatable = {"text", "state"}
                for k, v in data.items():
                    if k in updatable:
                        self.announcements[i][k] = v
                self.announcements[i]["updateTime"] = self._now()
                return {"status": "ok", "output": {"announcement": self.announcements[i]}}
        return {"status": "failed", "output": f"Announcement {announcement_id} not found in course {course_id}"}

    def delete_announcement(self, course_id: str, announcement_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for i, a in enumerate(self.announcements):
            if a["courseId"] == course_id and a["id"] == announcement_id:
                self.announcements.pop(i)
                return {"status": "ok", "output": {"deleted": True}}
        return {"status": "failed", "output": f"Announcement {announcement_id} not found in course {course_id}"}

    # -----------------------------------------------------------------------
    # Course Work Materials
    # -----------------------------------------------------------------------
    def list_materials(self, course_id: str, page_size: int = 20, page_token: int = 0) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}

        results = [m for m in self.materials if m["courseId"] == course_id]
        total = len(results)
        offset = int(page_token) if page_token else 0
        page_results = results[offset: offset + page_size]
        next_token = str(offset + page_size) if offset + page_size < total else None
        resp = {"courseWorkMaterial": page_results}
        if next_token:
            resp["nextPageToken"] = next_token
        return {"status": "ok", "output": resp}

    def get_material(self, course_id: str, material_id: str) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        for m in self.materials:
            if m["courseId"] == course_id and m["id"] == material_id:
                return {"status": "ok", "output": {"courseWorkMaterial": m}}
        return {"status": "failed", "output": f"Material {material_id} not found in course {course_id}"}

    def create_material(self, course_id: str, title: str, description: str | None = None,
                        topicId: str | None = None,
                        materials: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        if not any(c["id"] == course_id for c in self.courses):
            return {"status": "failed", "output": f"Course {course_id} not found"}
        if not title:
            return {"status": "failed", "output": "Missing required field: title"}

        now = self._now()
        mat = {
            "courseId": course_id,
            "id": f"mat_{self._next_mat_id:03d}",
            "title": title,
            "description": description if description is not None else "",
            "state": "PUBLISHED",
            "creationTime": now,
            "updateTime": now,
            "creatorUserId": "teacher_001",
            "topicId": topicId,
            "alternateLink": f"https://classroom.google.com/c/{course_id}/m/mat_{self._next_mat_id:03d}",
            "materials": materials if materials is not None else [],
        }
        self.materials.append(mat)
        self._next_mat_id += 1
        return {"status": "ok", "output": {"courseWorkMaterial": mat}}


if __name__ == "__main__":
    s = GoogleClassroomSession(seed=12)
    print(s.list_courses())
    print(s.get_course("course_001"))
