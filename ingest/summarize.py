"""Combine every parsed/extracted document into a summary and a draft intake file."""

import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import rules
from .schemas import AccountStatement, DocumentExtraction, PayStatement, Transaction

NOT_SPENDING = {"income", "reimbursement", "transfer_internal", "debt_payment", "investing"}
ONE_TIME = {"moving"}
MONEY_IN = {"income", "reimbursement"}
OWED_KINDS = {"credit_card", "auto_loan", "personal_loan", "installment"}
# Categories where a same-amount charge every month means a bill, not a habit.
BILL_LIKE = {"rent_housing", "utilities", "phone_internet", "insurance", "subscriptions", "installment_plan", "auto", "personal_private"}


def _money(x: float | None) -> str:
    return "?" if x is None else f"${x:,.2f}"


def _month(d: str) -> str:
    return d[:7]


def _table(header: list[str], rows: list[list], align: str) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---:" if a == "r" else "---" for a in align) + "|"] + [
        "| " + " | ".join(str(c) for c in r) + " |" for r in rows
    ]


# ---------------------------------------------------------------- pay
def pay_summary(pays: list[PayStatement]) -> tuple[list[str], dict]:
    pays = sorted(pays, key=lambda p: p.pay_date or p.pay_period_end or "")
    nets = [p.net_pay for p in pays]
    ot = [(sum(e.amount for e in p.earnings if e.kind == "overtime"), sum(e.hours or 0 for e in p.earnings if e.kind == "overtime")) for p in pays]
    bonus = [sum(e.amount for e in p.earnings if e.kind == "bonus") for p in pays]
    base_nets = [p.net_pay for p, (o, _), b in zip(pays, ot, bonus) if o == 0 and b == 0] or nets
    base = statistics.median(base_nets)
    latest = pays[-1]
    rows = [[p.pay_date, _money(p.gross_pay), f"{h:g}", _money(o), _money(b) if b else "", _money(p.net_pay)]
            for p, (o, h), b in zip(pays, ot, bonus)]
    out = ["## Pay", "", f"{len(pays)} pay statements, {pays[0].pay_date} to {latest.pay_date}.", ""]
    out += _table(["Pay date", "Gross", "OT hrs", "OT pay", "Bonus", "Net"], rows, "lrrrrr")
    checks_with_ot = sum(1 for o, _ in ot if o > 0)
    yearly_extra = sum(n - base for n in nets if n > base)
    out += [
        "",
        f"- Current rate: {_money(latest.hourly_rate)}/hr, OT {_money(latest.overtime_rate)}/hr, base pay {_money(latest.annual_salary)}/yr",
        f"- **Base net (no OT, no bonuses): {_money(base)} per check**, about {_money(base * 26 / 12)}/month. Budget fixed costs on this.",
        f"- Overtime on {checks_with_ot} of {len(pays)} checks, {sum(h for _, h in ot):g} hours total. OT and bonuses added {_money(yearly_extra)} net over the period. Send that kind of extra straight to debt.",
        f"- Retirement: you put in {latest.retirement_percent:g}% and your employer adds {_money(latest.employer_retirement_contribution)} per check. If that's the full match, keep it.",
    ]
    deductions: dict[str, float] = defaultdict(float)
    for d in latest.deductions:
        deductions[d.kind] += d.amount
    out += ["", "Deductions on the latest check: " + ", ".join(f"{k} {_money(v)}" for k, v in sorted(deductions.items(), key=lambda kv: -kv[1]))]
    draft = {
        "name": "Main job",
        "frequency": "biweekly",
        "net_per_paycheck_base": round(base, 2),
        "net_per_paycheck_median": round(statistics.median(nets), 2),
        "net_per_paycheck_min": round(min(nets), 2),
        "net_per_paycheck_max": round(max(nets), 2),
        "gross_per_paycheck_latest": latest.gross_pay,
        "last_pay_date": latest.pay_date,
        "overtime_checks": f"{checks_with_ot} of {len(pays)}",
        "is_amount_steady": checks_with_ot == 0,
    }
    return out, draft


