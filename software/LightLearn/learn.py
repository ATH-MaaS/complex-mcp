from typing import Dict, List, Optional
from pathlib import Path
import random, sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed


COURSE_LEVELS = ("beginner", "intermediate", "advanced")

SEED_COURSES = [
    ("Intro to Python",           "Alice Rivers",   "Learn Python basics from zero.",     "programming", "beginner"),
    ("Web Development with Flask","Bob Chen",       "Build web apps with Flask.",         "programming", "intermediate"),
    ("Applied Statistics",        "Dr. Priya Rao",  "Probability, tests, and inference.", "math",        "advanced"),
]

SEED_LESSONS = [
    (0, "Getting Started",        "Install Python and run hello world.",          15, 1, True),
    (0, "Variables and Types",    "Numbers, strings, booleans.",                  20, 2, True),
    (0, "Control Flow",           "if/else, loops.",                              25, 3, False),
    (1, "Flask Basics",           "Routes and templates.",                        30, 1, True),
    (1, "Working with Databases", "SQLAlchemy essentials.",                       35, 2, False),
    (1, "Deploying to Prod",      "Gunicorn, nginx, and env config.",             40, 3, False),
    (2, "Probability Refresher",  "Sample spaces and random variables.",          30, 1, False),
    (2, "Hypothesis Testing",     "t-tests and p-values.",                        45, 2, False),
]

SEED_ENROLLMENTS = [
    (0,  -3, 100, True),
    (1,  -1,  40, False),
    (2,   0,   0, False),
]

SEED_QUIZZES = [
    (0, "What symbol starts a Python comment?", ["//", "#", "--", "/*"], 1),
    (1, "Which type is immutable?",             ["list", "dict", "tuple", "set"], 2),
    (3, "Which decorator declares a Flask route?", ["@app.get", "@app.route", "@route", "@flask"], 1),
    (6, "P(A and B) for independent A,B equals?", ["P(A)+P(B)", "P(A)*P(B)", "P(A|B)", "1-P(A)"], 1),
]

SEED_ATTEMPTS = [
    (0, 1,  -3),
    (1, 0,  -2),
    (2, 1,  -1),
]


@dataclass
class Course:
    cid: str
    title: str
    instructor: str
    description: str
    category: str
    level: str


@dataclass
class Lesson:
    lsid: str
    course_id: str
    title: str
    content: str
    duration_min: int
    order: int
    is_completed: bool = False


@dataclass
class Enrollment:
    enid: str
    course_id: str
    enrolled_at: str
    progress_percent: int
    is_completed: bool
    completed_at: str = ""


@dataclass
class Quiz:
    qzid: str
    lesson_id: str
    question: str
    options: List[str] = field(default_factory=list)
    correct_index: int = 0


@dataclass
class QuizAttempt:
    qaid: str
    quiz_id: str
    selected_index: int
    is_correct: bool
    attempted_at: str


