"""Income for a year: every pay statement (gross, where it went, net), leave
balances over time, and other money in from the bank. Read-only, like engine.

    python -m app.income [YEAR]
"""

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

from ingest import rules
from ingest.store import load_docs

from . import engine

TAXES = {"federal_tax", "state_tax", "local_tax", "social_security", "medicare"}
RETIREMENT = {"retirement", "retirement_loan"}
INSURANCE = {"health_insurance", "dental_vision", "life_insurance"}
GROUPS = [("taxes", "Taxes"), ("retirement", "Retirement"), ("insurance", "Insurance"), ("other", "Other deductions")]
KIND_NAMES = {"federal_tax": "Federal tax", "state_tax": "State tax", "local_tax": "Local tax", "social_security": "Social Security",
              "medicare": "Medicare", "health_insurance": "Health insurance", "dental_vision": "Dental and vision",
              "life_insurance": "Life insurance", "union_dues": "Union dues", "allotment": "Allotments", "garnishment": "Garnishment"}
EARN_NAMES = {"regular": "Regular pay", "overtime": "Overtime", "holiday": "Holiday pay", "premium": "Premium pay",
              "leave": "Paid leave", "bonus": "Bonuses", "other": "Other earnings"}
LEAVE_NAMES = {"annual": "Vacation (annual leave)", "sick": "Sick leave"}


def _nice(desc: str) -> str:
    """'ABC SAVINGS' -> 'ABC Savings': short words stay as acronyms."""
    if desc.upper() in ("OASDI", "SOCIAL SECURITY"):
        return "Social Security"
    words = [w for w in desc.split()]
    return " ".join(w if len(w.strip(",")) <= 4 and w.isupper() else w.capitalize() for w in words)


def _group(kind: str) -> str:
    return "taxes" if kind in TAXES else "retirement" if kind in RETIREMENT else "insurance" if kind in INSURANCE else "other"


def statements() -> list:
    """Every pay statement on file, one per pay date, oldest first."""
    by_date = {}
    for _, doc, _ in load_docs():
        if doc.pay and doc.pay.pay_date:
            by_date[doc.pay.pay_date] = doc.pay
    return [by_date[k] for k in sorted(by_date)]


def _check(p) -> dict:
    groups = defaultdict(float)
    for d in p.deductions:
        groups[_group(d.kind)] += d.amount
    return {"date": p.pay_date, "gross": p.gross_pay, "net": p.net_pay,
            **{k: round(groups[k], 2) for k, _ in GROUPS},
            "overtime_hours": sum(e.hours or 0 for e in p.earnings if e.kind == "overtime"),
            "extra": round(sum(e.amount for e in p.earnings if e.kind in ("overtime", "bonus")), 2)}


