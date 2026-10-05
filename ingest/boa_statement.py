"""Bank of America credit card statement PDFs: the account summary only.

Transactions come from the CSV exports; the statement is where the balance,
minimum payment, due date, credit line and APRs live. The layout is fixed, so
this reads it exactly, with no model: a statement shared from the phone
updates the balances the moment it's uploaded."""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from .schemas import AccountStatement, CardTerms

MARKER = "Account Summary/Payment Information"
MONEY = r"\$?(-?[\d,]+\.\d\d)"


def _text(pdf: Path, pages: int = 5) -> str:
    with pdfplumber.open(pdf) as doc:
        return "\n".join((p.extract_text() or "") for p in doc.pages[:pages])


def is_statement(pdf: Path) -> bool:
    try:
        with pdfplumber.open(pdf) as doc:
            return MARKER in (doc.pages[0].extract_text() or "")
    except Exception:
        return False


def _money(text: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"\s*" + MONEY, text)
    return float(m.group(1).replace(",", "")) if m else None


def _pct(text: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"\s+([\d.]+)%", text)
    return float(m.group(1)) if m else None


def _date(s: str) -> str:
    return datetime.strptime(s, "%m/%d/%Y").date().isoformat()


def parse(pdf: Path) -> AccountStatement:
    text = _text(pdf)
    acct = re.search(r"Account#\s*([\d ]{8,30})", text)
    last4 = re.sub(r"\D", "", acct.group(1))[-4:] if acct else None
    period = re.search(r"([A-Z][a-z]+ \d{1,2}) - ([A-Z][a-z]+ \d{1,2}), (\d{4})", text)
    start = end = None
    if period:
        end_d = datetime.strptime(f"{period.group(2)} {period.group(3)}", "%B %d %Y").date()
        start_d = datetime.strptime(f"{period.group(1)} {period.group(3)}", "%B %d %Y").date()
        if start_d > end_d:  # a December-January cycle
            start_d = start_d.replace(year=start_d.year - 1)
        start, end = start_d.isoformat(), end_d.isoformat()
    due = re.search(r"Payment Due Date\s*(\d\d/\d\d/\d{4})", text)
    return AccountStatement(
        institution="Bank of America",
        account_kind="credit_card",
        account_last4=last4,
        period_start=start,
        period_end=end,
        opening_balance=_money(text, "Previous Balance"),
        closing_balance=_money(text, "New Balance Total"),
        transactions=[],
        card=CardTerms(
            credit_limit=_money(text, "Total Credit Line"),
            minimum_payment_due=_money(text, "Total Minimum Payment Due"),
            payment_due_date=_date(due.group(1)) if due else None,
            purchase_apr=_pct(text, "Purchases"),
            cash_advance_apr=_pct(text, "Bank Cash Advances"),
            interest_charged=_money(text, "Interest Charged"),
            fees_charged=_money(text, "Fees Charged"),
            promos=[],
        ),
    )
