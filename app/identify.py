"""Work out what an uploaded file is, and which account it belongs to, from its
contents: so a Bank of America export named `stmt.csv` still lands in the
right place, and a card export can never be filed as checking.

Order of evidence: the file name (credit_card_1234...), then the file's
transactions matched against ones already imported, then (cards) the
confirmation code of a payment, which checking's copy of that payment
records together with the card number.
"""

import csv
import io
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from ingest import boa_csv, boa_statement, paystub

from . import engine
from .models import Session, Txn

CARD_TAIL = re.compile(r"_(\d{4})\.csv$", re.I)
CONF = re.compile(r"CONF(?:IRMATION)?#\s*([A-Za-z0-9]{6,})", re.I)


def _known() -> tuple[dict[str, str], dict[str, str], list[Txn]]:
    """(import ref -> account, account -> display name, checking payment rows)."""
    ctx = engine.load()
    with Session() as s:
        refs = {ref: acct for ref, acct in s.execute(select(Txn.ref, Txn.account).where(Txn.source == "import", Txn.ref.is_not(None)))}
        payments = s.scalars(select(Txn).where(Txn.source == "import", Txn.description.ilike("%CRD%"))).all()
    names = {f"credit_card_{d.last4}": d.name for d in ctx.debts if d.last4 and d.kind == "credit_card"}
    for acct in set(refs.values()):
        names.setdefault(acct, acct.replace("_", " ").title())
    return refs, names, payments


def _by_overlap(keys: list[str], refs: dict[str, str], prefix: str) -> str | None:
    """The account whose already-imported refs share the most keys with this file."""
    votes = Counter()
    for key in keys:
        for acct in {a for a in refs.values() if a.startswith(prefix)}:
            if f"{acct}:{key}" in refs:
                votes[acct] += 1
    return votes.most_common(1)[0][0] if votes else None


def identify(path: Path) -> dict:
    refs, names, payments = _known()
    name = path.name
    out = {"file": name, "kind": "unknown", "label": "Not a file Money Doctor reads", "account": None, "how": None,
           "choices": [], "ok": False}
    suffix = path.suffix.lower()

    if suffix == ".xlsx":
        return {**out, "kind": "household", "label": "Household spreadsheet", "ok": True}

    if suffix == ".pdf":
        if paystub.matches(path):
            return {**out, "kind": "pay", "label": "Pay statement", "ok": True}
        if boa_statement.is_statement(path):
            st = boa_statement.parse(path)
            acct = f"credit_card_{st.account_last4}" if st.account_last4 else None
            return {**out, "kind": "statement", "label": f"{names.get(acct, 'Card')} statement", "account": acct,
                    "how": "read from the statement", "ok": True}
        return {**out, "kind": "pdf", "label": "PDF (will be read with a model if one is set up)", "ok": True}

    if suffix != ".csv" or not boa_csv.is_boa_csv(path):
        return out

    text = path.read_text(errors="replace")
    in_name = boa_csv.NAME.search(name)

    if text.startswith("Posted Date,Reference Number,Payee"):
        base = {**out, "kind": "card_csv", "label": "Card transactions",
                "choices": [{"key": a, "name": n} for a, n in names.items() if a.startswith("credit_card_")]}
        rows = list(csv.DictReader(io.StringIO(text)))
        acct, how = None, None
        if in_name and in_name.group(1).lower() == "credit_card":
            acct, how = f"credit_card_{in_name.group(2)}", "from the file name"
        elif (tail := CARD_TAIL.search(name)) and f"credit_card_{tail.group(1)}" in names:
            acct, how = f"credit_card_{tail.group(1)}", "from the file name"
        if not acct:
            keys = [r["Reference Number"].strip() for r in rows if r.get("Reference Number", "").strip()]
            if acct := _by_overlap(keys, refs, "credit_card_"):
                how = "matched transactions you already have"
        if not acct:  # a payment's confirmation code, as recorded on checking's side
            for r in rows:
                code = CONF.search(r.get("Payee", ""))
                hit = code and next((p for p in payments if code.group(1).lower() in p.description.lower()), None)
                card = hit and re.search(r"CRD\s*(\d{4})", hit.description)
                if card:
                    acct, how = f"credit_card_{card.group(1)}", "matched a payment to this card"
                    break
        if acct:
            base.update(account=acct, how=how, label=f"{names.get(acct, acct)} transactions", ok=True)
        return base

    # Checking / savings export with a running balance
    base = {**out, "kind": "deposit_csv", "label": "Checking or savings transactions",
            "choices": [{"key": a, "name": n} for a, n in names.items() if a.startswith(("checking_", "savings_"))]}
    acct, how = None, None
    if in_name and in_name.group(1).lower() in ("checking", "savings"):
        acct, how = f"{in_name.group(1).lower()}_{in_name.group(2)}", "from the file name"
    if not acct:
        _, _, body = text.partition("\n\n")
        keys = []
        for r in csv.DictReader(io.StringIO(body.strip())):
            if r.get("Amount", "").strip() and r.get("Running Bal.", "").strip():
                amount = float(r["Amount"].replace(",", "").replace('"', ""))
                keys.append(f"{r['Date']}|{amount}|bal:{r['Running Bal.'].strip()}")
        if acct := _by_overlap(keys, refs, ("checking_", "savings_")):
            how = "matched transactions you already have"
    if acct:
        base.update(account=acct, how=how, label=f"{names.get(acct, acct)} transactions", ok=True)
    return base
