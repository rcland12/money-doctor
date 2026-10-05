"""Payment emails -> transactions, within a couple of minutes of the payment.

Venmo, Cash App, PayPal and Bank of America (Zelle, card alerts) all email a
receipt for every payment. A Gmail filter puts those in one label; this reads
that label over IMAP (with a Gmail app password) and logs each payment.

  python -m app.mail --preview     # read the label, print what it would log, change nothing
  python -m app.mail --check       # log new payments now

Formats differ by sender and change over time, so parsing is by pattern, not
by template. Anything that looks like a payment but doesn't parse is kept as
"review" and shown in Settings, never guessed at.
"""

import argparse
import email
import html
import imaplib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.policy import default as default_policy
from email.utils import parseaddr, parsedate_to_datetime

from sqlalchemy import select

from ingest import rules

from . import config, engine
from .models import MailSeen, Session, Setting, Txn

PROVIDERS = {
    "venmo.com": "Venmo",
    "cash.app": "Cash App",
    "square.com": "Cash App",
    "squareup.com": "Cash App",
    "paypal.com": "PayPal",
    "bankofamerica.com": "Bank of America",
}
AMOUNT = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
# Names are capitalized words, so only the keywords around them ignore case.
NAME = r"(?P<who>[A-Z][\w.'&*-]*(?:[ \t]+[A-Z][\w.'&*-]*){0,3})"
INCOMING = [
    re.compile(NAME + r"\s+(?i:sent you|paid you)"),
    re.compile(r"(?i:received|you've got|you got)\b.*?\$[\d,.]+(?:\s*USD)?\s+(?i:from)\s+" + NAME),
]
OUTGOING = [
    re.compile(r"(?i:you (?:paid|sent)(?: a payment of)?)(?:\s*\$[\d,.]+(?:\s*USD)?)?\s+(?i:to)\s+" + NAME),
    re.compile(r"(?i:you paid)\s+" + NAME + r"\s+\$"),
    re.compile(r"(?i:receipt for your payment|payment sent|you sent money)\s+(?i:to)\s+" + NAME),
    re.compile(r"(?i:you completed)\s+" + NAME + r"'s (?i:request)"),
    re.compile(NAME + r"\s+(?i:charged you)"),
]
CARD_ALERT = re.compile(r"(?:credit|debit) card|card transaction|purchase", re.I)
MERCHANT = re.compile(r"(?:Merchant|Where|At)\s*:\s*(.+)", re.I)
LAST4 = re.compile(r"(?:ending in|ending|\*{2,}|x{2,})\s*(\d{4})", re.I)
MEMO = re.compile(r"(?:\b(?:Memo|Note|Message)\s*:\s*|\bfor\s+[\"“]?)(.{2,60}?)[\"”]?\s*(?:$|\n|\.)", re.I | re.M)
PAYMENT_WORDS = re.compile(r"\b(paid|sent|received|payment|charged|transaction|purchase|zelle|request|got money)\b", re.I)


@dataclass
class Receipt:
    provider: str
    direction: str  # "in" or "out"
    amount: float
    who: str
    memo: str | None
    last4: str | None
    when: date

    @property
    def description(self) -> str:
        if self.provider == "Bank of America" and self.direction == "out" and self.last4:
            return self.who  # a card purchase: the merchant
        verb = "from" if self.direction == "in" else "to"
        label = "Zelle" if self.provider == "Bank of America" else self.provider
        return f"{label} payment {verb} {self.who}"


def _text(msg: email.message.EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    body = part.get_content()
    if part.get_content_type() == "text/html":
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", body)
        body = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|td|li|h\d)>", "\n", body)
        body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"[ \t ]+", " ", body)


def provider_of(sender: str) -> str | None:
    domain = parseaddr(sender)[1].lower().rsplit("@", 1)[-1]
    return next((name for d, name in PROVIDERS.items() if domain == d or domain.endswith("." + d)), None)


def parse(sender: str, subject: str, body: str, when: date) -> Receipt | str | None:
    """A Receipt, "review" if it looks like a payment but doesn't parse, or None to ignore."""
    provider = provider_of(sender)
    if not provider:
        return None
    text = f"{subject}\n{body}"
    if not PAYMENT_WORDS.search(subject):
        return None  # promos, security notices, statements ready...
    m = AMOUNT.search(subject) or AMOUNT.search(body)
    if not m:
        return "review"
    amount = float(m.group(1).replace(",", ""))
    card = LAST4.search(text)
    last4 = card.group(1) if card else None

    # A card purchase alert from the bank
    if provider == "Bank of America" and CARD_ALERT.search(subject) and "zelle" not in text.lower():
        merchant = MERCHANT.search(body)
        if merchant:
            return Receipt(provider, "out", amount, merchant.group(1).strip()[:60], None, last4, when)
        return "review"

    for direction, patterns in (("in", INCOMING), ("out", OUTGOING)):
        for pattern in patterns:
            hit = pattern.search(subject) or pattern.search(body)
            if hit:
                who = re.sub(r"\s+", " ", hit.group("who")).strip(" .")
                memo = MEMO.search(subject) or MEMO.search(body[:400])
                return Receipt(provider, direction, amount, who, memo.group(1).strip() if memo else None, last4, when)
    return "review"


