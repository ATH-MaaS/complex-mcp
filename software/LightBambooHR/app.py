from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightBambooHRSession
except ImportError:
    from software.LightBambooHR.session import LightBambooHRSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightBambooHR")

session_dict: Dict[str, LightBambooHRSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightBambooHRSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.bamboohr_session.get_session_dict(),
    }


@mcp.tool
async def get_company(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.get_company()


@mcp.tool
async def employees_directory(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.employees_directory()


@mcp.tool
async def get_employee(employee_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.get_employee(employee_id)


@mcp.tool
async def create_employee(firstName: str, lastName: str, session_id: str, workEmail: str | None = None, department: str | None = None, jobTitle: str | None = None, location: str | None = None, hireDate: str | None = None, supervisorId: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.create_employee(firstName, lastName, workEmail, department, jobTitle, location, hireDate, supervisorId)


@mcp.tool
async def list_time_off_requests(session_id: str, status: str | None = None, employeeId: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.list_time_off_requests(status, employeeId)


@mcp.tool
async def create_time_off_request(employeeId: str, start: str, end: str, session_id: str, type: str = "Vacation", amount: int = 1, unit: str = "days", notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.create_time_off_request(employeeId, start, end, type, amount, unit, notes)


@mcp.tool
async def update_time_off_status(request_id: str, status: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.update_time_off_status(request_id, status)


@mcp.tool
async def whos_out(session_id: str, start: str | None = None, end: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.whos_out(start, end)


@mcp.tool
async def get_report(report_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.bamboohr_session.get_report(report_id)
