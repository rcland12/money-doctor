"""Bank of America CSV exports. Two formats:

Checking/savings (custom date range, with a running balance):
    Description,,Summary Amt.
    Beginning balance as of 03/01/2025,,"1,038.62"
    ...
    Date,Description,Amount,Running Bal.

Credit card (one statement month per file, no balances):
    Posted Date,Reference Number,Payee,Address,Amount

The account type and last 4 digits come from the file or folder name, e.g.
checking_1234_*.csv or credit_card_4321/May2026_4321.csv."""

import csv
import io
import re
from datetime import datetime
from pathlib import Path

from .schemas import AccountStatement, Transaction

NAME = re.compile(r"(checking|savings|credit_card)_(\d{4})", re.IGNORECASE)


def _iso(d: str) -> str:
    return datetime.strptime(d.strip(), "%m/%d/%Y").date().isoformat()


def _amount(s: str) -> float:
    return float(s.replace(",", "").replace('"', "").strip())


def _account(path: Path) -> tuple[str, str]:
    m = NAME.search(str(path))
    if not m:
        raise ValueError(f"{path}: name must contain checking_1234, savings_1234 or credit_card_1234")
    return m.group(1).lower(), m.group(2)


def _strip_address(payee: str, address: str) -> str:
    """'SHELL OIL 123 SPRINGFIELDIL' + 'SPRINGFIELD IL' -> 'SHELL OIL 123'."""
    compact_addr = re.sub(r"\s+", "", address)
    if not compact_addr:
        return payee.strip()
    chars, remaining = list(payee.rstrip()), len(compact_addr)
    if not re.sub(r"\s+", "", payee).endswith(compact_addr):
        return payee.strip()
    while remaining and chars:
        if not chars.pop().isspace():
            remaining -= 1
    return "".join(chars).strip() or payee.strip()


def is_boa_csv(path: Path) -> bool:
    head = path.read_text(errors="replace")[:80]
    return head.startswith("Description,,Summary Amt.") or head.startswith("Posted Date,Reference Number,Payee")


def parse(path: Path) -> tuple[AccountStatement, list[str]]:
    """Return the statement and any balance problems found while parsing."""
    kind, last4 = _account(path)
    text = path.read_text()
    problems: list[str] = []
    txns: list[Transaction] = []
    opening = closing = period_start = period_end = None

    if text.startswith("Description,,Summary Amt."):
        summary, _, body = text.partition("\n\n")
        for row in csv.reader(io.StringIO(summary)):
            if row and row[0].startswith("Beginning balance"):
                opening = _amount(row[2])
                period_start = _iso(row[0].rsplit(" ", 1)[-1])
            elif row and row[0].startswith("Ending balance"):
                closing = _amount(row[2])
                period_end = _iso(row[0].rsplit(" ", 1)[-1])
        running = opening
        for row in csv.DictReader(io.StringIO(body.strip())):
            if not row["Amount"].strip():
                continue  # the "Beginning balance" line
            amount = _amount(row["Amount"])
            running = round(running + amount, 2) if running is not None else None
            if running is not None and row["Running Bal."].strip() and abs(running - _amount(row["Running Bal."])) > 0.01:
                problems.append(f"running balance off on {row['Date']} {row['Description'][:30]}")
                running = _amount(row["Running Bal."])
            # The running balance makes two identical same-day charges distinct,
            # and matches across overlapping date-range downloads.
            ref = f"{row['Date']}|{amount}|bal:{row['Running Bal.'].strip()}" if row["Running Bal."].strip() else None
            txns.append(Transaction(date=_iso(row["Date"]), reference=ref, description=row["Description"].strip(),
                                    amount=amount, category="other", looks_recurring=False))
    else:
        for row in csv.DictReader(io.StringIO(text)):
            txns.append(Transaction(
                date=_iso(row["Posted Date"]),
                reference=row["Reference Number"].strip() or None,
                description=_strip_address(row["Payee"], row["Address"]),
                amount=_amount(row["Amount"]),
                category="other",
                looks_recurring=False,
            ))

    dates = sorted(t.date for t in txns)
    statement = AccountStatement(
        institution="Bank of America",
        account_kind=kind,
        account_last4=last4,
        period_start=period_start or (dates[0] if dates else None),
        period_end=period_end or (dates[-1] if dates else None),
        opening_balance=opening,
        closing_balance=closing,
        transactions=txns,
    )
    return statement, problems[:5]
