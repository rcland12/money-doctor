"""Bank sync through SimpleFIN Bridge (https://beta-bridge.simplefin.org).

  1. You link your bank at SimpleFIN and create a one-time *setup token*.
  2. claim() trades it for an *access URL* (a private credential, kept in the
     database, never logged). A setup token works once.
  3. sync() pulls transactions and balances a few times a day.

Transactions become regular imports: categorized by the same rules, matched
to anything you logged by hand, and never duplicated against CSV exports you
uploaded earlier (a bank row already imported from a CSV is recognized by
account, amount and date).
"""

import base64
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ingest import rules

from . import engine
from .models import Debt, DebtBalance, SavingsGoal, Session, Setting, Txn

KEY = "simplefin"
# SimpleFIN's edge turns away Python's default User-Agent with a 403.
UA = {"User-Agent": "MoneyDoctor/0.1 (+self-hosted budgeting app)"}
SYNC_DAYS = 40  # how far back each sync looks (SimpleFIN recommends at most 45); overlap is harmless


def _get() -> dict:
    with Session() as s:
        row = s.get(Setting, KEY)
        return dict(row.value) if row and row.value else {}


def _put(**fields) -> dict:
    with Session.begin() as s:
        row = s.get(Setting, KEY) or Setting(key=KEY, value={})
        value = {**(row.value or {}), **fields}
        row.value = value
        s.merge(row)
    return value


