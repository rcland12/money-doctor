"""A calendar feed (.ics) of payments, paydays and reminders, for Apple
Calendar or Google Calendar to subscribe to. Calendar apps can't log in, so
the feed is reached through a secret link (reset it from Settings)."""

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from . import engine
from .models import Session, Setting

KEY = "calendar_key"


def link_key(reset: bool = False) -> str:
    with Session.begin() as s:
        row = s.get(Setting, KEY)
        if row and row.value and not reset:
            return row.value
        key = secrets.token_urlsafe(24)
        s.merge(Setting(key=KEY, value=key))
        return key


def valid(key: str | None) -> bool:
    with Session() as s:
        row = s.get(Setting, KEY)
    return bool(key and row and row.value and secrets.compare_digest(key, row.value))


def _esc(text: str) -> str:
    """Escape TEXT values: backslash, semicolon, comma, newline."""
    return text.replace("\\", r"\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")


def _fold(line: str) -> str:
    """iCalendar lines are folded at 75 octets."""
    out, raw = [], line.encode()
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return "\r\n".join(out)


def _event(day: str, title: str, description: str, alarm: bool, uid_key: str | None = None) -> list[str]:
    d = date.fromisoformat(day)
    uid = hashlib.sha1(f"{day}|{uid_key or title.split(':')[0]}".encode()).hexdigest()[:20]
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@money-doctor",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_esc(title)}",
        "TRANSP:TRANSPARENT",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_esc(description)}")
    if alarm:  # 9:00 that morning
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(title)}", "TRIGGER:PT9H", "END:VALARM"]
    return lines + ["END:VEVENT"]


def feed(url: str) -> str:
    ctx = engine.load()
    days = 90
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Money Doctor//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:Money Doctor", "REFRESH-INTERVAL;VALUE=DURATION:PT2H", "X-PUBLISHED-TTL:PT2H"]
    # Same UID whatever the state, so "Pay X" turns into "Paid: X" in place.
    for item in engine.payment_schedule(ctx, days):
        detail = "\n".join(f"{p['label']}: ${p['amount']:,.2f}" for p in item.get("parts") or [])
        note = item.get("note") or ""
        desc = "\n".join(x for x in (detail, note, url) if x)
        amount = f"${item['amount']:,.2f}"
        if item.get("paid"):
            title, alarm = f"Paid: {item['name']} {amount}", False
        elif engine.is_autopay(ctx, item):
            title, alarm = f"Autopay: {item['name']} {amount}", False
            desc = "Comes out on its own. Make sure checking has the money.\n" + desc
        else:
            title, alarm = f"{item['name']}: {amount}", item["kind"] != "transfer"
        lines += _event(item["date"], title, desc, alarm, uid_key=item["name"])
    for day, charges in engine.recurring_charges(ctx, ctx.today, ctx.today + timedelta(days=days)).items():
        for c in charges:
            title = f"Ending: {c['name']} (renews ${c['amount']:,.2f} unless cancelled)" if c["ending"] else f"Autopay: {c['name']} ${c['amount']:,.2f}"
            lines += _event(day, title, "\n".join(x for x in (f"Charged to {c['account']}", c.get("note") or "", url) if x),
                            alarm=False, uid_key=c["name"])
    for d in engine.paydays(ctx, ctx.today, ctx.today + timedelta(days=days)):
        lines += _event(d.isoformat(), f"Payday: ${engine.paycheck_amount(ctx):,.2f}", url, alarm=False)
    for e in ctx.events:
        if e.kind in ("reminder", "birthday", "trip", "event") and ctx.today <= e.date <= ctx.today + timedelta(days=days):
            lines += _event(e.date.isoformat(), e.name, e.note or "", alarm=e.kind == "reminder")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
