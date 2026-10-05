"""Budget math: where each line stands this month, what's safe to spend today,
what's due, what each paycheck should do, and when the debt is gone.

Everything is computed from the database on request; nothing here writes."""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import yaml
from sqlalchemy import select

from . import config
from .models import BillPaid, Debt, DebtBalance, Event, Line, SavingsGoal, Session, Setting, Txn

VARIABLE, BILL, FUND, SAVINGS = "variable", "bill", "fund", "savings"


def month_of(d: date) -> str:
    return d.strftime("%Y-%m")


def month_bounds(month: str) -> tuple[date, date]:
    y, m = map(int, month.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def next_month(month: str) -> str:
    first, last = month_bounds(month)
    return month_of(last + timedelta(days=1))


def months_between(a: str, b: str) -> list[str]:
    out, m = [], a
    while m <= b:
        out.append(m)
        m = next_month(m)
    return out


@dataclass
class Ctx:
    """Everything loaded once per request."""

    today: date
    lines: list[Line]
    debts: list[Debt]
    balances: dict[str, list[DebtBalance]]
    txns: list[Txn]
    events: list[Event]
    goals: list[SavingsGoal]
    paid_marks: set[tuple[str, str]]
    settings: dict
    by_key: dict[str, Line] = field(default_factory=dict)

    @property
    def income(self) -> dict:
        return self.settings.get("income") or {}

    @property
    def plan(self) -> dict:
        return self.settings.get("plan") or {}


def load(today: date | None = None) -> Ctx:
    today = today or date.today()
    with Session() as s:
        lines = list(s.scalars(select(Line).order_by(Line.sort)))
        balances: dict[str, list[DebtBalance]] = defaultdict(list)
        for b in s.scalars(select(DebtBalance).order_by(DebtBalance.as_of)):
            balances[b.debt_key].append(b)
        ctx = Ctx(
            today=today,
            lines=lines,
            debts=list(s.scalars(select(Debt))),
            balances=balances,
            txns=list(s.scalars(select(Txn).where(Txn.superseded_by.is_(None)).order_by(Txn.date))),
            events=list(s.scalars(select(Event).order_by(Event.date))),
            goals=list(s.scalars(select(SavingsGoal))),
            paid_marks={(p.line_key, p.month) for p in s.scalars(select(BillPaid))},
            settings={row.key: row.value for row in s.scalars(select(Setting))},
        )
    ctx.by_key = {ln.key: ln for ln in lines}
    return ctx


# ---------------------------------------------------------------- paydays
def paydays(ctx: Ctx, start: date, end: date) -> list[date]:
    anchor = date.fromisoformat(str(ctx.income.get("pay_anchor", start.isoformat())))
    step = int(ctx.income.get("pay_every_days", 14))
    d = anchor + timedelta(days=((start - anchor).days // step) * step)
    out = []
    while d <= end:
        if d >= start:
            out.append(d)
        d += timedelta(days=step)
    return out


def paycheck_amount(ctx: Ctx) -> float:
    return float(ctx.income.get("paycheck_net", 0))


# ---------------------------------------------------------------- lines
def resolve_line(ctx: Ctx, t: Txn) -> tuple[str | None, bool]:
    """(line key, is_offset). Hand-set lines win, then `match`, then `tracks`,
    then `small_purchases` can move a small one (energy drinks at a gas station)."""
    if t.line_key:
        return t.line_key, False
    key, offset = _resolve(ctx, t)
    for rule in ctx.settings.get("small_purchases") or []:
        if key == rule.get("line") and t.amount < 0 and -t.amount < float(rule.get("under", 0)):
            return rule.get("becomes"), False
    return key, offset


def _resolve(ctx: Ctx, t: Txn) -> tuple[str | None, bool]:
    month, desc = month_of(t.date), t.description.upper()
    active = [ln for ln in ctx.lines if ln.active(month)]
    for ln in active + [ln for ln in ctx.lines if not ln.active(month)]:
        if any(m in desc for m in ln.match):
            return ln.key, False
    for ln in active:
        if t.category in ln.tracks:
            return ln.key, False
    for ln in active:
        if t.category in ln.offsets:
            return ln.key, True
    return None, False


def cards_extra(ctx: Ctx, month: str) -> float:
    """Whatever the two budgeted paychecks don't assign goes to the top debt."""
    budget = paycheck_amount(ctx) * int(ctx.income.get("budget_paychecks", 2))
    return round(budget - sum(ln.amount for ln in ctx.lines if ln.active(month)), 2)


def line_status(ctx: Ctx, month: str) -> list[dict]:
    first, last = month_bounds(month)
    plan_start = str(ctx.plan.get("start") or month)
    spent: dict[str, float] = defaultdict(float)       # this month, net of offsets
    gross_out: dict[str, float] = defaultdict(float)   # this month, payments only (bill detection)
    fund_spent: dict[str, float] = defaultdict(float)  # since the plan started
    items: dict[str, list[Txn]] = defaultdict(list)
    for t in ctx.txns:
        key, _ = resolve_line(ctx, t)
        if not key:
            continue
        if first <= t.date <= last:
            spent[key] -= t.amount
            items[key].append(t)
            if t.amount < 0:
                gross_out[key] -= t.amount
        if month_of(t.date) >= plan_start and t.date <= last:
            fund_spent[key] -= t.amount

    in_month = min(max(ctx.today, first), last)
    elapsed = (in_month - first).days + 1
    days = (last - first).days + 1
    out = []
    for ln in ctx.lines:
        if not ln.active(month):
            continue
        row = {
            "key": ln.key, "name": ln.name, "group": ln.group, "kind": ln.kind, "target": ln.amount,
            "spent": round(spent[ln.key], 2), "remaining": round(ln.amount - spent[ln.key], 2),
            "private": ln.private, "note": ln.note, "count": len(items[ln.key]),
        }
        if ln.kind == VARIABLE:
            row["expected_by_now"] = round(ln.amount * elapsed / days, 2)
            row["pace"] = "over" if spent[ln.key] > ln.amount else ("ahead" if spent[ln.key] > row["expected_by_now"] * 1.1 else "ok")
        if ln.kind == BILL and ln.due_day:
            due = date(first.year, first.month, min(ln.due_day, days))
            paid = (ln.key, month) in ctx.paid_marks or gross_out[ln.key] >= 0.9 * ln.amount
            row.update(due=due.isoformat(), paid=paid, pay_from=ln.pay_from, due_amount=ln.due_amount or ln.amount)
        if ln.kind == FUND:
            contributed = sum(ln.amount for m in months_between(max(plan_start, ln.from_month or plan_start), month) if ln.active(m))
            row["balance"] = round(ln.start_balance + contributed - fund_spent[ln.key], 2)
        out.append(row)
    return out


def safe_to_spend(ctx: Ctx, status: list[dict]) -> dict:
    first, last = month_bounds(month_of(ctx.today))
    days_left = (last - ctx.today).days + 1
    lines = []
    for row in status:
        if row["kind"] != VARIABLE or row["target"] <= 0:
            continue
        per_day = max(0.0, row["remaining"]) / days_left
        lines.append({"key": row["key"], "name": row["name"], "remaining": row["remaining"], "per_day": round(per_day, 2)})
    return {"total_per_day": round(sum(x["per_day"] for x in lines), 2), "days_left": days_left, "lines": lines,
            "left_this_month": round(sum(max(0.0, x["remaining"]) for x in lines), 2)}


# ---------------------------------------------------------------- due & events
def due_soon(ctx: Ctx, days: int = 7) -> list[dict]:
    """Bills due in the next `days`. A past-due bill is only called late when the
    bank data already covers its due date, so a data lag isn't mistaken for a miss."""
    end = ctx.today + timedelta(days=days)
    through = freshness(ctx)["bank_data_through"]
    out = []
    for month in sorted({month_of(ctx.today), month_of(end)}):
        for row in line_status(ctx, month):
            if "due" not in row:
                continue
            due = date.fromisoformat(row["due"])
            late = (ctx.today - timedelta(days=5) <= due < ctx.today and not row["paid"]
                    and through is not None and through >= row["due"])
            if ctx.today <= due <= end or late:
                out.append({"date": row["due"], "name": row["name"], "amount": row["due_amount"], "paid": row["paid"],
                            "pay_from": row.get("pay_from"), "key": row["key"], "late": late})
    for e in ctx.events:
        if ctx.today <= e.date <= end and e.kind == "bill":
            out.append({"date": e.date.isoformat(), "name": e.name, "amount": e.amount, "paid": False, "key": None, "late": False})
    return sorted(out, key=lambda x: x["date"])


def upcoming_events(ctx: Ctx, days: int = 45) -> list[dict]:
    end = ctx.today + timedelta(days=days)
    return [{"date": e.date.isoformat(), "end": e.end.isoformat() if e.end else None, "name": e.name,
             "amount": e.amount, "kind": e.kind, "line": e.line_key, "days_away": (e.date - ctx.today).days}
            for e in ctx.events if ctx.today <= e.date <= end and e.kind != "bill"]


# ---------------------------------------------------------------- paychecks
def paycheck_plan(ctx: Ctx, payday: date) -> dict:
    """What to do with one paycheck: pay the bills due before the next payday,
    move this paycheck's fund and savings transfers, and send half of the
    month's extra to the top debt. Checking absorbs the timing differences."""
    month = month_of(payday)
    first, last = month_bounds(month)
    in_month = paydays(ctx, first, last)
    n = in_month.index(payday) + 1 if payday in in_month else 1
    amount = paycheck_amount(ctx)
    budgeted = int(ctx.income.get("budget_paychecks", 2))
    base = {"date": payday.isoformat(), "number": n, "amount": amount}
    if n > budgeted:
        return {**base, "extra_paycheck": True, "bills": [], "transfers": [], "extra": None,
                "rule": third_paycheck_rule(ctx, month)}
    window_end = payday + timedelta(days=int(ctx.income.get("pay_every_days", 14)))
    bills, transfers = [], []
    for ln in ctx.lines:
        if ln.amount <= 0:
            continue
        if ln.kind == BILL and ln.due_day:
            for m in sorted({month_of(payday), month_of(window_end)}):
                f, l = month_bounds(m)
                due = date(f.year, f.month, min(ln.due_day, l.day))
                if payday <= due < window_end and ln.active(m):
                    bills.append({"name": ln.name, "amount": ln.due_amount or ln.amount, "key": ln.key, "due": due.isoformat()})
        elif ln.kind in (FUND, SAVINGS) and ln.pay_from == n and ln.active(month):
            transfers.append({"name": ln.name, "amount": ln.amount, "key": ln.key})
    target = top_debt(ctx)
    extra = {"name": f"Extra to {target.name}" if target else "Extra to savings",
             "amount": round(max(0.0, cards_extra(ctx, month)) / budgeted, 2), "key": "extra"}
    return {**base, "extra_paycheck": False, "bills": sorted(bills, key=lambda b: b["due"]),
            "transfers": transfers, "extra": extra, "until": (window_end - timedelta(days=1)).isoformat()}


def third_paycheck_rule(ctx: Ctx, month: str) -> dict:
    for rule in ctx.plan.get("third_paycheck") or []:
        if str(rule.get("month"))[:7] == month:
            return rule
    return {"month": month, "split": {"cards": 0.5, "life_happens": 0.5}}


# ---------------------------------------------------------------- debt
def current_balance(ctx: Ctx, key: str) -> tuple[float, date | None]:
    hist = ctx.balances.get(key) or []
    return (hist[-1].balance, hist[-1].as_of) if hist else (0.0, None)


def top_debt(ctx: Ctx) -> Debt | None:
    order = [d for d in ctx.debts if d.payoff_order != "last" and current_balance(ctx, d.key)[0] > 0]
    return max(order, key=lambda d: d.apr) if order else None


def projection(ctx: Ctx) -> dict:
    """Month-by-month avalanche on the debts in play, using the budget's money."""
    targets = [d for d in ctx.debts if d.payoff_order != "last"]
    bal = {d.key: current_balance(ctx, d.key)[0] for d in targets}
    apr = {d.key: d.apr / 100 for d in targets}
    min_lines = {ln.debt_key: ln for ln in ctx.lines if ln.debt_key in bal}
    # Balances are as of the latest statements; the month after that is the first
    # one whose payments aren't reflected yet.
    as_of = max((current_balance(ctx, d.key)[1] for d in targets if current_balance(ctx, d.key)[1]), default=ctx.today)
    month = next_month(month_of(as_of))
    series, paid_off, interest = [], {}, 0.0
    step = int(ctx.income.get("pay_every_days", 14))
    for _ in range(120):
        if sum(bal.values()) < 0.01:
            break
        first, last = month_bounds(month)
        cash = sum(ln.amount for ln in min_lines.values() if ln.active(month)) + max(0.0, cards_extra(ctx, month))
        if len(paydays(ctx, first, last)) > int(ctx.income.get("budget_paychecks", 2)):
            rule = third_paycheck_rule(ctx, month)
            extra = paycheck_amount(ctx)
            if "rest" in rule:
                cash += extra - float(rule.get("emergency_fund", 0))
            else:
                cash += extra * float((rule.get("split") or {}).get("cards", 0.5))
        for k in bal:
            i = bal[k] * apr[k] / 12
            bal[k] += i
            interest += i
        # minimums first, then everything else to the highest APR
        left = cash
        for k in bal:
            m = min(bal[k], max(35.0, bal[k] * 0.01 + bal[k] * apr[k] / 12), left)
            bal[k] -= m
            left -= m
        for k in sorted(bal, key=lambda k: -apr[k]):
            x = min(bal[k], left)
            bal[k] -= x
            left -= x
        for k in bal:
            if bal[k] < 0.01 and k not in paid_off:
                paid_off[k] = month
        series.append({"month": month, "total": round(sum(bal.values()), 2), **{k: round(v, 2) for k, v in bal.items()}})
        month = next_month(month)
    done = series[-1]["month"] if series and series[-1]["total"] < 0.01 else None
    target = str(ctx.plan.get("target_payoff") or "")[:7] or None
    return {"series": series, "paid_off": paid_off, "done": done, "interest": round(interest, 2),
            "target": target, "on_track": bool(done and target and done <= target), "step": step}


def debts_summary(ctx: Ctx) -> list[dict]:
    out = []
    for d in ctx.debts:
        bal, as_of = current_balance(ctx, d.key)
        out.append({"key": d.key, "name": d.name, "kind": d.kind, "apr": d.apr, "balance": round(bal, 2),
                    "account": f"credit_card_{d.last4}" if d.kind == "credit_card" and d.last4 else None,
                    "as_of": as_of.isoformat() if as_of else None, "limit": d.limit, "minimum": d.minimum,
                    "used": round(bal / d.limit, 3) if d.limit else None,
                    "history": [{"date": b.as_of.isoformat(), "balance": b.balance} for b in ctx.balances.get(d.key, [])]})
    return out


# ---------------------------------------------------------------- payments
PAYBACK_EXCLUDE = NOT_SPENDING_CATS = {"debt_payment", "transfer_internal", "investing", "income", "reimbursement", "fees_interest"}


def card_accounts(ctx: Ctx) -> dict[str, Debt]:
    """account key (as on transactions) -> the card's debt."""
    return {f"credit_card_{d.last4}": d for d in ctx.debts if d.kind == "credit_card" and d.last4}


def paid_with(ctx: Ctx) -> dict[str, str]:
    """Which account each bill or fund lands on: set in the budget file as
    `paid_with`, otherwise the account that carried most of its dollars lately."""
    explicit = (ctx.settings.get("paid_with") or {})
    weight: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    since = ctx.today - timedelta(days=120)
    for t in ctx.txns:
        if t.date >= since and t.amount < 0 and t.account and t.account != "logged":
            key, _ = resolve_line(ctx, t)
            if key:
                weight[key][t.account] += -t.amount
    out = {}
    for ln in ctx.lines:
        if ln.key in explicit:
            out[ln.key] = explicit[ln.key]
        elif weight[ln.key]:
            out[ln.key] = max(weight[ln.key], key=weight[ln.key].get)
    return out


def card_charges(ctx: Ctx, account: str, start: date, end: date) -> list[Txn]:
    """New spending on a card in [start, end): purchases and refunds, not payments or interest."""
    return [t for t in ctx.txns if t.account == account and start <= t.date < end and t.category not in PAYBACK_EXCLUDE]


def _due(ln: Line, month: str) -> date:
    first, last = month_bounds(month)
    return date(first.year, first.month, min(ln.due_day, last.day))


def payment_schedule(ctx: Ctx, days: int = 14) -> list[dict]:
    """Every payment to make from today through `days` ahead, by date.

    - Each payday, one payment per card: what was charged to it since the last
      payday (so card spending never turns into new debt), plus its minimum if
      that's due before the next payday, plus the plan's extra for the top debt.
    - Bills that come out of checking, on their due dates.
    - Each payday, the fund and savings transfers assigned to it.
    """
    start, end = ctx.today, ctx.today + timedelta(days=days)
    step = int(ctx.income.get("pay_every_days", 14))
    budgeted = int(ctx.income.get("budget_paychecks", 2))
    cards = card_accounts(ctx)
    lands_on = paid_with(ctx)
    card_debt_keys = {d.key for d in cards.values()}
    top = top_debt(ctx)
    # Charges from before the plan started are already in the card balances the
    # payoff plan works down; paybacks only cover spending since then.
    plan_start = month_bounds(str(ctx.plan.get("start") or month_of(start))[:7])[0]
    out: list[dict] = []

    # Each card's ledger since the plan started: what's owed back right now.
    ahead: dict[str, float] = {}
    for account, debt in cards.items():
        ledger = card_ledger(ctx, account, debt, plan_start, top)
        if ledger["due_now"] > 0.5:
            out.append({"date": start.isoformat(), "kind": "card", "name": f"Pay {debt.name} now", "account": account,
                        "key": f"now:{account}:{start.isoformat()}", "amount": ledger["due_now"], "parts": ledger["parts"],
                        "note": "Pays back what's been charged to the card, so it doesn't turn into new debt."})
        ahead[account] = max(0.0, -ledger["due_now"])
        # Card bills that will post soon: pay each back when it does.
        for ln in ctx.lines:
            if ln.kind != "bill" or not ln.due_day or lands_on.get(ln.key) != account:
                continue
            for m in months_between(month_of(start), month_of(end)):
                due = _due(ln, m)
                if start <= due <= end and ln.active(m) and not _posted(ctx, ln.key, due):
                    out.append({"date": due.isoformat(), "kind": "card", "name": f"Pay back {ln.name}", "account": account,
                                "amount": ln.amount, "parts": [], "line": ln.key, "note": f"Charged to {debt.name}; pay it back as soon as it posts."})
        for e in ctx.events:
            if e.amount and e.line_key and lands_on.get(e.line_key) == account and start <= e.date <= end and not _posted(ctx, e.line_key, e.date):
                out.append({"date": e.date.isoformat(), "kind": "card", "name": f"Pay back {e.name}", "account": account,
                            "amount": e.amount, "parts": [], "note": f"Charged to {debt.name}; pay it back as soon as it posts."})

    for payday in paydays(ctx, start, end):
        month = month_of(payday)
        first, last = month_bounds(month)
        n = paydays(ctx, first, last).index(payday) + 1
        prev, nxt = payday - timedelta(days=step), payday + timedelta(days=step)

        if n > budgeted:  # a third paycheck: the plan's rule for it
            rule = third_paycheck_rule(ctx, month)
            amt = paycheck_amount(ctx)
            if rule.get("emergency_fund"):
                ef = float(rule["emergency_fund"])
                out.append({"date": payday.isoformat(), "kind": "transfer", "name": "Emergency fund (third paycheck)", "amount": ef, "parts": []})
                out.append({"date": payday.isoformat(), "kind": "card", "name": f"Pay {top.name}" if top else "Extra to debt",
                            "amount": round(amt - ef, 2), "parts": [{"label": "rest of the third paycheck", "amount": round(amt - ef, 2)}]})
            else:
                share = float((rule.get("split") or {}).get("cards", 0.5))
                out.append({"date": payday.isoformat(), "kind": "card", "name": f"Pay {top.name}" if top else "Extra to debt",
                            "amount": round(amt * share, 2), "parts": [{"label": "half of the third paycheck", "amount": round(amt * share, 2)}]})
                out.append({"date": payday.isoformat(), "kind": "transfer", "name": "Life-happens fund (third paycheck)", "amount": round(amt * (1 - share), 2), "parts": []})
        else:
            for account, debt in cards.items():
                parts = _plan_parts(ctx, debt, payday, n, budgeted, top, plan_start)
                if ahead.get(account, 0) > 0.005 and parts:
                    use = min(ahead[account], sum(x["amount"] for x in parts))
                    ahead[account] -= use
                    parts.append({"label": "already paid early", "amount": -round(use, 2)})
                total = round(sum(x["amount"] for x in parts), 2)
                if total > 0.005:
                    out.append({"date": payday.isoformat(), "kind": "card", "name": f"Pay {debt.name}", "account": account,
                                "key": f"pay:{account}:{payday.isoformat()}", "amount": total, "parts": parts})
            moves = [ln for ln in ctx.lines if ln.kind in (FUND, SAVINGS) and ln.pay_from == n and ln.active(month) and ln.amount > 0]
            for ln in moves:
                out.append({"date": payday.isoformat(), "kind": "transfer", "name": f"Move to {ln.name}", "amount": ln.amount, "parts": [],
                            "key": f"move:{ln.key}:{payday.isoformat()}"})

    # Household bills paid in full (split with roommates): on their dates.
    for cb in ctx.settings.get("cash_bills") or []:
        needles = [m.upper() for m in cb.get("match") or []]
        for m in months_between(month_of(start), month_of(end)):
            f, l = month_bounds(m)
            due = date(f.year, f.month, min(int(cb["day"]), l.day))
            if not start <= due <= end:
                continue
            posted = any(t.amount < 0 and abs((t.date - due).days) <= 10 and any(n in t.description.upper() for n in needles)
                         for t in ctx.txns)
            account = cb.get("paid_with", "")
            if account.startswith("credit_card_"):
                if not posted:
                    card = cards.get(account)
                    out.append({"date": due.isoformat(), "kind": "card", "name": f"Pay back {cb['name']}", "account": account,
                                "amount": float(cb["amount"]), "parts": [], "line": cb["key"],
                                "note": f"Charged to {card.name if card else 'the card'}; pay it back as soon as it posts. " + (cb.get("note") or "")})
            else:
                out.append({"date": due.isoformat(), "kind": "bill", "name": cb["name"], "amount": float(cb["amount"]), "parts": [],
                            "note": cb.get("note"), "key": f"cash:{cb['key']}:{due.isoformat()}", "match": needles, "paid": posted})

    # Bills paid straight from checking, on their due dates
    for ln in ctx.lines:
        if ln.kind != "bill" or not ln.due_day or ln.debt_key in card_debt_keys:
            continue
        if lands_on.get(ln.key, "checking").startswith("credit_card_"):
            continue  # it lands on a card; the card payment covers it
        for m in months_between(month_of(start), month_of(end)):
            due = _due(ln, m)
            if start <= due <= end and ln.active(m):
                out.append({"date": due.isoformat(), "kind": "bill", "name": ln.name, "amount": ln.due_amount or ln.amount,
                            "parts": [], "note": ln.note, "key": ln.key})
    for e in ctx.events:
        if e.kind == "bill" and e.amount and start <= e.date <= end:
            if e.line_key and lands_on.get(e.line_key, "").startswith("credit_card_"):
                continue  # listed above as a card pay-back
            else:
                out.append({"date": e.date.isoformat(), "kind": "bill", "name": e.name, "amount": e.amount, "parts": [],
                            "note": e.note, "key": f"event:{e.id}"})

    order = {"card": 0, "bill": 1, "transfer": 2}
    for item in out:
        item["paid"] = item.get("paid") or _payment_seen(ctx, item)
        item.pop("match", None)
    return sorted(out, key=lambda x: (x["date"], order[x["kind"]], x["name"]))


def _plan_parts(ctx: Ctx, debt: Debt, payday: date, n: int, budgeted: int, top: Debt | None, plan_start: date) -> list[dict]:
    """What the plan sends to one card on one payday: its minimum when it falls
    due before the next payday, plus (top debt only) the month's extra and last
    month's unspent everyday money."""
    step = int(ctx.income.get("pay_every_days", 14))
    nxt = payday + timedelta(days=step)
    month = month_of(payday)
    first = month_bounds(month)[0]
    parts = []
    min_line = next((ln for ln in ctx.lines if ln.debt_key == debt.key and ln.active(month)), None)
    if min_line and min_line.due_day and any(payday <= _due(min_line, m) < nxt for m in {month, month_of(nxt)}):
        d = min_line.due_day
        parts.append({"label": f"minimum (due the {d}{'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')})", "amount": min_line.amount})
    if top and top.key == debt.key:
        extra = round(max(0.0, cards_extra(ctx, month)) / budgeted, 2)
        if extra:
            parts.append({"label": "extra toward payoff", "amount": extra})
        if n == 1:
            last_month = month_of(first - timedelta(days=1))
            # Only once that month is over: until then its leftover isn't known.
            if month_of(plan_start) <= last_month < month_of(ctx.today):
                left = round(sum(max(0.0, r["remaining"]) for r in line_status(ctx, last_month)
                                 if r["kind"] == VARIABLE and r["target"] > 0), 2)
                if left > 0:
                    name = date.fromisoformat(last_month + "-01").strftime("%B")
                    parts.append({"label": f"left over from {name} (everyday lines)", "amount": left})
    return parts


def card_ledger(ctx: Ctx, account: str, debt: Debt, plan_start: date, top: Debt | None) -> dict:
    """Since the plan started: new charges + scheduled payments due so far − payments made.
    Positive = owed back now. Negative = paid ahead (counts toward the next scheduled payment)."""
    budgeted = int(ctx.income.get("budget_paychecks", 2))
    charges = card_charges(ctx, account, plan_start, ctx.today + timedelta(days=1))
    charged = round(-sum(t.amount for t in charges), 2)
    scheduled = 0.0
    for payday in paydays(ctx, plan_start, ctx.today - timedelta(days=1)):
        first, last = month_bounds(month_of(payday))
        n = paydays(ctx, first, last).index(payday) + 1
        if n <= budgeted:
            scheduled += sum(x["amount"] for x in _plan_parts(ctx, debt, payday, n, budgeted, top, plan_start))
        elif top and top.key == debt.key:  # a third paycheck's share for the cards
            rule = third_paycheck_rule(ctx, month_of(payday))
            amt = paycheck_amount(ctx)
            scheduled += amt - float(rule["emergency_fund"]) if rule.get("emergency_fund") else amt * float((rule.get("split") or {}).get("cards", 0.5))
    paid = round(sum(t.amount for t in ctx.txns if t.account == account and t.category == "debt_payment"
                     and t.amount > 0 and t.date >= plan_start), 2)
    due_now = round(charged + scheduled - paid, 2)
    parts = []
    if charges:
        parts.append({"label": f"charges since {plan_start.strftime('%-m/%-d')} ({len(charges)})", "amount": charged})
    if scheduled:
        parts.append({"label": "scheduled card payments due so far", "amount": round(scheduled, 2)})
    if paid:
        parts.append({"label": "already paid", "amount": -paid})
    return {"due_now": due_now, "parts": parts, "charged": charged, "scheduled": round(scheduled, 2), "paid": paid}


def _posted(ctx: Ctx, line_key: str, due: date) -> bool:
    """Has a charge for this line shown up near its due date?"""
    return any(t.amount < 0 and abs((t.date - due).days) <= 5 and resolve_line(ctx, t)[0] == line_key for t in ctx.txns)


def _payment_seen(ctx: Ctx, item: dict) -> bool:
    d = date.fromisoformat(item["date"])
    if item.get("key") and (item["key"], month_of(d)) in ctx.paid_marks:
        return True  # marked done by hand
    if item["kind"] == "card":
        last4 = item.get("account", "")[-4:]
        paid = sum(-t.amount for t in ctx.txns if t.amount < 0 and t.category == "debt_payment" and last4 and last4 in t.description
                   and d - timedelta(days=1) <= t.date <= d + timedelta(days=4))
        return paid >= item["amount"] * 0.95
    if item.get("key") and item["kind"] == "bill":
        # Paid when payments to that line near the due date cover most of it
        # (a small utility bill on the same line doesn't count as the rent).
        near = sum(-t.amount for t in ctx.txns if t.amount < 0 and abs((t.date - d).days) <= 4 and resolve_line(ctx, t)[0] == item["key"])
        return near >= 0.9 * item["amount"]
    return False


# ---------------------------------------------------------------- cash forecast
def checking_balance(ctx: Ctx) -> tuple[float | None, str | None]:
    """Checking's available balance: from bank sync, else the last running balance in a CSV import."""
    account = (ctx.settings.get("cash") or {}).get("account")
    for a in (ctx.settings.get("simplefin") or {}).get("accounts") or []:
        if account and a.get("mapped_to") == account:
            # Available, not posted: pending payments (rent, insurance) are already gone.
            available = a.get("available")
            return float(available if available is not None else a["balance"]), a.get("as_of")
    rows = [t for t in ctx.txns if t.account == account and t.ref and "|bal:" in t.ref]
    if rows:
        last = max(rows, key=lambda t: (t.date, t.id))
        return float(last.ref.split("bal:")[1].replace(",", "")), last.date.isoformat()
    return None, None


def marked_payments(ctx: Ctx) -> list[dict]:
    """Card payments marked as sent on the site that the bank hasn't shown yet.
    `in_balance` is False until a bank sync runs after the mark, so the forecast
    takes them out of checking itself until then."""
    last_sync = (ctx.settings.get("simplefin") or {}).get("last_sync") or ""
    cards = card_accounts(ctx)
    return [{"id": t.id, "date": t.date.isoformat(), "amount": t.amount, "account": t.account,
             "card": cards[t.account].name if t.account in cards else t.account,
             "in_balance": bool(last_sync) and last_sync > t.created_at.isoformat(timespec="seconds")}
            for t in ctx.txns if t.source == "manual" and t.category == "debt_payment" and t.amount > 0
            and t.date >= ctx.today - timedelta(days=10)]


def roommate_inflows(ctx: Ctx, start: date, end: date) -> list[dict]:
    """Roommates' shares for upcoming months (from the household sheet), counted
    two days after the due date. The current month isn't assumed: it's counted
    when it arrives."""
    path = config.DATA_DIR / "ingest" / "household.json"
    if not path.exists():
        return []
    import json

    data = json.loads(path.read_text())
    settings = config.DATA_DIR / "settings.yaml"
    me = (yaml.safe_load(settings.read_text()) or {}).get("household_me") if settings.exists() else None
    out = []
    for m in data.get("months", []):
        if not m.get("due"):
            continue
        due = date.fromisoformat(m["due"])
        arrives = due + timedelta(days=2)
        if due > ctx.today and start <= arrives <= end:
            for name, p in m["people"].items():
                if name != me and p.get("owed"):
                    out.append({"date": arrives.isoformat(), "name": f"{name}'s share ({m['month']})", "amount": p["owed"]})
    return out


def forecast(ctx: Ctx, days: int = 42) -> dict:
    """Checking's projected balance each day: paychecks and roommates in;
    payments, savings transfers and expected everyday spending out."""
    balance, as_of = checking_balance(ctx)
    marked = marked_payments(ctx)
    if balance is not None:
        balance = round(balance - sum(m["amount"] for m in marked if not m["in_balance"]), 2)
    cash = ctx.settings.get("cash") or {}
    cushion = float(cash.get("cushion", 0))
    start, end = ctx.today, ctx.today + timedelta(days=days)
    schedule = payment_schedule(ctx, days)
    paycheck = paycheck_amount(ctx)
    inflows: dict[str, list] = defaultdict(list)
    for d in paydays(ctx, start, end):
        inflows[d.isoformat()].append({"name": "Paycheck", "amount": paycheck})
    for r in roommate_inflows(ctx, start, end):
        inflows[r["date"]].append({"name": r["name"], "amount": r["amount"]})
    outflows: dict[str, list] = defaultdict(list)
    done: dict[str, list] = defaultdict(list)  # already paid; shown on the day, not counted
    for item in schedule:
        row = {"name": item["name"], "amount": item["amount"], "kind": item["kind"], "account": account_label(item.get("account")) if item.get("account") else None,
               "note": item.get("note"), "parts": item.get("parts") or [], "autopay": is_autopay(ctx, item)}
        (done if item.get("paid") else outflows)[item["date"]].append(row)
    automatic = recurring_charges(ctx, start, end)

    # Everyday spending at budget pace: this month's remainder spread over its
    # remaining days, then each later month's budget spread over its days.
    status_now = {r["key"]: r for r in line_status(ctx, month_of(start))}
    def spend_on(d: date) -> float:
        month = month_of(d)
        first, last = month_bounds(month)
        variable = [ln for ln in ctx.lines if ln.kind == VARIABLE and ln.amount > 0 and ln.active(month)]
        if month == month_of(start):
            left = sum(max(0.0, status_now[ln.key]["remaining"]) for ln in variable if ln.key in status_now)
            return left / ((last - start).days + 1)
        return sum(ln.amount for ln in variable) / ((last - first).days + 1)

    rows, running = [], balance
    lowest = None
    for i in range(days + 1):
        d = start + timedelta(days=i)
        key = d.isoformat()
        spend = round(spend_on(d), 2)
        inn = round(sum(x["amount"] for x in inflows[key]), 2)
        out = round(sum(x["amount"] for x in outflows[key]), 2)
        if running is not None:
            running = round(running + inn - out - spend, 2)
            if lowest is None or running < lowest["balance"]:
                lowest = {"date": key, "balance": running}
        rows.append({"date": key, "in": inflows[key], "out": outflows[key], "done": done[key], "auto": automatic[key],
                     "spend": spend, "start": None if running is None else round(running - inn + out + spend, 2),
                     "end": running, "payday": any(x["name"] == "Paycheck" for x in inflows[key])})
    top = top_debt(ctx)
    safe = max(0.0, (lowest["balance"] - cushion)) if lowest else 0.0
    # An early payment comes off the card's next scheduled payments, so it can't
    # be more than what's scheduled to that card in the window.
    accounts = {a for a, d in card_accounts(ctx).items() if top and d.key == top.key}
    safe = min(safe, sum(i["amount"] for i in schedule if i["kind"] == "card" and i.get("account") in accounts and not i.get("paid")))
    return {
        "today": ctx.today.isoformat(), "balance": balance, "as_of": as_of, "cushion": cushion, "days": rows, "lowest": lowest,
        "safe_to_send": float(int(safe // 10 * 10)),  # rounded down to $10
        "send_to": top.name if top else None, "marked": marked, "accounts": account_balances(ctx),
    }


def is_autopay(ctx: Ctx, item: dict) -> bool:
    """Does this scheduled payment come out on its own (budget.yaml `autopay`)?"""
    key = item.get("key") or ""
    line = item.get("line") or (key.split(":")[1] if key.startswith(("cash:", "move:")) else key)
    return line in set(ctx.settings.get("autopay") or [])


def recurring_charges(ctx: Ctx, start: date, end: date) -> dict[str, list]:
    """Subscriptions and renewals from the `recurring` registry by date. They charge
    on their own (a card, PayPal or checking), so the day view lists them for reference."""
    out: dict[str, list] = defaultdict(list)
    for r in ctx.settings.get("recurring") or []:
        if r.get("status", "active") == "cancelled":
            continue
        freq = r.get("frequency", "monthly")
        if freq == "monthly" and r.get("day"):
            d = _next_monthly(start, int(r["day"]))
        elif r.get("next"):
            d = date.fromisoformat(str(r["next"]))
        else:
            continue
        while d <= end:
            if d >= start:
                out[d.isoformat()].append({"name": r["name"], "amount": float(r["amount"]), "account": account_label(r.get("method")),
                                           "autopay": bool(r.get("autopay")), "note": r.get("note"),
                                           "ending": r.get("status") == "ending"})
            d = _add_months(d, EVERY_MONTHS[freq])
            if freq == "monthly" and r.get("day"):
                d = d.replace(day=min(int(r["day"]), calendar.monthrange(d.year, d.month)[1]))
    return out


def account_balances(ctx: Ctx) -> dict:
    """Latest known balance of every account, for the calendar's day view."""
    nw = net_worth(ctx)
    debts = []
    for d in ctx.debts:
        bal, as_of = current_balance(ctx, d.key)
        debts.append({"name": d.name, "kind": d.kind, "balance": round(bal, 2), "as_of": as_of.isoformat() if as_of else None,
                      "limit": d.limit, "apr": d.apr})
    return {"cash": [a for a in nw["assets"] if a["kind"] == "cash"],
            "investments": [a for a in nw["assets"] if a["kind"] == "investment"], "debts": debts}


# ---------------------------------------------------------------- net worth
def net_worth(ctx: Ctx) -> dict:
    """Cash and investments minus debts. Bank balances come from bank sync;
    investments from bank sync when available, else the last number entered."""
    synced = (ctx.settings.get("simplefin") or {}).get("accounts") or []
    manual = ctx.settings.get("asset_balances") or {}
    assets = []
    for a in synced:
        if (a.get("mapped_to") or "").startswith(("checking_", "savings_")):
            assets.append({"key": a["mapped_to"], "name": a["name"].split("-")[0].strip(), "kind": "cash",
                           "balance": a["balance"], "as_of": a["as_of"], "source": "bank sync"})
    for spec in ctx.settings.get("assets") or []:
        match = next((a for a in synced if spec.get("simplefin") and spec["simplefin"].lower() in (a.get("name") or "").lower()), None)
        if match:
            item = {"balance": match["balance"], "as_of": match["as_of"], "source": "bank sync"}
        elif spec["key"] in manual:
            item = {**manual[spec["key"]], "source": "entered"}
        else:
            item = {"balance": spec.get("balance", 0), "as_of": str(spec.get("as_of") or ""), "source": "entered"}
        assets.append({"key": spec["key"], "name": spec["name"], "kind": "investment", "editable": not match, **item})
    debts = [{"key": d.key, "name": d.name, "balance": round(current_balance(ctx, d.key)[0], 2)} for d in ctx.debts]
    total_assets = round(sum(a["balance"] for a in assets), 2)
    total_debts = round(sum(d["balance"] for d in debts), 2)
    return {"assets": assets, "debts": debts, "total_assets": total_assets, "total_debts": total_debts,
            "net": round(total_assets - total_debts, 2)}


# ---------------------------------------------------------------- misc
def leave() -> dict | None:
    draft = config.DATA_DIR / "ingest" / "intake-draft.yaml"
    if not draft.exists():
        return None
    return (yaml.safe_load(draft.read_text()) or {}).get("leave")


def freshness(ctx: Ctx) -> dict:
    last_import: dict[str, str] = {}
    for t in ctx.txns:
        if t.source == "import":
            last_import[t.account or "?"] = max(last_import.get(t.account or "?", ""), t.date.isoformat())
    through = min(last_import.values()) if last_import else None
    logged = [t for t in ctx.txns if t.source in ("shortcut", "manual")]
    return {"bank_data_through": through, "accounts": last_import,
            "logged_since": sum(1 for t in logged if not through or t.date.isoformat() > through),
            "last_logged": max((t.created_at for t in logged), default=None)}


NOT_SPENDING = {"debt_payment", "transfer_internal", "investing", "income", "reimbursement"}


def day_spending(ctx: Ctx, day: date) -> list[dict]:
    """Purchases on a day. Card/loan payments and transfers move money; they aren't spending."""
    out = []
    for t in ctx.txns:
        if t.date == day and t.amount < 0 and t.category not in NOT_SPENDING:
            key, _ = resolve_line(ctx, t)
            ln = ctx.by_key.get(key) if key else None
            out.append({"description": "Personal" if ln and ln.private else t.description, "amount": -t.amount,
                        "line": ln.name if ln else None, "source": t.source})
    return out


def dashboard(today: date | None = None) -> dict:
    ctx = load(today)
    month = month_of(ctx.today)
    status = line_status(ctx, month)
    first, last = month_bounds(month)
    upcoming_pay = paydays(ctx, ctx.today, ctx.today + timedelta(days=21))
    return {
        "today": ctx.today.isoformat(),
        "owner": ctx.settings.get("owner"),
        "month": month,
        "lines": status,
        "safe": safe_to_spend(ctx, status),
        "due": due_soon(ctx),
        "events": upcoming_events(ctx),
        "paydays": [d.isoformat() for d in upcoming_pay],
        "next_paycheck": paycheck_plan(ctx, upcoming_pay[0]) if upcoming_pay else None,
        "payments": payment_schedule(ctx),
        "cards_extra": cards_extra(ctx, month),
        "debts": debts_summary(ctx),
        "projection": projection(ctx),
        "net_worth": net_worth(ctx),
        "cash": {k: v for k, v in forecast(ctx).items() if k != "days"},
        "goals": [{"key": g.key, "name": g.name, "target": g.target, "balance": g.balance} for g in ctx.goals],
        "yesterday": day_spending(ctx, ctx.today - timedelta(days=1)),
        "leave": leave(),
        "freshness": freshness(ctx),
    }


# ---------------------------------------------------------------- recurring
PER_MONTH = {"monthly": 1, "semiannual": 1 / 6, "yearly": 1 / 12, "every_3_years": 1 / 36}
EVERY_MONTHS = {"monthly": 1, "semiannual": 6, "yearly": 12, "every_3_years": 36}


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _next_monthly(today: date, day: int) -> date:
    """The next date (today or later) that falls on `day` of a month."""
    first = date(today.year, today.month, 1)
    for m in (first, _add_months(first, 1)):
        d = m.replace(day=min(day, calendar.monthrange(m.year, m.month)[1]))
        if d >= today:
            return d
    return d


def account_label(account: str | None) -> str:
    if not account:
        return "Not set"
    if account.startswith("credit_card_"):
        return f"Card {account.rsplit('_', 1)[1]}"
    if account.startswith("checking_"):
        return "Checking / debit card"
    return {"paypal": "PayPal", "apple_card": "Apple Card", "apple_cash": "Apple Cash"}.get(account, account.replace("_", " ").title())


def _recommend(kind: str, account: str | None, cards_owed: bool, foreign: bool) -> tuple[str, str]:
    """(recommended account, why) for a recurring payment."""
    if kind in ("loan", "card_minimum"):
        return "checking", "Loan and card payments come straight from checking."
    if kind == "rent":
        return "checking", "Rent goes through the portal from checking."
    if cards_owed:
        why = ("Your cards carry a balance, so they have no grace period: a new charge starts interest the day it posts. "
               "A fixed bill gains nothing from the card, so let checking pay it.")
        if account == "paypal":
            return "paypal", "Fine as is, as long as PayPal draws on checking (not a credit card)."
        if foreign:
            why += " It's billed in euros, so expect about 3% in conversion either way."
        return "checking", why
    return "card", "Once the cards are at $0, put it on a rewards card and pay the card in full each month."


def recurring(ctx: Ctx) -> dict:
    """Every recurring payment: budget bills, household bills, and the `recurring`
    registry (subscriptions, yearly renewals), with how to pay each one."""
    today, month = ctx.today, month_of(ctx.today)
    lands_on = paid_with(ctx)
    cards = card_accounts(ctx)
    cards_owed = any(current_balance(ctx, d.key)[0] > 0 for d in cards.values())
    autopay = set(ctx.settings.get("autopay") or [])
    debts = {d.key: d for d in ctx.debts}
    checking = (ctx.settings.get("cash") or {}).get("account", "checking")
    items: list[dict] = []

    def add(**kw):
        account = kw.get("account")
        rec, why = _recommend(kw["type"], account, cards_owed, kw.pop("foreign", False))
        if rec == "checking":
            rec_account = checking
        elif rec == "card":
            rec_account = account if account and account.startswith("credit_card_") else "credit_card"
        else:
            rec_account = account
        kw.update(method=account_label(account), recommended=account_label(rec_account) if rec != "card" else "Rewards card",
                  why=why, change=bool(account) and rec_account != account and rec != "card" and kw["status"] != "ending",
                  per_month=round(kw["amount"] * PER_MONTH[kw["frequency"]], 2))
        items.append(kw)

    for ln in ctx.lines:
        if ln.kind != BILL or ln.key == "subscriptions":
            continue
        ended = ln.until_month and ln.until_month < month
        if ended and ln.until_month < month_of(today - timedelta(days=62)):
            continue  # long gone
        if ln.debt_key in debts and debts[ln.debt_key].kind == "credit_card":
            kind, account = "card_minimum", checking
        elif ln.debt_key or ln.key.endswith("_loan"):
            kind, account = "loan", checking
        elif ln.key == "housing":
            kind, account = "rent", checking
        else:
            kind, account = "bill", lands_on.get(ln.key)
        nxt = None
        if ln.due_day and not ended:
            nxt = _next_monthly(today, ln.due_day)
            if not ln.active(month_of(nxt)):
                nxt = None
        status = "cancelled" if ended else "ending" if ln.until_month else "active"
        last = None
        if ln.until_month:
            f, l = month_bounds(ln.until_month)
            last = date(f.year, f.month, min(ln.due_day or 1, l.day)).isoformat()
        add(key=ln.key, name=ln.name, type=kind, amount=round(ln.due_amount or ln.amount, 2), frequency="monthly",
            day=ln.due_day, next=nxt.isoformat() if nxt else None, ends=last, account=account, status=status,
            autopay=ln.key in autopay or None, line=ln.name, note=ln.note)

    for cb in ctx.settings.get("cash_bills") or []:
        add(key=cb["key"], name=cb["name"], type="household", amount=float(cb["amount"]), frequency="monthly",
            day=int(cb["day"]), next=_next_monthly(today, int(cb["day"])).isoformat(), ends=None,
            account=cb.get("paid_with"), status="active", autopay=cb["key"] in autopay or None,
            line="Household share", note=cb.get("note") or "Shared bill; the amount varies.")

    for r in ctx.settings.get("recurring") or []:
        freq = r.get("frequency", "monthly")
        nxt = None
        if freq == "monthly" and r.get("day"):
            nxt = _next_monthly(today, int(r["day"]))
        elif r.get("next"):
            nxt = date.fromisoformat(str(r["next"]))
            while nxt < today:
                nxt = _add_months(nxt, EVERY_MONTHS[freq])
        status = r.get("status", "active")
        line = ctx.by_key.get(r.get("line") or "")
        add(key=r["key"], name=r["name"], type="subscription", amount=float(r["amount"]), frequency=freq,
            day=r.get("day"), next=nxt.isoformat() if nxt and status != "cancelled" else None,
            ends=nxt.isoformat() if status == "ending" and nxt else None, account=r.get("method"), status=status,
            autopay=r.get("autopay"), line=line.name if line else None, note=r.get("note"),
            amount_note=r.get("currency_note"), foreign=bool(r.get("currency_note")))

    live = [i for i in items if i["status"] not in ("cancelled", "ending") or (i["ends"] and i["ends"] >= today.isoformat())]
    return {"today": today.isoformat(), "items": items, "cards_owed": cards_owed,
            "per_month": round(sum(i["per_month"] for i in live if i["status"] != "cancelled"), 2),
            "per_year": round(sum(i["per_month"] for i in live if i["status"] != "cancelled") * 12, 2),
            "to_change": sum(1 for i in items if i["change"] and i["status"] != "cancelled")}