def claim(setup_token: str) -> dict:
    """Exchange a setup token for the access URL. Works once per token."""
    try:
        claim_url = base64.b64decode(setup_token.strip()).decode().strip()
    except Exception:
        raise ValueError("That doesn't look like a SimpleFIN setup token (it should be one long line of letters and numbers).")
    if not claim_url.startswith("https://"):
        raise ValueError("That doesn't look like a SimpleFIN setup token.")
    req = urllib.request.Request(claim_url, data=b"", method="POST", headers={"Content-Length": "0", **UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            access = resp.read().decode().strip()
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise ValueError("SimpleFIN rejected this token: it was already used, or part of it is missing. Create a new setup token and paste the whole thing.")
        raise
    _put(access_url=access, connected_at=datetime.now().isoformat(timespec="seconds"), error=None)
    return status()


def _fetch(access_url: str, start: date) -> dict:
    parts = urllib.parse.urlsplit(access_url)
    auth = base64.b64encode(f"{urllib.parse.unquote(parts.username or '')}:{urllib.parse.unquote(parts.password or '')}".encode()).decode()
    base = urllib.parse.urlunsplit((parts.scheme, parts.hostname + (f":{parts.port}" if parts.port else ""), parts.path, "", ""))
    query = urllib.parse.urlencode({"start-date": int(datetime.combine(start, datetime.min.time()).timestamp())})
    req = urllib.request.Request(f"{base.rstrip('/')}/accounts?{query}", headers={"Authorization": f"Basic {auth}", **UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _map(account: dict, known: set[str], debts: list[Debt], manual: dict) -> str | None:
    """Our account key for a SimpleFIN account: set by hand, or by its last 4 digits."""
    if account["id"] in manual:
        return manual[account["id"]] or None
    digits = re.findall(r"(\d{4})\D*$", account.get("name", "")) or re.findall(r"\d{4}", account.get("name", ""))
    if not digits:
        return None
    last4 = digits[-1]
    for key in sorted(known):
        if key.endswith("_" + last4):
            return key
    for d in debts:
        if d.last4 == last4:
            return f"credit_card_{last4}" if d.kind == "credit_card" else f"debt:{d.key}"
    return None


def sync() -> dict:
    state = _get()
    if not state.get("access_url"):
        raise RuntimeError("SimpleFIN isn't connected yet")
    try:
        data = _fetch(state["access_url"], date.today() - timedelta(days=SYNC_DAYS))
    except Exception as exc:
        _put(error=f"sync failed: {exc.__class__.__name__}", last_sync=datetime.now().isoformat(timespec="seconds"))
        raise

    from .importer import _reconcile

    rules.personal_rules.cache_clear()
    ctx = engine.load()
    manual = state.get("mapping") or {}
    added = skipped = 0
    seen_accounts = []
    with Session.begin() as s:
        known = {a for a in s.scalars(select(Txn.account).where(Txn.source == "import").distinct()) if a}
        debts = list(s.scalars(select(Debt)))
        new_rows: list[Txn] = []
        for acct in data.get("accounts", []):
            key = _map(acct, known, debts, manual)
            balance = float(acct.get("balance") or 0)
            as_of = date.fromtimestamp(int(acct.get("balance-date") or datetime.now().timestamp()))
            available = acct.get("available-balance")
            seen_accounts.append({"id": acct["id"], "name": acct.get("name"), "org": (acct.get("org") or {}).get("name"),
                                  "balance": balance, "available": float(available) if available not in (None, "") else None,
                                  "as_of": as_of.isoformat(), "mapped_to": key})
            if not key:
                continue

            # Balances: debts (cards, loans) and savings goals follow the bank.
            debt_key = key[5:] if key.startswith("debt:") else next((d.key for d in debts if d.kind == "credit_card" and key == f"credit_card_{d.last4}"), None)
            if debt_key and not s.scalar(select(DebtBalance).where(DebtBalance.debt_key == debt_key, DebtBalance.as_of == as_of)):
                s.add(DebtBalance(debt_key=debt_key, as_of=as_of, balance=abs(balance), source="simplefin"))
            for goal in s.scalars(select(SavingsGoal).where(SavingsGoal.account == key)):
                goal.balance = balance
            if key.startswith("debt:"):
                continue  # loans: balance only

            existing = s.scalars(select(Txn).where(Txn.account == key, Txn.date >= date.today() - timedelta(days=SYNC_DAYS + 5))).all()
            by_ref = {t.ref: t for t in existing}
            claimed: set[int] = set()
            for t in sorted(acct.get("transactions", []), key=lambda t: t.get("posted", 0)):
                if t.get("pending"):
                    continue  # posted only: pending amounts and ids can change
                ref = f"sfin:{key}:{t['id']}"[:160]
                if ref in by_ref:
                    claimed.add(by_ref[ref].id)  # so a same-amount twin isn't mistaken for it
                    continue
                amount = float(t["amount"])
                when = date.fromtimestamp(int(t.get("transacted_at") or t["posted"]))
                # Already here from a CSV, a statement, or before the bank was re-linked in
                # SimpleFIN (which can change transaction ids)? Same account, amount, within 3 days.
                twin = next((e for e in existing if e.source == "import" and e.id not in claimed
                             and abs(e.amount - amount) < 0.005 and abs((e.date - when).days) <= 3), None)
                if twin:
                    claimed.add(twin.id)
                    skipped += 1
                    continue
                description = (t.get("description") or t.get("payee") or "").strip()
                category, _ = rules.categorize(description, None, when, amount)
                row = Txn(date=when, amount=amount, description=description, category=category, account=key,
                          source="import", ref=ref, note=(t.get("memo") or None))
                s.add(row)
                new_rows.append(row)
                added += 1
        s.flush()
        matched = _reconcile(s, new_rows)
    _put(last_sync=datetime.now().isoformat(timespec="seconds"), accounts=seen_accounts,
         errors=data.get("errors") or [], error=None)
    return {"added": added, "already_had": skipped, "matched_to_logged": matched, "errors": data.get("errors") or []}


def set_mapping(account_id: str, key: str | None) -> dict:
    mapping = {**(_get().get("mapping") or {}), account_id: key}
    _put(mapping=mapping)
    return status()


def disconnect() -> dict:
    _put(access_url=None, connected_at=None)
    return status()


def status() -> dict:
    state = _get()
    return {
        "connected": bool(state.get("access_url")),
        "connected_at": state.get("connected_at"),
        "last_sync": state.get("last_sync"),
        "error": state.get("error"),
        "errors": state.get("errors") or [],
        "accounts": state.get("accounts") or [],
    }
