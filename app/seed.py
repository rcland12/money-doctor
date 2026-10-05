"""Load the budget file into the database. The file is the source of truth for
lines, debts, events and settings; transactions and balance history are kept."""

from datetime import date

import yaml
from sqlalchemy import delete, select

from . import config
from .models import DebtBalance, Debt, Event, Line, SavingsGoal, Session, Setting


def _month(v) -> str | None:
    if v is None:
        return None
    return v.strftime("%Y-%m") if isinstance(v, date) else str(v)[:7]


def load_budget(path=config.BUDGET_FILE) -> dict:
    if not path.exists():
        example = config.ROOT / "config" / "budget.example.yaml"
        path = example
    return yaml.safe_load(path.read_text()) or {}


def seed(path=config.BUDGET_FILE) -> dict:
    b = load_budget(path)
    with Session.begin() as s:
        s.execute(delete(Line))
        for i, ln in enumerate(b.get("lines", [])):
            s.add(Line(
                key=ln["key"], name=ln["name"], group=ln.get("group", "Other"), kind=ln.get("kind", "variable"),
                amount=float(ln.get("amount", 0)), due_day=ln.get("due_day"), due_amount=ln.get("due_amount"), pay_from=ln.get("pay_from"),
                from_month=_month(ln.get("from")), until_month=_month(ln.get("until")),
                tracks=ln.get("tracks", []), offsets=ln.get("offsets", []), match=[m.upper() for m in ln.get("match", [])],
                debt_key=ln.get("debt"), shortcut=ln.get("shortcut"), private=bool(ln.get("private")),
                note=ln.get("note"), start_balance=float(ln.get("start_balance", 0)), sort=i,
            ))
        keep = set()
        for d in b.get("debts", []):
            keep.add(d["key"])
            debt = s.get(Debt, d["key"]) or Debt(key=d["key"])
            debt.name, debt.kind, debt.last4 = d["name"], d.get("kind", "other"), d.get("last4")
            debt.apr, debt.minimum, debt.due_day = float(d.get("apr", 0)), float(d.get("minimum", 0)), d.get("due_day")
            debt.limit, debt.payoff_order = d.get("limit"), d.get("payoff_order")
            s.add(debt)
            s.flush()
            as_of = d.get("as_of") or date.today()
            exists = s.scalar(select(DebtBalance).where(DebtBalance.debt_key == d["key"], DebtBalance.as_of == as_of))
            if not exists and d.get("balance") is not None:
                s.add(DebtBalance(debt_key=d["key"], as_of=as_of, balance=float(d["balance"]), source="budget"))
        for debt in s.scalars(select(Debt)).all():
            if debt.key not in keep:
                s.delete(debt)
        s.execute(delete(Event))
        for e in b.get("events", []):
            s.add(Event(date=e["date"], end=e.get("end"), name=e["name"], amount=e.get("amount"),
                        line_key=e.get("line"), kind=e.get("kind", "event"), note=e.get("note")))
        s.execute(delete(SavingsGoal))
        for g in b.get("savings_goals", []):
            s.add(SavingsGoal(key=g["key"], name=g["name"], target=float(g["target"]), balance=float(g.get("balance", 0)),
                              account=g.get("account")))
        for key in ("owner", "timezone", "income", "plan", "digest", "wallet_cards", "paid_with", "card_numbers", "small_purchases", "assets", "cash", "cash_bills", "recurring", "autopay"):
            s.merge(Setting(key=key, value=_jsonable(b.get(key))))
    return b


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, date):
        return v.isoformat()
    return v