class LearnSession:
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
            self.courses: Dict[str, Course] = {}
            self.lessons: Dict[str, Lesson] = {}
            self.enrollments: Dict[str, Enrollment] = {}
            self.quizzes: Dict[str, Quiz] = {}
            self.attempts: Dict[str, QuizAttempt] = {}
            self._seed_all()
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightLearn')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def uuid(self) -> str:
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "".join(self.rng.choices(alphabet, k=22))

    def _now(self) -> str:
        return self._today.isoformat(timespec="minutes")

    def _offset_dt(self, days: int) -> str:
        return (self._today + timedelta(days=days)).isoformat(timespec="minutes")

    def _seed_all(self) -> None:
        course_ids: List[str] = []
        for title, instr, desc, cat, level in SEED_COURSES:
            c = Course(
                cid=self.uuid(),
                title=title,
                instructor=instr,
                description=desc,
                category=cat,
                level=level,
            )
            self.courses[c.cid] = c
            course_ids.append(c.cid)

        lesson_ids: List[str] = []
        for cidx, ltitle, lcontent, dur, order, done in SEED_LESSONS:
            l = Lesson(
                lsid=self.uuid(),
                course_id=course_ids[cidx],
                title=ltitle,
                content=lcontent,
                duration_min=dur,
                order=order,
                is_completed=done,
            )
            self.lessons[l.lsid] = l
            lesson_ids.append(l.lsid)

        for cidx, enroll_off, progress, completed in SEED_ENROLLMENTS:
            enrolled = self._offset_dt(enroll_off)
            e = Enrollment(
                enid=self.uuid(),
                course_id=course_ids[cidx],
                enrolled_at=enrolled,
                progress_percent=progress,
                is_completed=completed,
                completed_at=self._now() if completed else "",
            )
            self.enrollments[e.enid] = e

        quiz_ids: List[str] = []
        for lidx, question, options, correct in SEED_QUIZZES:
            q = Quiz(
                qzid=self.uuid(),
                lesson_id=lesson_ids[lidx],
                question=question,
                options=list(options),
                correct_index=correct,
            )
            self.quizzes[q.qzid] = q
            quiz_ids.append(q.qzid)

        for qidx, selected, off in SEED_ATTEMPTS:
            qz = self.quizzes[quiz_ids[qidx]]
            a = QuizAttempt(
                qaid=self.uuid(),
                quiz_id=qz.qzid,
                selected_index=selected,
                is_correct=(selected == qz.correct_index),
                attempted_at=self._offset_dt(off),
            )
            self.attempts[a.qaid] = a

    def get_session_dict(self) -> Dict:
        return {
            "courses": {k: asdict(v) for k, v in self.courses.items()},
            "lessons": {k: asdict(v) for k, v in self.lessons.items()},
            "enrollments": {k: asdict(v) for k, v in self.enrollments.items()},
            "quizzes": {k: asdict(v) for k, v in self.quizzes.items()},
            "attempts": {k: asdict(v) for k, v in self.attempts.items()},
        }

    def _course_summary(self, c: Course) -> Dict:
        return {
            "cid": c.cid,
            "title": c.title,
            "instructor": c.instructor,
            "category": c.category,
            "level": c.level,
        }

    def _find_enrollment(self, course_id: str) -> Optional[Enrollment]:
        for e in self.enrollments.values():
            if e.course_id == course_id:
                return e
        return None

    def list_courses(self, category: Optional[str] = None,
                     level: Optional[str] = None) -> Dict:
        items = list(self.courses.values())
        if category:
            items = [c for c in items if c.category == category]
        if level:
            items = [c for c in items if c.level == level]
        items.sort(key=lambda c: c.title)
        return {"status": "ok", "output": [self._course_summary(c) for c in items]}

    def get_course(self, cid: str) -> Dict:
        c = self.courses.get(cid)
        if not c:
            return {"status": "failed", "output": f"course {cid} not found"}
        return {"status": "ok", "output": asdict(c)}

    def enroll(self, course_id: str) -> Dict:
        if course_id not in self.courses:
            return {"status": "failed", "output": f"course {course_id} not found"}
        existing = self._find_enrollment(course_id)
        if existing:
            return {"status": "failed", "output": "already enrolled"}
        e = Enrollment(
            enid=self.uuid(),
            course_id=course_id,
            enrolled_at=self._now(),
            progress_percent=0,
            is_completed=False,
            completed_at="",
        )
        self.enrollments[e.enid] = e
        return {"status": "ok", "output": asdict(e)}

    def unenroll(self, course_id: str) -> Dict:
        e = self._find_enrollment(course_id)
        if not e:
            return {"status": "failed", "output": "not enrolled"}
        del self.enrollments[e.enid]
        return {"status": "ok", "output": {"course_id": course_id, "unenrolled": True}}

    def list_lessons(self, course_id: str) -> Dict:
        if course_id not in self.courses:
            return {"status": "failed", "output": f"course {course_id} not found"}
        items = [l for l in self.lessons.values() if l.course_id == course_id]
        items.sort(key=lambda l: l.order)
        return {"status": "ok", "output": [asdict(l) for l in items]}

    def get_lesson(self, lsid: str) -> Dict:
        l = self.lessons.get(lsid)
        if not l:
            return {"status": "failed", "output": f"lesson {lsid} not found"}
        return {"status": "ok", "output": asdict(l)}

    def complete_lesson(self, lesson_id: str) -> Dict:
        l = self.lessons.get(lesson_id)
        if not l:
            return {"status": "failed", "output": f"lesson {lesson_id} not found"}
        l.is_completed = True
        siblings = [x for x in self.lessons.values() if x.course_id == l.course_id]
        if siblings:
            done = sum(1 for x in siblings if x.is_completed)
            pct = int(round(100 * done / len(siblings)))
            e = self._find_enrollment(l.course_id)
            if e:
                e.progress_percent = pct
                if pct >= 100 and not e.is_completed:
                    e.is_completed = True
                    e.completed_at = self._now()
        return {"status": "ok", "output": asdict(l)}

    def list_enrollments(self, is_completed: Optional[bool] = None) -> Dict:
        items = list(self.enrollments.values())
        if is_completed is not None:
            items = [e for e in items if e.is_completed == is_completed]
        items.sort(key=lambda e: e.enrolled_at, reverse=True)
        return {"status": "ok", "output": [asdict(e) for e in items]}

    def get_enrollment(self, course_id: str) -> Dict:
        e = self._find_enrollment(course_id)
        if not e:
            return {"status": "failed", "output": f"no enrollment for course {course_id}"}
        return {"status": "ok", "output": asdict(e)}

    def update_progress(self, course_id: str, progress_percent: int) -> Dict:
        e = self._find_enrollment(course_id)
        if not e:
            return {"status": "failed", "output": f"no enrollment for course {course_id}"}
        if progress_percent < 0 or progress_percent > 100:
            return {"status": "failed", "output": "progress_percent must be in [0, 100]"}
        e.progress_percent = int(progress_percent)
        if e.progress_percent >= 100:
            if not e.is_completed:
                e.is_completed = True
                e.completed_at = self._now()
        else:
            e.is_completed = False
            e.completed_at = ""
        return {"status": "ok", "output": asdict(e)}

    def list_quizzes(self, lesson_id: Optional[str] = None) -> Dict:
        items = list(self.quizzes.values())
        if lesson_id:
            items = [q for q in items if q.lesson_id == lesson_id]
        return {"status": "ok", "output": [asdict(q) for q in items]}

    def get_quiz(self, qzid: str) -> Dict:
        q = self.quizzes.get(qzid)
        if not q:
            return {"status": "failed", "output": f"quiz {qzid} not found"}
        return {"status": "ok", "output": asdict(q)}

    def submit_quiz(self, quiz_id: str, selected_index: int) -> Dict:
        q = self.quizzes.get(quiz_id)
        if not q:
            return {"status": "failed", "output": f"quiz {quiz_id} not found"}
        if selected_index < 0 or selected_index >= len(q.options):
            return {"status": "failed", "output": "selected_index out of range"}
        a = QuizAttempt(
            qaid=self.uuid(),
            quiz_id=quiz_id,
            selected_index=int(selected_index),
            is_correct=(int(selected_index) == q.correct_index),
            attempted_at=self._now(),
        )
        self.attempts[a.qaid] = a
        return {"status": "ok", "output": asdict(a)}

    def list_quiz_attempts(self, quiz_id: Optional[str] = None) -> Dict:
        items = list(self.attempts.values())
        if quiz_id:
            items = [a for a in items if a.quiz_id == quiz_id]
        items.sort(key=lambda a: a.attempted_at, reverse=True)
        return {"status": "ok", "output": [asdict(a) for a in items]}

    def search_courses(self, query: str) -> Dict:
        q = query.lower()
        items = [c for c in self.courses.values()
                 if q in c.title.lower()
                 or q in c.instructor.lower()
                 or q in c.description.lower()
                 or q in c.category.lower()]
        items.sort(key=lambda c: c.title)
        return {"status": "ok", "output": [self._course_summary(c) for c in items]}

    def list_finished(self) -> Dict:
        items = [e for e in self.enrollments.values() if e.is_completed]
        items.sort(key=lambda e: e.completed_at, reverse=True)
        return {"status": "ok", "output": [asdict(e) for e in items]}

    def get_course_progress(self, course_id: str) -> Dict:
        if course_id not in self.courses:
            return {"status": "failed", "output": f"course {course_id} not found"}
        siblings = [l for l in self.lessons.values() if l.course_id == course_id]
        total = len(siblings)
        done = sum(1 for l in siblings if l.is_completed)
        pct = int(round(100 * done / total)) if total else 0
        e = self._find_enrollment(course_id)
        return {
            "status": "ok",
            "output": {
                "course_id": course_id,
                "total_lessons": total,
                "completed_lessons": done,
                "progress_percent": pct,
                "enrolled": e is not None,
                "is_completed": bool(e.is_completed) if e else False,
            },
        }

    def get_stats(self) -> Dict:
        by_level: Dict[str, int] = {lv: 0 for lv in COURSE_LEVELS}
        by_category: Dict[str, int] = {}
        for c in self.courses.values():
            by_level[c.level] = by_level.get(c.level, 0) + 1
            by_category[c.category] = by_category.get(c.category, 0) + 1
        correct = sum(1 for a in self.attempts.values() if a.is_correct)
        total_attempts = len(self.attempts)
        return {
            "status": "ok",
            "output": {
                "courses": len(self.courses),
                "lessons": len(self.lessons),
                "enrollments": len(self.enrollments),
                "quizzes": len(self.quizzes),
                "attempts": total_attempts,
                "correct_attempts": correct,
                "by_level": by_level,
                "by_category": by_category,
            },
        }
