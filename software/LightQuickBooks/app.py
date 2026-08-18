from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightQuickBooksSession
except ImportError:
    from software.LightQuickBooks.session import LightQuickBooksSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightQuickBooks")

session_dict: Dict[str, LightQuickBooksSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None, fixture: str | None = None):
	session = LightQuickBooksSession(os_cfg=os_cfg, seed=seed, fixture=fixture)
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
        "output": session.quickbooks_session.get_session_dict(),
    }


# --- Company / Documents ---

@mcp.tool
async def get_company_info(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_company_info()


@mcp.tool
async def get_company_raw(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_company_raw()


@mcp.tool
async def get_bill_payments(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_bill_payments()


@mcp.tool
async def get_corporate_expense_ledger(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_corporate_expense_ledger()


@mcp.tool
async def get_reimbursement_policy(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_reimbursement_policy()


@mcp.tool
async def get_break_even_analysis(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_break_even_analysis()


# --- Customers ---

@mcp.tool
async def get_customer(customer_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_customer(customer_id)


@mcp.tool
async def create_customer(session_id: str, DisplayName: str = "", GivenName: str | None = None, FamilyName: str | None = None, CompanyName: str | None = None, PrimaryEmailAddr: Dict[str, str] | None = None, PrimaryPhone: Dict[str, str] | None = None, BillAddr: Dict[str, str] | None = None, Notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_customer(DisplayName, GivenName, FamilyName, CompanyName, PrimaryEmailAddr, PrimaryPhone, BillAddr, Notes)


@mcp.tool
async def update_customer(customer_id: str, session_id: str, DisplayName: str | None = None, GivenName: str | None = None, FamilyName: str | None = None, CompanyName: str | None = None, PrimaryEmailAddr: Dict[str, str] | None = None, PrimaryPhone: Dict[str, str] | None = None, BillAddr: Dict[str, str] | None = None, Active: bool | None = None, Notes: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.update_customer(customer_id, DisplayName, GivenName, FamilyName, CompanyName, PrimaryEmailAddr, PrimaryPhone, BillAddr, Active, Notes)


# --- Vendors ---

@mcp.tool
async def get_vendor(vendor_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_vendor(vendor_id)


@mcp.tool
async def create_vendor(session_id: str, DisplayName: str = "", CompanyName: str | None = None, PrimaryEmailAddr: Dict[str, str] | None = None, PrimaryPhone: Dict[str, str] | None = None, BillAddr: Dict[str, str] | None = None, AcctNum: str | None = None, Vendor1099: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_vendor(DisplayName, CompanyName, PrimaryEmailAddr, PrimaryPhone, BillAddr, AcctNum, Vendor1099)


@mcp.tool
async def update_vendor(vendor_id: str, session_id: str, DisplayName: str | None = None, CompanyName: str | None = None, PrimaryEmailAddr: Dict[str, str] | None = None, PrimaryPhone: Dict[str, str] | None = None, BillAddr: Dict[str, str] | None = None, Active: bool | None = None, AcctNum: str | None = None, Vendor1099: bool | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.update_vendor(vendor_id, DisplayName, CompanyName, PrimaryEmailAddr, PrimaryPhone, BillAddr, Active, AcctNum, Vendor1099)


# --- Items ---

@mcp.tool
async def get_item(item_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_item(item_id)


@mcp.tool
async def create_item(session_id: str, Name: str = "", Description: str | None = None, Type: str = "Service", UnitPrice: float = 0, IncomeAccountRef: Dict[str, str] | None = None, Taxable: bool = False):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_item(Name, Description, Type, UnitPrice, IncomeAccountRef, Taxable)


@mcp.tool
async def update_item(item_id: str, session_id: str, Name: str | None = None, Description: str | None = None, UnitPrice: float | None = None, Active: bool | None = None, Taxable: bool | None = None, IncomeAccountRef: Dict[str, str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.update_item(item_id, Name, Description, UnitPrice, Active, Taxable, IncomeAccountRef)


# --- Accounts ---

@mcp.tool
async def get_account(account_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_account(account_id)


# --- Invoices ---

@mcp.tool
async def get_invoice(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_invoice(invoice_id)


@mcp.tool
async def get_invoice_pdf(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_invoice_pdf(invoice_id)


@mcp.tool
async def create_invoice(session_id: str, CustomerRef: Dict[str, str] | None = None, Line: List[Dict[str, Any]] | None = None, TxnDate: str | None = None, DueDate: str | None = None, BillEmail: Dict[str, str] | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_invoice(CustomerRef, Line, TxnDate, DueDate, BillEmail)


@mcp.tool
async def update_invoice(invoice_id: str, session_id: str, CustomerRef: Dict[str, str] | None = None, Line: List[Dict[str, Any]] | None = None, DueDate: str | None = None, BillEmail: Dict[str, str] | None = None, PrintStatus: str | None = None, EmailStatus: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.update_invoice(invoice_id, CustomerRef, Line, DueDate, BillEmail, PrintStatus, EmailStatus)


@mcp.tool
async def void_invoice(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.void_invoice(invoice_id)


@mcp.tool
async def send_invoice(invoice_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.send_invoice(invoice_id)


# --- Bills ---

@mcp.tool
async def get_bill(bill_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_bill(bill_id)


@mcp.tool
async def create_bill(session_id: str, VendorRef: Dict[str, str] | None = None, Line: List[Dict[str, Any]] | None = None, TxnDate: str | None = None, DueDate: str | None = None, DocNumber: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_bill(VendorRef, Line, TxnDate, DueDate, DocNumber)


@mcp.tool
async def pay_bill(bill_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.pay_bill(bill_id)


# --- Payments ---

@mcp.tool
async def get_payment(payment_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_payment(payment_id)


@mcp.tool
async def create_payment(session_id: str, CustomerRef: Dict[str, str] | None = None, TotalAmt: float = 0, Line: List[Dict[str, Any]] | None = None, TxnDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_payment(CustomerRef, TotalAmt, Line, TxnDate)


# --- Estimates ---

@mcp.tool
async def get_estimate(estimate_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_estimate(estimate_id)


@mcp.tool
async def create_estimate(session_id: str, CustomerRef: Dict[str, str] | None = None, Line: List[Dict[str, Any]] | None = None, TxnDate: str | None = None, ExpirationDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_estimate(CustomerRef, Line, TxnDate, ExpirationDate)


@mcp.tool
async def convert_estimate_to_invoice(estimate_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.convert_estimate_to_invoice(estimate_id)


# --- Expenses (Purchases) ---

@mcp.tool
async def get_expense(expense_id: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.get_expense(expense_id)


@mcp.tool
async def create_expense(session_id: str, AccountRef: Dict[str, str] | None = None, Line: List[Dict[str, Any]] | None = None, PaymentType: str = "CreditCard", TxnDate: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.create_expense(AccountRef, Line, PaymentType, TxnDate)


# --- Query ---

@mcp.tool
async def execute_query(query: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.execute_query(query)


# --- Reports ---

@mcp.tool
async def profit_and_loss(session_id: str, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.profit_and_loss(start_date, end_date)


@mcp.tool
async def balance_sheet(session_id: str, start_date: str | None = None, end_date: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.balance_sheet(start_date, end_date)


@mcp.tool
async def accounts_receivable_aging(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.accounts_receivable_aging()


@mcp.tool
async def accounts_payable_aging(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.quickbooks_session.accounts_payable_aging()