def _leave(pays: list) -> dict | None:
    if not pays:
        return None
    latest = pays[-1]
    kinds = []
    for lv in latest.leave:
        kinds.append({"kind": lv.kind, "name": LEAVE_NAMES.get(lv.kind, lv.kind.capitalize()),
                      "balance": lv.balance_hours, "earned_per_period": lv.accrued_period, "earned_ytd": lv.accrued_ytd,
                      "used_ytd": lv.used_ytd, "used_period": lv.used_period, "expires": lv.use_or_lose_date})
    history = []
    for p in pays:
        row = {"date": p.pay_date}
        for lv in p.leave:
            if lv.balance_hours is not None:
                row[lv.kind] = lv.balance_hours
        history.append(row)
    out = {"as_of": latest.pay_period_end or latest.pay_date, "kinds": kinds, "history": history,
           "year_end": latest.leave_year_end, "carryover_cap": latest.max_leave_carryover}
    annual = next((lv for lv in latest.leave if lv.kind == "annual"), None)
    if annual and annual.balance_hours is not None and latest.leave_year_end and latest.pay_period_end:
        periods = max(0, (date.fromisoformat(latest.leave_year_end) - date.fromisoformat(latest.pay_period_end)).days // 14)
        projected = annual.balance_hours + (annual.accrued_period or 0) * periods
        out.update(periods_left=periods, projected=projected,
                   use_or_lose=max(0.0, projected - latest.max_leave_carryover) if latest.max_leave_carryover else None)
    return out


def other_income(ctx: engine.Ctx, year: int) -> list[dict]:
    """Money in from the bank that isn't a paycheck: side work, refunds, people paying you back."""
    groups: dict[tuple, dict] = {}
    for t in ctx.txns:
        if t.date.year != year or t.amount <= 0 or t.category not in ("income", "reimbursement"):
            continue
        if not (t.account or "").startswith(("checking", "savings")) and t.source == "import":
            continue  # card credits are refunds and payments, not income
        if rules.is_salary(t.description):
            continue
        kind = "Paid back" if t.category == "reimbursement" else "Other income"
        key = (kind, rules.merchant_key(t.description).title())
        g = groups.setdefault(key, {"kind": kind, "name": key[1], "amount": 0.0, "count": 0, "last": None})
        g["amount"] = round(g["amount"] + t.amount, 2)
        g["count"] += 1
        g["last"] = max(g["last"] or "", t.date.isoformat())
    return sorted(groups.values(), key=lambda g: (g["kind"], -g["amount"]))


def income(year: int | None = None) -> dict:
    ctx = engine.load()
    pays = statements()
    years = sorted({int(p.pay_date[:4]) for p in pays} | {ctx.today.year}, reverse=True)
    year = year or ctx.today.year
    mine = [p for p in pays if p.pay_date.startswith(str(year))]
    checks = [_check(p) for p in mine]

    earnings, deductions, employer = defaultdict(lambda: [0.0, 0.0]), defaultdict(float), defaultdict(float)
    for p in mine:
        for e in p.earnings:
            earnings[e.kind][0] += e.amount
            earnings[e.kind][1] += e.hours or 0
        for d in p.deductions:
            deductions[(d.kind, d.description)] += d.amount
        for c in p.employer_contributions:
            employer[c.description] += c.amount
    gross = round(sum(c["gross"] for c in checks), 2)
    net = round(sum(c["net"] for c in checks), 2)

    by_group = []
    for key, label in GROUPS:
        merged: dict[str, float] = defaultdict(float)
        for (k, desc), v in deductions.items():
            if _group(k) == key:
                merged[KIND_NAMES.get(k) or _nice(desc)] += v
        items = sorted(({"name": n, "amount": round(v, 2)} for n, v in merged.items()), key=lambda i: -i["amount"])
        if items:
            by_group.append({"key": key, "name": label, "amount": round(sum(i["amount"] for i in items), 2), "items": items})

    months = defaultdict(lambda: {"gross": 0.0, "net": 0.0, "checks": 0})
    for c in checks:
        m = months[c["date"][:7]]
        m["gross"] += c["gross"]
        m["net"] += c["net"]
        m["checks"] += 1

    latest = mine[-1] if mine else (pays[-1] if pays else None)
    out = {
        "year": year, "years": years, "first_statement": pays[0].pay_date if pays else None, "today": ctx.today.isoformat(), "checks": checks,
        "gross": gross, "net": net, "count": len(checks),
        "kept": round(net / gross, 3) if gross else None,
        "earnings": sorted(({"kind": k, "name": EARN_NAMES.get(k, k.title()), "amount": round(v[0], 2), "hours": round(v[1], 2)}
                            for k, v in earnings.items()), key=lambda e: -e["amount"]),
        "deductions": by_group,
        "employer": {"total": round(sum(employer.values()), 2),
                     "items": sorted(({"name": _nice(k), "amount": round(v, 2)} for k, v in employer.items()), key=lambda i: -i["amount"])},
        "months": [{"month": k, **{f: round(v, 2) if isinstance(v, float) else v for f, v in m.items()}} for k, m in sorted(months.items())],
        "rate": {"hourly": latest.hourly_rate, "overtime": latest.overtime_rate, "salary": latest.annual_salary,
                 "retirement_percent": latest.retirement_percent} if latest else None,
        "leave": _leave(pays),
        "other": other_income(ctx, year),
    }
    if year == ctx.today.year and checks:
        left = engine.paydays(ctx, ctx.today + timedelta(days=1), date(year, 12, 31))
        left = [d for d in left if d.isoformat() > checks[-1]["date"]]
        base = [c for c in checks if not c["extra"]] or checks
        out["projection"] = {"checks_left": len(left),
                             "gross": round(gross + len(left) * statistics.median(c["gross"] for c in base), 2),
                             "net": round(net + len(left) * statistics.median(c["net"] for c in base), 2)}
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(income(int(sys.argv[1]) if len(sys.argv) > 1 else None), indent=1))
