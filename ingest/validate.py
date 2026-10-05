"""Arithmetic checks that catch extraction mistakes without a human re-reading
every PDF: pay lines must add up to gross and net, and transactions must move
the opening balance to the closing balance."""

from .schemas import DocumentExtraction

TOLERANCE = 0.05


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def check(doc: DocumentExtraction) -> list[str]:
    problems = []
    if doc.pay:
        p = doc.pay
        earned = sum(e.amount for e in p.earnings)
        deducted = sum(d.amount for d in p.deductions)
        if p.earnings and not _close(earned, p.gross_pay):
            problems.append(f"earnings sum {earned:.2f} != gross {p.gross_pay:.2f}")
        if not _close(p.gross_pay - deducted, p.net_pay):
            problems.append(f"gross {p.gross_pay:.2f} - deductions {deducted:.2f} != net {p.net_pay:.2f}")
    if doc.statement:
        s = doc.statement
        # Loan payments split into principal and interest, so only deposit
        # accounts and cards reconcile by simple addition.
        balanced = s.account_kind in ("checking", "savings", "credit_card")
        # A summary-only statement (transactions come from CSVs) has nothing to add up.
        if balanced and s.transactions and s.opening_balance is not None and s.closing_balance is not None:
            flow = sum(t.amount for t in s.transactions)
            owed = s.account_kind == "credit_card"
            expected = s.opening_balance - flow if owed else s.opening_balance + flow
            if not _close(expected, s.closing_balance):
                problems.append(
                    f"opening {s.opening_balance:.2f} with transactions gives {expected:.2f}, "
                    f"statement says closing {s.closing_balance:.2f}"
                )
    if doc.doc_type == "other":
        problems.append("not recognized as a pay or account statement")
    return problems