def _account(receipt: Receipt, ctx: engine.Ctx) -> str:
    if receipt.provider != "Bank of America":
        return receipt.provider.lower().replace(" ", "")  # venmo, cashapp, paypal
    numbers = {str(k): v for k, v in (ctx.settings.get("card_numbers") or {}).items()}
    if receipt.last4 and receipt.last4 in numbers:
        return numbers[receipt.last4]
    if receipt.last4:
        for account in engine.card_accounts(ctx):
            if account.endswith(receipt.last4):
                return account
    checking = sorted({t.account for t in ctx.txns if t.account and t.account.startswith("checking_")})
    return checking[0] if checking else "checking"


def _connect() -> imaplib.IMAP4_SSL:
    if not (config.MAIL_USER and config.MAIL_PASSWORD):
        raise RuntimeError("set MAIL_USER and MAIL_PASSWORD (a Gmail app password)")
    imap = imaplib.IMAP4_SSL(config.MAIL_IMAP_HOST, timeout=30)
    imap.login(config.MAIL_USER, config.MAIL_PASSWORD)
    status, _ = imap.select(f'"{config.MAIL_FOLDER}"', readonly=True)
    if status != "OK":
        raise RuntimeError(f"no Gmail label called {config.MAIL_FOLDER!r}")
    return imap


def _fetch(imap: imaplib.IMAP4_SSL, since_days: int):
    since = (date.today() - timedelta(days=since_days)).strftime("%d-%b-%Y")
    status, data = imap.uid("search", None, f"(SINCE {since})")
    for uid in (data[0].split() if status == "OK" and data and data[0] else []):
        status, parts = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK" or not parts or not isinstance(parts[0], tuple):
            continue
        msg = email.message_from_bytes(parts[0][1], policy=default_policy)
        try:
            when = parsedate_to_datetime(msg["Date"]).astimezone().date()
        except Exception:
            when = date.today()
        yield msg, when


def preview(since_days: int = 14) -> list[tuple]:
    imap = _connect()
    try:
        out = []
        for msg, when in _fetch(imap, since_days):
            body = _text(msg)
            result = parse(msg["From"] or "", msg["Subject"] or "", body, when)
            out.append((when, msg["From"], msg["Subject"], result))
        return out
    finally:
        imap.logout()


def check() -> dict:
    """Log new payment emails. Safe to run any time: each email is handled once."""
    from .importer import _reconcile

    counts = {"logged": 0, "review": 0, "ignored": 0}
    try:
        imap = _connect()
    except Exception as exc:
        _state(error=str(exc))
        raise
    try:
        ctx = engine.load()
        with Session.begin() as s:
            seen = set(s.scalars(select(MailSeen.message_id)))
            new_rows: list[Txn] = []
            for msg, when in _fetch(imap, config.MAIL_SINCE_DAYS):
                msg_id = (msg["Message-ID"] or f"{msg['Date']}|{msg['Subject']}").strip()[:250]
                if msg_id in seen:
                    continue
                seen.add(msg_id)
                result = parse(msg["From"] or "", msg["Subject"] or "", _text(msg), when)
                row = MailSeen(message_id=msg_id, received=when, sender=(msg["From"] or "")[:200], subject=(msg["Subject"] or "")[:300])
                if isinstance(result, Receipt):
                    amount = result.amount if result.direction == "in" else -result.amount
                    desc = result.description
                    category, _ = rules.categorize(desc, "reimbursement" if result.direction == "in" else None, when, amount)
                    txn = Txn(date=when, amount=amount, description=desc, category=category, account=_account(result, ctx),
                              source="email", ref=f"email:{msg_id}"[:160], note=result.memo)
                    s.add(txn)
                    s.flush()
                    new_rows.append(txn)
                    row.status, row.txn_id = "logged", txn.id
                    counts["logged"] += 1
                else:
                    row.status = result or "ignored"
                    counts["review" if result == "review" else "ignored"] += 1
                s.add(row)
            # A payment you also logged by hand (Got Paid Back, Log Expense) becomes one entry.
            counts["matched"] = _reconcile(s, new_rows)
        _state(error=None, **counts)
        return counts
    finally:
        imap.logout()


def _state(**fields) -> None:
    with Session.begin() as s:
        row = s.get(Setting, "mail_state") or Setting(key="mail_state", value={})
        row.value = {**(row.value or {}), **fields, "last_check": datetime.now().isoformat(timespec="seconds")}
        s.merge(row)


def status() -> dict:
    with Session() as s:
        state = (s.get(Setting, "mail_state") or Setting(value={})).value or {}
        recent = s.scalars(select(MailSeen).where(MailSeen.status != "ignored").order_by(MailSeen.received.desc()).limit(25)).all()
        return {
            "configured": bool(config.MAIL_USER and config.MAIL_PASSWORD),
            "folder": config.MAIL_FOLDER,
            "state": state,
            "recent": [{"date": m.received.isoformat(), "from": m.sender, "subject": m.subject, "status": m.status} for m in recent],
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    if args.check:
        print(check())
        return
    for when, sender, subject, result in preview(args.days):
        if result is None:
            continue
        shown = result if isinstance(result, str) else f"{'+' if result.direction == 'in' else '-'}${result.amount:,.2f}  {result.description}" + (f"  ({result.memo})" if result.memo else "")
        print(f"{when}  {parseaddr(sender)[1]:32}  {subject[:60]:60}  ->  {shown}")


if __name__ == "__main__":
    main()
