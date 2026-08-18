from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightGustoSession
except ImportError:
    from software.LightGusto.session import LightGustoSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightGusto")

session_dict: Dict[str, LightGustoSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightGustoSession(os_cfg=os_cfg, seed=seed)
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
        "output": session.gusto_session.get_session_dict(),
    }


@mcp.tool
async def get_company(company_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.get_company(company_id)


@mcp.tool
async def list_company_employees(company_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.list_company_employees(company_id)


@mcp.tool
async def get_employee(employee_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.get_employee(employee_id)


@mcp.tool
async def list_company_payrolls(company_id: str, session_id: str, processed: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.list_company_payrolls(company_id, processed)


@mcp.tool
async def get_payroll(payroll_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.get_payroll(payroll_id)


@mcp.tool
async def create_payroll(company_id: str, pay_period_start: str, pay_period_end: str, session_id: str, check_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.create_payroll(company_id, pay_period_start, pay_period_end, check_date)


@mcp.tool
async def submit_payroll(payroll_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.submit_payroll(payroll_id)


@mcp.tool
async def list_company_contractors(company_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.gusto_session.list_company_contractors(company_id)
