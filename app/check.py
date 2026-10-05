"""Check a budget file before loading it: mistakes that would break the app or
quietly count wrong, then what the plan adds up to. Nothing is written; the
budget goes into a throwaway database.

    python -m app.check                     # data/budget.yaml
    python -m app.check path/to/budget.yaml
    docker compose exec money-doctor python -m app.check

Exits 1 when there are errors."""

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import get_args
from zoneinfo import ZoneInfo

import yaml

os.environ["MD_DB_URL"] = f"sqlite:///{tempfile.mkdtemp()}/check.db"  # before the app opens the real one

from . import config, engine, models, seed  # noqa: E402
from ingest.schemas import Category  # noqa: E402

KINDS = {"variable", "bill", "fund", "savings"}
MONTH = re.compile(r"^\d{4}-\d{2}$")


def problems(b: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    cats = set(get_args(Category))
    inc = b.get("income") or {}
    for k in ("paycheck_net", "pay_anchor", "pay_every_days"):
        if k not in inc:
            errors.append(f"income.{k} is missing")
    if inc.get("pay_every_days") not in (None, 7, 14):
        warnings.append(f"income.pay_every_days is {inc['pay_every_days']}: paydays step by a fixed number of days, "
                        "so only weekly (7) and every two weeks (14) line up; twice-a-month and monthly pay drift")
    try:
        ZoneInfo(str(b.get("timezone", "UTC")))
    except Exception:
        errors.append(f"timezone {b.get('timezone')!r} isn't a time zone name like America/Chicago")

    debts = {d.get("key") for d in b.get("debts") or []}
    for d in b.get("debts") or []:
        for k in ("key", "name", "balance", "apr"):
            if d.get(k) is None:
                errors.append(f"debt {d.get('key') or d.get('name') or '?'}: {k} is missing")
        if d.get("kind") == "credit_card" and not d.get("last4"):
            warnings.append(f"debt {d.get('key')}: no last4, so card transactions and statements can't be matched to it")

    keys = [ln.get("key") for ln in b.get("lines") or []]
    for k in {k for k in keys if keys.count(k) > 1}:
        errors.append(f"line key {k!r} is used more than once")
    for ln in b.get("lines") or []:
        name = ln.get("key") or ln.get("name") or "?"
        for k in ("key", "name", "amount"):
            if ln.get(k) is None:
                errors.append(f"line {name}: {k} is missing")
        if ln.get("kind", "variable") not in KINDS:
            errors.append(f"line {name}: kind {ln.get('kind')!r} isn't one of {', '.join(sorted(KINDS))}")
        if ln.get("kind") == "bill" and not ln.get("due_day"):
            warnings.append(f"line {name}: a bill without due_day never shows as due or paid")
        if ln.get("pay_from") not in (None, 1, 2):
            errors.append(f"line {name}: pay_from must be 1 or 2 (which paycheck of the month)")
        for k in ("tracks", "offsets"):
            for c in ln.get(k) or []:
                if c not in cats:
                    errors.append(f"line {name}: {k} has {c!r}, which isn't a category (see ingest/schemas.py)")
        if ln.get("debt") and ln["debt"] not in debts:
            errors.append(f"line {name}: debt {ln['debt']!r} isn't in debts")
        for k in ("from", "until"):
            if ln.get(k) is not None and not MONTH.match(str(ln[k])[:7]):
                errors.append(f"line {name}: {k} should be YYYY-MM")

    for rule in (b.get("plan") or {}).get("third_paycheck") or []:
        if not MONTH.match(str(rule.get("month", ""))[:7]):
            errors.append(f"plan.third_paycheck: month {rule.get('month')!r} should be YYYY-MM")

    for r in b.get("recurring") or []:
        freq = r.get("frequency", "monthly")
        if freq not in engine.EVERY_MONTHS:
            errors.append(f"recurring {r.get('key')}: frequency {freq!r} isn't one of {', '.join(engine.EVERY_MONTHS)}")
        elif not (r.get("next") or (freq == "monthly" and r.get("day"))):
            warnings.append(f"recurring {r.get('key')}: needs next (a date), or day for monthly ones, to show on the calendar")
        for k in ("key", "name", "amount"):
            if r.get(k) is None:
                errors.append(f"recurring {r.get('key') or r.get('name') or '?'}: {k} is missing")
    for cb in b.get("cash_bills") or []:
        for k in ("key", "name", "amount", "day"):
            if cb.get(k) is None:
                errors.append(f"cash_bills {cb.get('key') or '?'}: {k} is missing")
    known = set(keys) | {cb.get("key") for cb in b.get("cash_bills") or []}
    for k in b.get("autopay") or []:
        if k not in known:
            warnings.append(f"autopay: {k!r} isn't a line or cash_bills key")
    if not (b.get("digest") or {}).get("to"):
        warnings.append("digest.to is empty, so there's no morning email")
    return errors, warnings


def summary(path: Path) -> str:
    models.init_db()
    seed.seed(path)
    ctx = engine.load()
    month = engine.month_of(ctx.today)
    pay, n = engine.paycheck_amount(ctx), int(ctx.income.get("budget_paychecks", 2))
    active = [ln for ln in ctx.lines if ln.active(month)]
    extra = engine.cards_extra(ctx, month)
    out = [f"This month ({month}):",
           f"  income budgeted   {pay * n:>10,.2f}  ({n} paychecks of {pay:,.2f})",
           f"  lines             {sum(ln.amount for ln in active):>10,.2f}  ({len(active)} active)"]
    for kind in sorted(KINDS):
        total = sum(ln.amount for ln in active if ln.kind == kind)
        if total:
            out.append(f"    {kind:<15} {total:>10,.2f}")
    out.append(f"  extra to debt     {extra:>10,.2f}" + ("  <- the lines add up to more than the income" if extra < 0 else ""))
    top = engine.top_debt(ctx)
    if top:
        out.append(f"  goes to           {top.name} ({top.apr}% APR)")
    p = engine.projection(ctx)
    if ctx.debts:
        done = p["done"] or "not within 10 years"
        verdict = "" if not p["target"] else ("  on track" if p["on_track"] else "  behind the target")
        out += ["", f"Payoff: {done} (target {p['target'] or 'none'}){verdict}",
                f"  interest until then {p['interest']:,.2f}"]
        for key, m in sorted(p["paid_off"].items(), key=lambda x: x[1]):
            out.append(f"  {key:<18} paid off {m}")
    return "\n".join(out)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else config.BUDGET_FILE
    if not path.exists():
        sys.exit(f"{path} doesn't exist (the app would fall back to config/budget.example.yaml)")
    try:
        b = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        sys.exit(f"{path} isn't valid YAML:\n{e}")
    errors, warnings = problems(b)
    for e in errors:
        print(f"error: {e}")
    for w in warnings:
        print(f"warning: {w}")
    if errors:
        sys.exit(1)
    if warnings:
        print()
    print(summary(path))


if __name__ == "__main__":
    main()
