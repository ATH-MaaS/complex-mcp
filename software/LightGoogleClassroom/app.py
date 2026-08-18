from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGoogleClassroomSession
except ImportError:
    from software.LightGoogleClassroom.session import LightGoogleClassroomSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("google-classroom")

session_dict: Dict[str, LightGoogleClassroomSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGoogleClassroomSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.google_classroom_session.get_session_dict(),
    }


@mcp.tool
async def list_courses(session_id: str, course_states: str | None = None, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_courses(course_states, page_size, page_token)


@mcp.tool
async def get_course(course_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_course(course_id)


@mcp.tool
async def create_course(name: str, session_id: str, section: str | None = None, descriptionHeading: str | None = None, description: str | None = None, room: str | None = None, ownerId: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.create_course(name, section, descriptionHeading, description, room, ownerId)


@mcp.tool
async def update_course(course_id: str, session_id: str, name: str | None = None, section: str | None = None, descriptionHeading: str | None = None, description: str | None = None, room: str | None = None, courseState: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.update_course(course_id, name, section, descriptionHeading, description, room, courseState)


@mcp.tool
async def archive_course(course_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.archive_course(course_id)


@mcp.tool
async def list_coursework(course_id: str, session_id: str, topic_id: str | None = None, course_work_states: str | None = None, order_by: str | None = None, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_coursework(course_id, topic_id, course_work_states, order_by, page_size, page_token)


@mcp.tool
async def get_coursework(course_id: str, coursework_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_coursework(course_id, coursework_id)


@mcp.tool
async def create_coursework(course_id: str, title: str, workType: str, session_id: str, description: str | None = None, state: str | None = None, maxPoints: float | None = None, topicId: str | None = None, dueDate: Dict[str, Any] | None = None, dueTime: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.create_coursework(course_id, title, workType, description, state, maxPoints, topicId, dueDate, dueTime)


@mcp.tool
async def update_coursework(course_id: str, coursework_id: str, session_id: str, title: str | None = None, description: str | None = None, state: str | None = None, maxPoints: float | None = None, topicId: str | None = None, dueDate: Dict[str, Any] | None = None, dueTime: Dict[str, Any] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.update_coursework(course_id, coursework_id, title, description, state, maxPoints, topicId, dueDate, dueTime)


@mcp.tool
async def delete_coursework(course_id: str, coursework_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.delete_coursework(course_id, coursework_id)


@mcp.tool
async def list_topics(course_id: str, session_id: str, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_topics(course_id, page_size, page_token)


@mcp.tool
async def get_topic(course_id: str, topic_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_topic(course_id, topic_id)


@mcp.tool
async def create_topic(course_id: str, name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.create_topic(course_id, name)


@mcp.tool
async def update_topic(course_id: str, topic_id: str, session_id: str, name: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.update_topic(course_id, topic_id, name)


@mcp.tool
async def delete_topic(course_id: str, topic_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.delete_topic(course_id, topic_id)


@mcp.tool
async def list_submissions(course_id: str, coursework_id: str, session_id: str, states: str | None = None, late: bool | None = None, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_submissions(course_id, coursework_id, states, late, page_size, page_token)


@mcp.tool
async def get_submission(course_id: str, coursework_id: str, submission_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_submission(course_id, coursework_id, submission_id)


@mcp.tool
async def grade_submission(course_id: str, coursework_id: str, submission_id: str, session_id: str, assignedGrade: float | None = None, draftGrade: float | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.grade_submission(course_id, coursework_id, submission_id, assignedGrade, draftGrade)


@mcp.tool
async def return_submission(course_id: str, coursework_id: str, submission_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.return_submission(course_id, coursework_id, submission_id)


@mcp.tool
async def reclaim_submission(course_id: str, coursework_id: str, submission_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.reclaim_submission(course_id, coursework_id, submission_id)


@mcp.tool
async def turn_in_submission(course_id: str, coursework_id: str, submission_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.turn_in_submission(course_id, coursework_id, submission_id)


@mcp.tool
async def modify_submission_attachments(course_id: str, coursework_id: str, submission_id: str, session_id: str, addAttachments: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.modify_submission_attachments(course_id, coursework_id, submission_id, addAttachments)


@mcp.tool
async def list_students(course_id: str, session_id: str, page_size: int = 30, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_students(course_id, page_size, page_token)


@mcp.tool
async def get_student(course_id: str, user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_student(course_id, user_id)


@mcp.tool
async def invite_student(course_id: str, emailAddress: str, session_id: str, fullName: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.invite_student(course_id, emailAddress, fullName)


@mcp.tool
async def remove_student(course_id: str, user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.remove_student(course_id, user_id)


@mcp.tool
async def list_teachers(course_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_teachers(course_id)


@mcp.tool
async def get_teacher(course_id: str, user_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_teacher(course_id, user_id)


@mcp.tool
async def list_announcements(course_id: str, session_id: str, announcement_states: str | None = None, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_announcements(course_id, announcement_states, page_size, page_token)


@mcp.tool
async def get_announcement(course_id: str, announcement_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_announcement(course_id, announcement_id)


@mcp.tool
async def create_announcement(course_id: str, text: str, session_id: str, state: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.create_announcement(course_id, text, state)


@mcp.tool
async def update_announcement(course_id: str, announcement_id: str, session_id: str, text: str | None = None, state: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.update_announcement(course_id, announcement_id, text, state)


@mcp.tool
async def delete_announcement(course_id: str, announcement_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.delete_announcement(course_id, announcement_id)


@mcp.tool
async def list_materials(course_id: str, session_id: str, page_size: int = 20, page_token: int = 0):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.list_materials(course_id, page_size, page_token)


@mcp.tool
async def get_material(course_id: str, material_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.get_material(course_id, material_id)


@mcp.tool
async def create_material(course_id: str, title: str, session_id: str, description: str | None = None, topicId: str | None = None, materials: List[Dict[str, Any]] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.google_classroom_session.create_material(course_id, title, description, topicId, materials)