def leave_summary(pays: list[PayStatement]) -> tuple[list[str], dict]:
    pays = sorted(pays, key=lambda p: p.pay_period_end or "")
    latest = pays[-1]
    by_kind = {lv.kind: lv for lv in latest.leave}
    out = ["## Leave", ""]
    rows = [[lv.kind, lv.balance_hours if lv.balance_hours is not None else "", lv.accrued_period or "",
             lv.used_ytd or "", lv.use_or_lose_date or ""] for lv in latest.leave]
    out += _table(["Type", "Balance (hrs)", "Earned per pay period", "Used this leave year", "Use-or-lose date"], rows, "lrrrl")
    draft: dict = {"as_of": latest.pay_period_end}
    annual = by_kind.get("annual")
    if annual and annual.balance_hours is not None and latest.leave_year_end and latest.pay_period_end:
        end = date.fromisoformat(latest.leave_year_end)
        last = date.fromisoformat(latest.pay_period_end)
        periods_left = max(0, (end - last).days // 14)
        rate = annual.accrued_period or 0
        projected = annual.balance_hours + rate * periods_left
        cap = latest.max_leave_carryover
        lose = max(0.0, projected - cap) if cap else 0.0
        out += [
            "",
            f"- Vacation: {annual.balance_hours:g} hrs now, +{rate:g} hrs per pay period ({rate * 26:g} hrs = {rate * 26 / 8:g} days a year).",
            f"- By leave year end ({latest.leave_year_end}, {periods_left} pay periods away) you'll have about **{projected:g} hrs ({projected / 8:.1f} days)** if you take none.",
        ]
        if cap:
            out.append(f"- Carryover cap is {cap:g} hrs: " + (f"**use at least {lose:g} hrs before {latest.leave_year_end} or lose them.**" if lose else "nothing to lose this year."))
        draft.update(annual_balance=annual.balance_hours, annual_accrual_per_period=rate, leave_year_end=latest.leave_year_end,
                     projected_at_year_end=projected, carryover_cap=cap, use_or_lose_hours=lose)
    sick = by_kind.get("sick")
    if sick and sick.balance_hours is not None:
        used = [next((lv.used_period or 0 for lv in p.leave if lv.kind == "sick"), 0) for p in pays]
        out.append(f"- Sick leave: {sick.balance_hours:g} hrs, +{sick.accrued_period or 0:g} per pay period; you used {sum(used):g} hrs across these {len(pays)} statements.")
        draft["sick_balance"] = sick.balance_hours
    bonus = by_kind.get("bonus time off")
    if bonus and bonus.balance_hours:
        out.append(f"- Bonus time off: {bonus.balance_hours:g} hrs. These expire (check the use-or-lose date on your pay statement), so use them first.")
        draft["bonus_time_off_balance"] = bonus.balance_hours
    return out, draft


# ---------------------------------------------------------------- accounts
def account_key(s: AccountStatement) -> str:
    return f"{s.institution} {s.account_kind} ••{s.account_last4 or '????'}"


def accounts_summary(stmts: list[AccountStatement]) -> tuple[list[str], list, list]:
    # Latest statement per account that actually states a balance (card CSVs don't).
    latest: dict[str, AccountStatement] = {}
    for s in sorted(stmts, key=lambda s: s.period_end or ""):
        if s.closing_balance is not None or account_key(s) not in latest:
            latest[account_key(s)] = s
    accounts, debts, rows = [], [], []
    for key, s in latest.items():
        apr = (s.card.purchase_apr if s.card else None) or (s.loan.interest_rate if s.loan else None)
        minimum = (s.card.minimum_payment_due if s.card else None) or (s.loan.regular_payment if s.loan else None)
        due = (s.card.payment_due_date if s.card else None) or (s.loan.payment_due_date if s.loan else None)
        limit = s.card.credit_limit if s.card else None
        balance = None if s.closing_balance is None else round(s.closing_balance, 2)
        used = f"{balance / limit:.0%}" if balance is not None and limit else ""
        rows.append([key, s.period_end, _money(balance), f"{apr}%" if apr is not None else "", _money(minimum) if minimum else "", due or "", _money(limit) if limit else "", used])
        if s.account_kind in OWED_KINDS:
            debts.append({"name": key, "type": s.account_kind, "balance": balance, "apr": apr, "minimum_payment": minimum,
                          "due": due, "credit_limit": limit})
        else:
            accounts.append({"name": key, "type": s.account_kind, "balance": balance, "as_of": s.period_end})
    out = ["## Accounts (latest statement each)", ""]
    out += _table(["Account", "As of", "Balance", "APR", "Min due", "Due", "Limit", "Used"], rows, "llrrrlrr")
    card_debt = sum(d["balance"] or 0 for d in debts if d["type"] == "credit_card")
    card_limit = sum(d["credit_limit"] or 0 for d in debts if d["type"] == "credit_card")
    if card_limit:
        out += ["", f"Credit card debt **{_money(card_debt)}** of {_money(card_limit)} in limits ({card_debt / card_limit:.0%} used). "
                "Under 30% is where credit scores stop being hurt by it."]
    return out, accounts, debts


# ---------------------------------------------------------------- transactions
def all_transactions(stmts: list[AccountStatement]) -> list[tuple[AccountStatement, Transaction, str]]:
    """Deduplicated (statement, transaction, category) across overlapping files."""
    seen, out = set(), []
    for s in stmts:
        for t in s.transactions:
            key = (account_key(s), t.reference) if t.reference else (account_key(s), t.date, t.amount, t.description)
            if key in seen:
                continue
            seen.add(key)
            category, _ = rules.categorize(t.description, t.category, t.date, t.amount)
            out.append((s, t, category))
    return out


def common_window(stmts: list[AccountStatement]) -> tuple[str, str]:
    """Dates every account has data for, so months compare fairly."""
    spans: dict[str, list[str]] = defaultdict(list)
    for s in stmts:
        spans[account_key(s)] += [s.period_start, s.period_end]
    starts = [min(d for d in v if d) for v in spans.values()]
    ends = [max(d for d in v if d) for v in spans.values()]
    return max(starts), min(ends)


def spending_summary(stmts: list[AccountStatement]) -> tuple[list[str], dict, list]:
    start, end = common_window(stmts)
    txns = [(s, t, c) for s, t, c in all_transactions(stmts) if start <= t.date <= end]
    months = sorted({_month(t.date) for _, t, _ in txns})
    n_months = (date.fromisoformat(end) - date.fromisoformat(start)).days / 30.44
    out = [f"## Money in and out, {start} to {end} ({n_months:.1f} months, all accounts)", ""]

    # Money in
    income: dict[str, float] = defaultdict(float)
    for _, t, c in txns:
        if c in MONEY_IN and t.amount > 0:
            k = rules.merchant_key(t.description)
            src = "Salary" if rules.is_salary(t.description) else ("Roommate & friends paying you back" if c == "reimbursement" else "Side income & other")
            income[src] += t.amount
    out += ["**Money in, per month:** " + ", ".join(f"{k} {_money(v / n_months)}" for k, v in sorted(income.items(), key=lambda kv: -kv[1])), ""]

    # Spending by category and month
    by_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for _, t, c in txns:
        if c not in NOT_SPENDING:
            by_cat[c][_month(t.date)] -= t.amount  # refunds net out
    averages = {c: round(sum(v.values()) / n_months, 2) for c, v in by_cat.items()}
    rows = [[c] + [f"{by_cat[c].get(m, 0):,.0f}" for m in months] + [f"**{averages[c]:,.0f}**"]
            for c in sorted(by_cat, key=lambda c: -averages[c])]
    total = sum(averages.values())
    ongoing = sum(v for c, v in averages.items() if c not in ONE_TIME)
    rows.append(["**total**"] + [f"**{sum(by_cat[c].get(m, 0) for c in by_cat):,.0f}**" for m in months] + [f"**{total:,.0f}**"])
    out += ["**Spending by category** (excludes card/loan payments, transfers, investing):", ""]
    out += _table(["Category"] + [m[2:] for m in months] + ["Avg/mo"], rows, "l" + "r" * (len(months) + 1))
    reimbursed = sum(t.amount for _, t, c in txns if c == "reimbursement") / n_months
    out += ["", f"Without one-time move costs: **{_money(ongoing)}/mo**. Roommates and friends paid back "
            f"{_money(reimbursed)}/mo of that, so your own money covered about **{_money(ongoing - reimbursed)}/mo**."]

    # Interest and fees per card
    interest: dict[str, float] = defaultdict(float)
    for s, t, c in txns:
        if c == "fees_interest":
            interest[account_key(s)] -= t.amount
    if interest:
        out += ["", "**Interest and fees paid:** " + ", ".join(f"{k} {_money(v)} ({_money(v / n_months)}/mo)" for k, v in interest.items())
                + f". Total **{_money(sum(interest.values()))}** over the period."]

    # Other outflows worth seeing
    for cat, label in (("debt_payment", "Card and loan payments"), ("investing", "Money moved to investing"), ("installment_plan", "Installment plans")):
        amt = -sum(t.amount for s, t, c in txns if c == cat and s.account_kind in ("checking", "savings"))
        if amt:
            out.append(f"- {label} from checking: {_money(amt)} ({_money(amt / n_months)}/mo)")

    # Largest uncategorized merchants
    other: dict[str, float] = defaultdict(float)
    for _, t, c in txns:
        if c == "other" and t.amount < 0:
            other[rules.merchant_key(t.description)] -= t.amount
    if other:
        top = sorted(other.items(), key=lambda kv: -kv[1])[:8]
        out += ["", "**Largest 'other' merchants** (add them to data/merchant-rules.yaml): " + ", ".join(f"{k} {_money(v)}" for k, v in top)]

    # Recurring charges
    groups: dict[str, list[tuple[AccountStatement, Transaction, str]]] = defaultdict(list)
    for s, t, c in txns:
        if c not in NOT_SPENDING and t.amount < 0:
            groups[rules.merchant_key(t.description)].append((s, t, c))
    recurring = []
    for merchant, items in groups.items():
        ts = [t for _, t, _ in items]
        category = statistics.mode(c for _, _, c in items)
        ts_months = {_month(t.date) for t in ts}
        amounts = [-t.amount for t in ts]
        med = statistics.median(amounts)
        steady = sum(abs(a - med) <= max(0.15 * med, 1.0) for a in amounts) >= 0.7 * len(amounts)
        last_seen = max(t.date for t in ts)
        if category in BILL_LIKE and len(ts_months) >= 3 and steady or category == "installment_plan":
            recurring.append({
                "name": merchant.title(), "amount": round(med, 2), "category": category,
                "months_seen": len(ts_months), "billing_days": sorted({int(t.date[8:10]) for t in ts}),
                "last_seen": last_seen, "account": account_key(items[-1][0]),
                "active": last_seen >= (date.fromisoformat(end) - timedelta(days=45)).isoformat(),
            })
    recurring.sort(key=lambda r: (not r["active"], -r["amount"]))
    rows = [[r["name"], _money(r["amount"]), r["category"], r["months_seen"], ", ".join(map(str, r["billing_days"][:6])),
             r["last_seen"], "yes" if r["active"] else "stopped?"] for r in recurring]
    out += ["", "## Recurring charges", ""]
    out += _table(["Merchant", "Typical", "Category", "Months", "Billing days", "Last seen", "Active"], rows, "lrlrlll")
    active_total = sum(r["amount"] for r in recurring if r["active"] and r["category"] in ("subscriptions", "installment_plan"))
    out += ["", f"Active subscriptions and installments: about **{_money(active_total)}/month**."]
    return out, averages, recurring


def build(docs: list[tuple[str, DocumentExtraction, list[str]]], household_lines: list[str] | None = None) -> tuple[str, dict]:
    pays = [d.pay for _, d, _ in docs if d.pay]
    stmts = [d.statement for _, d, _ in docs if d.statement]
    md = [f"# Money Doctor ingest summary ({date.today()})", "", f"{len(docs)} documents: {len(pays)} pay statements, {len(stmts)} account files.", ""]
    draft: dict = {"_generated": date.today().isoformat()}
    flagged = [(name, problems) for name, _, problems in docs if problems]
    if flagged:
        md += ["## Needs a human look", ""] + [f"- `{n}`: {'; '.join(p)}" for n, p in flagged] + [""]
    if pays:
        lines, income = pay_summary(pays)
        md += lines + [""]
        lines, leave = leave_summary(pays)
        md += lines + [""]
        draft.update(income=[income], leave=leave)
    if household_lines:
        md += household_lines + [""]
    if stmts:
        lines, accounts, debts = accounts_summary(stmts)
        md += lines + [""]
        lines, averages, recurring = spending_summary(stmts)
        md += lines
        draft.update(accounts=accounts, debts=debts, variable_spending_monthly_avg=averages, recurring_detected=recurring)
    return "\n".join(md) + "\n", draft
