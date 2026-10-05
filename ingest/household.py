"""Reads the shared-house workbook (Google Sheets exported as .xlsx):
per-person owed / paid / left for each month from the "Payments" sheet, plus
the fixed costs from the "Balance Sheet" inputs. Formulas are read as their
cached values, so export from Google Sheets rather than saving from a tool
that doesn't recalculate."""

from datetime import date, datetime
from pathlib import Path

import openpyxl


def _cells(ws):
    return [[c for c in row] for row in ws.iter_rows(values_only=True)]


def _find(rows, text):
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if isinstance(v, str) and v.strip().upper() == text.upper():
                return r, c
    raise ValueError(f"'{text}' not found")


def parse(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    payments = _cells(wb["Payments"])
    hdr_r, month_c = _find(payments, "Month")
    # The row above the header names each person's 3-column group.
    names = [(c, str(v).strip().title()) for c, v in enumerate(payments[hdr_r - 1]) if isinstance(v, str) and v.strip() and v.strip().upper() != "HOUSEHOLD"]
    months = []
    for row in payments[hdr_r + 1:]:
        label = row[month_c]
        if not label or str(label).strip().upper() == "TOTAL":
            break
        due = row[month_c + 1]
        due = due.date() if isinstance(due, datetime) else due
        people = {}
        for c, name in names:
            owed, paid, left = (float(row[c + i] or 0) for i in range(3))
            people[name] = {"owed": round(owed, 2), "paid": round(paid, 2), "left": round(left, 2)}
        months.append({"month": str(label).strip(), "due": due.isoformat() if isinstance(due, date) else None, "people": people})

    fixed = {}
    sheet = _cells(wb["Balance Sheet"])
    r, c = _find(sheet, "MONTHLY FIXED COSTS")
    for row in sheet[r + 1:]:
        if not isinstance(row[c], str) or not isinstance(row[c + 1], (int, float)):
            break
        fixed[row[c].strip()] = float(row[c + 1])
    return {"source": path.name, "fixed_costs": fixed, "months": months}


def summary(data: dict, me: str | None = None, today: date | None = None) -> list[str]:
    """me: your name as it appears in the sheet (data/settings.yaml `household_me`); defaults to the first person."""
    today = today or date.today()
    me = me or next(iter(data["months"][0]["people"]))
    out = ["## Household (shared house)", ""]
    fixed = ", ".join(f"{k} ${v:,.2f}" for k, v in data["fixed_costs"].items())
    out.append(f"Fixed household costs per month: {fixed}.")
    months = [m for m in data["months"] if m["due"]]
    current = next((m for m in months if m["due"] >= today.isoformat()), months[-1])
    upcoming = [m for m in months if m["due"] >= current["due"]]
    steady = upcoming[1]["people"][me]["owed"] if len(upcoming) > 1 else current["people"][me]["owed"]
    out.append(f"- **Your share: ${current['people'][me]['owed']:,.2f} for {current['month']}**, then about "
               f"**${steady:,.2f}/month** plus a third of electric and water as bills arrive.")
    for m in upcoming[:1]:
        others = ", ".join(f"{n} ${p['owed']:,.2f}" for n, p in m["people"].items() if n != me)
        out.append(f"- Roommates owe you for {m['month']} (due {m['due']}): {others}.")
    late = [(m["month"], n, p["left"]) for m in months if m["due"] < current["due"]
            for n, p in m["people"].items() if n != me and p["left"] > 0.05]
    if late:
        out.append("- Still unpaid from past months: " + "; ".join(f"{n} ${left:,.2f} ({month})" for month, n, left in late) + ".")
    else:
        out.append("- Roommates are settled up for every past month.")
    mine = [(m["month"], m["people"][me]["left"]) for m in months if m["due"] < current["due"] and m["people"][me]["left"] > 0.05]
    if mine:
        out.append("- Your own share still marked unpaid: " + "; ".join(f"${left:,.2f} ({month})" for month, left in mine) + ".")
    return out
