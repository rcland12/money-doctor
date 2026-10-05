"""The morning email: today's spending room, what's due, the next paycheck,
yesterday's spending, debt progress, and what's coming up.

  python -m app.digest                  # print the text version for today
  python -m app.digest --html out.html  # write the HTML version
  python -m app.digest --send           # send it now
  python -m app.digest --date 2026-04-14
"""

import argparse
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config, engine
from .models import DigestLog, Session, init_db

env = Environment(loader=FileSystemLoader(Path(__file__).with_name("templates")), autoescape=select_autoescape(["html"]))


def money(x: float | None, cents: bool = True) -> str:
    if x is None:
        return "?"
    return f"-${abs(x):,.2f}" if x < 0 else (f"${x:,.2f}" if cents else f"${x:,.0f}")


def day_label(iso: str, today: date) -> str:
    d = date.fromisoformat(iso)
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta < 0:
        return d.strftime("%a %-m/%-d")
    return d.strftime("%a %-m/%-d") if delta < 7 else d.strftime("%b %-d")


env.filters["money"] = money
env.filters["ordinal"] = lambda n: f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def context(today: date | None = None) -> dict:
    """What the email shows. Balances, birthdays and leave stay on the website."""
    db = engine.dashboard(today)
    t = date.fromisoformat(db["today"])
    lines = db["lines"]
    variable = [ln for ln in lines if ln["kind"] == "variable" and ln["target"] > 0]
    for ln in variable:
        ln["frac"] = min(max(ln["spent"] / ln["target"], 0), 1)
        ln["role"] = {"over": "bad", "ahead": "warn"}.get(ln.get("pace"), "good")
    for item in db["due"]:
        item["label"] = day_label(item["date"], t)
    events = [e for e in db["events"] if e["kind"] != "birthday" and e["days_away"] <= 21]
    for e in events:
        e["label"] = day_label(e["date"], t)
    # Payments: everything through the next payday (at least a week), by day.
    upcoming = [date.fromisoformat(d) for d in db["paydays"] if date.fromisoformat(d) > t]
    horizon = max(7, (upcoming[0] - t).days if upcoming else 7)
    groups: list[dict] = []
    for item in db["payments"]:
        d = date.fromisoformat(item["date"])
        if (d - t).days > horizon:
            continue
        if not groups or groups[-1]["date"] != item["date"]:
            groups.append({"date": item["date"], "label": day_label(item["date"], t), "today": d == t, "items": []})
        groups[-1]["items"].append(item)
    fresh = db["freshness"]
    return {
        "t": t,
        "owner": db["owner"],
        "date_long": t.strftime("%A, %B %-d"),
        "month_name": t.strftime("%B"),
        "safe": db["safe"],
        "payment_days": groups,
        "cash": db.get("cash") or {},
        "pay_today": next((g["items"] for g in groups if g["today"]), []),
        "variable": variable,
        "personal": next((ln for ln in lines if ln["private"] and ln["spent"] > 0), None),
        "yesterday": db["yesterday"],
        "yesterday_total": sum(x["amount"] for x in db["yesterday"]),
        "events": events,
        "fresh": fresh,
        "fresh_label": date.fromisoformat(fresh["bank_data_through"]).strftime("%b %-d") if fresh["bank_data_through"] else None,
        "url": config.PUBLIC_URL,
    }


def subject(c: dict) -> str:
    parts = [c["t"].strftime("%a %-m/%-d"), f"{money(c['safe']['total_per_day'], cents=False)}/day to spend"]
    todo = [i for i in c["pay_today"] if not i["paid"] and i["kind"] != "transfer"]
    if todo:
        parts.append("pay today: " + ", ".join(f"{i['name'].removeprefix('Pay ')} {money(i['amount'], cents=False)}" for i in todo[:3]))
    return " · ".join(parts)


def render(today: date | None = None) -> tuple[str, str, str]:
    c = context(today)
    return subject(c), env.get_template("digest.txt").render(**c), env.get_template("digest.html").render(**c)


def send(today: date | None = None, to: str | None = None, force: bool = False) -> str:
    today = today or date.today()
    init_db()
    with Session() as s:
        if not force and s.get(DigestLog, today):
            return "already sent today"
        digest_cfg = engine.load(today).settings.get("digest") or {}
    to = to or digest_cfg.get("to")
    if not (config.SMTP_HOST and to):
        return "not sent: set SMTP_HOST and digest.to"
    subj, text, html = render(today)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subj, config.SMTP_FROM, to
    msg["List-Id"] = "Money Doctor <digest.money-doctor>"  # Gmail filter: list:digest.money-doctor
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        if config.SMTP_STARTTLS:
            smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)
    with Session.begin() as s:
        s.merge(DigestLog(day=today, status=f"sent to {to}"))
    return f"sent to {to}"


def seconds_until(send_at: str, now: datetime) -> float:
    hh, mm = map(int, send_at.split(":"))
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--html", type=Path, help="write the HTML version to this file")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--to")
    args = ap.parse_args()
    if args.send:
        print(send(args.date, args.to, force=True))
        return
    subj, text, html = render(args.date)
    if args.html:
        args.html.write_text(html)
    print(f"Subject: {subj}\n\n{text}")


if __name__ == "__main__":
    main()
