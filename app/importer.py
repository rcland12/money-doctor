"""Bring ingest results into the database: transactions, statement balances,
and savings balances. Safe to run repeatedly."""

import hashlib
from datetime import date, timedelta

from sqlalchemy import select

from ingest import rules
from ingest.store import load_docs
from ingest.summarize import all_transactions

from .models import Debt, DebtBalance, SavingsGoal, Session, Txn

DEBT_KINDS = {"credit_card", "auto_loan", "personal_loan", "installment"}


def _ref(account: str, t) -> str:
    if t.reference:
        return f"{account}:{t.reference}"
    digest = hashlib.sha1(f"{t.date}|{t.amount}|{t.description}".encode()).hexdigest()[:16]
    return f"{account}:{digest}"


def run() -> dict:
    rules.personal_rules.cache_clear()
    rules.overrides.cache_clear()
    docs = load_docs()
    stmts = [d.statement for _, d, _ in docs if d.statement]
    added = updated = matched = 0
    with Session.begin() as s:
        known = {t.ref: t for t in s.scalars(select(Txn).where(Txn.source == "import"))}
        # Rows bank sync already brought in: a CSV covering the same days mustn't add them again.
        synced: dict[str, list[Txn]] = {}
        for t in known.values():
            if (t.ref or "").startswith("sfin:"):
                synced.setdefault(t.account, []).append(t)
        claimed: set[int] = set()
        new: list[Txn] = []
        for st, t, category in all_transactions(stmts):
            account = f"{st.account_kind}_{st.account_last4}"
            ref = _ref(account, t)
            row = known.get(ref)
            if row:
                if row.category != category:  # rules were edited
                    row.category = category
                    updated += 1
                continue
            twin = next((x for x in synced.get(account, []) if x.id not in claimed and abs(x.amount - t.amount) < 0.005
                         and abs((x.date - _d(t.date)).days) <= 3), None)
            if twin:
                claimed.add(twin.id)
                continue
            row = Txn(date=_d(t.date), amount=t.amount,
                      description=t.description, category=category, account=account, source="import", ref=ref)
            s.add(row)
            new.append(row)
            known[ref] = row
            added += 1
        s.flush()
        # Match against every recent bank row nothing is matched to yet, not just
        # new ones, so a logged entry freed up by a correction still finds its row.
        taken = set(s.scalars(select(Txn.superseded_by).where(Txn.superseded_by.is_not(None))))
        recent = s.scalars(select(Txn).where(Txn.source == "import", Txn.date >= date.today() - timedelta(days=120))).all()
        matched = _reconcile(s, [t for t in recent if t.id not in taken])

        # Statement balances -> debt history; savings balance -> goal
        debts = {d.last4: d for d in s.scalars(select(Debt)) if d.last4}
        for st in stmts:
            if st.closing_balance is None or not st.period_end:
                continue
            end = _d(st.period_end)
            if st.account_kind in DEBT_KINDS and st.account_last4 in debts:
                key = debts[st.account_last4].key
                if not s.scalar(select(DebtBalance).where(DebtBalance.debt_key == key, DebtBalance.as_of == end)):
                    s.add(DebtBalance(debt_key=key, as_of=end, balance=st.closing_balance, source="statement"))
            for goal in s.scalars(select(SavingsGoal).where(SavingsGoal.account == f"{st.account_kind}_{st.account_last4}")):
                goal.balance = st.closing_balance
    return {"added": added, "recategorized": updated, "matched_to_logged": matched}


def _d(value):
    from datetime import date
    return date.fromisoformat(value) if isinstance(value, str) else value


def _reconcile(s, new: list[Txn]) -> int:
    """A purchase logged from the phone and the same purchase arriving from the
    bank become one: the bank row wins, and keeps the logged line and note."""
    matched = 0
    pending = [t for t in s.scalars(select(Txn).where(Txn.source.in_(["shortcut", "manual", "email"]), Txn.superseded_by.is_(None)))
               if t not in new]
    for row in sorted(new, key=lambda r: r.date):
        for logged in pending:
            # A payment marked to a card only matches that card's row.
            if logged.account and logged.account.startswith("credit_card_") and logged.category == "debt_payment" and row.account != logged.account:
                continue
            if abs(logged.amount - row.amount) < 0.01 and timedelta(days=-1) <= row.date - logged.date <= timedelta(days=5):
                logged.superseded_by = row.id
                row.line_key = row.line_key or logged.line_key
                row.note = row.note or logged.note
                pending.remove(logged)
                matched += 1
                break
    return matched
