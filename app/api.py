"""HTTP API. /api/v1/* serves both the website (session) and Shortcuts (bearer token)."""

import asyncio
import datetime as dt
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select


from . import config, digest, engine, ical, importer, mail, seed, simplefin
from .auth import check_password, new_token, require_user
from .models import ApiToken, BillPaid, DebtBalance, Line, Session, Setting, Txn

router = APIRouter(prefix="/api")
v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_user)])


# ---------------------------------------------------------------- auth
class Login(BaseModel):
    password: str


@router.post("/auth/login")
def login(body: Login, request: Request):
    if not check_password(body.password):
        raise HTTPException(401, "Wrong password")
    request.session["user"] = "owner"
    return {"ok": True}


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/calendar.ics", include_in_schema=False)
def calendar_feed(key: str | None = None):
    """The subscribed-calendar feed. Calendar apps can't log in, so the secret key is the access."""
    from fastapi.responses import Response

    if not ical.valid(key):
        raise HTTPException(404)
    return Response(ical.feed(config.PUBLIC_URL), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "no-store"})


@router.get("/auth/me")
def me(request: Request):
    try:
        require_user(request)
    except HTTPException:
        return {"user": None, "mode": config.AUTH_MODE}
    return {"user": "owner", "mode": config.AUTH_MODE}


# ---------------------------------------------------------------- quick log (Shortcut)
class LogIn(BaseModel):
    amount: float | str = Field(description="Positive = money spent; '$1,234.56' strings are fine (Wallet sends those)")
    category: str = Field("auto", description="A Shortcut label, e.g. 'Groceries', a line key, or 'auto' to use the merchant")
    merchant: str | None = None
    card: str | None = Field(None, description="Wallet card name from the Apple Pay automation (Card or Pass)")
    note: str | None = None
    date: dt.date | None = None
    refund: bool = False
    account: str | None = None


def _find_line(label: str) -> Line:
    wanted = label.strip().lower()
    with Session() as s:
        for ln in s.scalars(select(Line)):
            if wanted in {ln.key.lower(), ln.name.lower(), (ln.shortcut or "").lower()}:
                return ln
    raise HTTPException(404, f"No budget line called {label!r}")


def _line_message(ln: Line, amount: float, today: date, verb: str | None = None) -> dict:
    """A one-line reply for the phone: what happened and where the line stands."""
    status = next(r for r in engine.line_status(engine.load(today), engine.month_of(today)) if r["key"] == ln.key)
    name = "Personal" if ln.private else ln.name
    if verb is None:
        verb = f"Recorded ${abs(amount):,.2f} paid back to {name}." if amount > 0 else f"Logged ${abs(amount):,.2f} to {name}."
    parts = [verb]
    if status["target"] > 0:
        left = status["remaining"]
        month = today.strftime("%B")
        if left >= 0:
            days_left = (engine.month_bounds(engine.month_of(today))[1] - today).days + 1
            per_day = f" (${left / days_left:,.2f} a day)" if ln.kind == "variable" and left > 0 else ""
            parts.append(f"${left:,.2f} left for {month}{per_day}.")
        else:
            parts.append(f"The line is ${-left:,.2f} over for {month}.")
    return {"message": " ".join(parts), "line": ln.key, "remaining": status["remaining"], "spent": status["spent"]}


def _parse_amount(v: float | str) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    cleaned = re.sub(r"[^\d.\-]", "", v.replace(",", ""))
    if not cleaned:
        raise HTTPException(400, f"Can't read an amount from {v!r}")
    return float(cleaned)


def _auto_line(merchant: str | None, amount: float = -1.0) -> Line | None:
    """Pick a line from the merchant name with the same rules the bank import uses."""
    if not merchant:
        return None
    from ingest import rules

    category, _ = rules.categorize(merchant)
    ctx = engine.load()
    probe = Txn(date=ctx.today, amount=amount, description=merchant, category=category)
    key, _ = engine.resolve_line(ctx, probe)
    return ctx.by_key.get(key) if key else None


def _wallet_account(card: str | None) -> str | None:
    """Map a Wallet card name to an account key, via `wallet_cards` in the budget
    file ({"name contains": "credit_card_1234"}) or a last-4 in the name."""
    if not card:
        return None
    ctx = engine.load()
    for needle, account in (ctx.settings.get("wallet_cards") or {}).items():
        if needle.lower() in card.lower():
            return account
    digits = re.findall(r"\d{4}", card)
    for account in engine.card_accounts(ctx):
        if digits and account.endswith(digits[-1]):
            return account
    return f"wallet:{card[:40]}"


@v1.post("/tx")
def log_tx(body: LogIn):
    when = body.date or date.today()
    value = _parse_amount(body.amount)
    # Money coming back (a friend paying you back, a return): refund=true or a negative amount.
    amount = abs(value) if (body.refund or value < 0) else -abs(value)
    label = body.category.strip().lower()
    auto = label == "auto"
    if auto:
        ln = _auto_line(body.merchant, amount)
    else:
        ln = None if label == "other" else _find_line(body.category)
    if auto:
        from ingest import rules

        category = rules.categorize(body.merchant or "")[0]
    else:
        category = ln.tracks[0] if ln and ln.tracks else "other"
    with Session.begin() as s:
        s.add(Txn(date=when, amount=amount, description=body.merchant or body.note or (ln.name if ln else "Other"),
                  category=category, line_key=None if auto else (ln.key if ln else None),
                  account=body.account or _wallet_account(body.card) or "logged", source="shortcut", note=body.note))
    if not ln:
        return {"message": f"Logged ${abs(amount):,.2f} as Other. Assign it a budget line on the website.", "line": None}
    return _line_message(ln, amount, when)


class FixIn(BaseModel):
    category: str


@v1.post("/fix")
def fix_last(body: FixIn):
    """Move the most recent logged entry to another budget line (for when Apple Pay guesses wrong)."""
    ln = _find_line(body.category)
    with Session.begin() as s:
        row = s.scalar(select(Txn).where(Txn.source == "shortcut").order_by(Txn.created_at.desc()))
        if not row:
            raise HTTPException(404, "Nothing logged to fix")
        row.line_key = ln.key
        amount, desc, when = row.amount, row.description, row.date
    return _line_message(ln, amount, when, f"Moved {desc} (${abs(amount):,.2f}) to {'Personal' if ln.private else ln.name}.")


@v1.post("/undo")
@v1.delete("/tx/last")
def undo_last():
    with Session.begin() as s:
        row = s.scalar(select(Txn).where(Txn.source == "shortcut").order_by(Txn.created_at.desc()))
        if not row:
            raise HTTPException(404, "Nothing to undo")
        msg = f"Removed ${abs(row.amount):,.2f} ({row.description})."
        s.delete(row)
    return {"message": msg}


@v1.get("/setup")
def setup_info():
    """What the iPhone setup page needs to fill in the Shortcut steps."""
    return {"base": config.SHORTCUT_BASE, "auth": config.SHORTCUT_AUTH, "site": config.PUBLIC_URL}


@v1.get("/categories")
def categories():
    """The Shortcut's menu, in budget order."""
    with Session() as s:
        month = engine.month_of(date.today())
        labels = [ln.shortcut for ln in s.scalars(select(Line).order_by(Line.sort)) if ln.shortcut and ln.active(month)]
    return {"categories": labels if "Other" in labels else labels + ["Other"]}


@v1.get("/summary")
def summary():
    """What Siri reads out: today's spending room, the next payments, and the payoff date."""
    db = engine.dashboard()
    lines = [f"Safe to spend today: ${db['safe']['total_per_day']:,.2f}."]
    upcoming = [p for p in db["payments"] if not p["paid"] and p["kind"] != "transfer"][:3]
    if upcoming:
        when = lambda iso: "today" if iso == db["today"] else date.fromisoformat(iso).strftime("%b %-d")
        lines.append("Next payments: " + "; ".join(f"{p['name']} ${p['amount']:,.2f} {when(p['date'])}" for p in upcoming) + ".")
    p = db["projection"]
    if p["done"]:
        done = date.fromisoformat(p["done"] + "-01").strftime("%B %Y")
        lines.append(f"On track to pay off the cards by {done}." if p["on_track"] else f"Cards paid off by {done}, behind the target.")
    return {"message": "\n".join(lines), "safe_today": db["safe"]["total_per_day"]}


# ---------------------------------------------------------------- documents
def _run_ingest() -> str:
    """Parse new files, extract other PDFs if a backend is set, then import."""
    import subprocess
    import sys

    cmds = [[sys.executable, "-m", "ingest", "parse"]]
    if config.EXTRACT_BACKEND != "none":
        cmds += [[sys.executable, "-m", "ingest", "redact"], [sys.executable, "-m", "ingest", "extract", "--backend", config.EXTRACT_BACKEND]]
    cmds.append([sys.executable, "-m", "ingest", "summarize", "--quiet"])
    out = []
    for cmd in cmds:
        r = subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True, timeout=1200)
        out.append((r.stdout + r.stderr).strip().splitlines()[-1:] if (r.stdout or r.stderr) else [])
    return " / ".join(line for chunk in out for line in chunk)


async def _stage(files: list[UploadFile]) -> list[Path]:
    staged = []
    for f in files:
        tmp = config.INBOX_DIR / ".incoming" / Path(f.filename or "upload").name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        staged.append(tmp)
    return staged


@v1.post("/documents/inspect")
async def inspect_documents(files: list[UploadFile] = File(...)):
    """What each file is and which account it belongs to, before uploading."""
    from .identify import identify

    staged = await _stage(files)
    try:
        return [await asyncio.to_thread(identify, path) for path in staged]
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


@v1.post("/documents")
async def upload(files: list[UploadFile] = File(...), account: str | None = None, accounts: str | None = Form(None)):
    """Save files into the inbox, ingest them, and say what came in.

    Each file's account comes from its contents when that's certain (see
    app/identify.py). `accounts` (JSON {filename: account}) or `account` (one
    for all) is only used for files that can't be identified, and must match
    the file's kind: a card export can only go to a card."""
    from .identify import identify

    chosen = json.loads(accounts) if accounts else {}
    staged = await _stage(files)
    saved, problems = [], []
    for tmp in staged:
        info = await asyncio.to_thread(identify, tmp)
        name = tmp.name
        if info["kind"] == "unknown":
            problems.append(f"{name}: not a file Money Doctor reads")
            tmp.unlink(missing_ok=True)
            continue
        target = info["account"]
        if not target and info["kind"] in ("card_csv", "deposit_csv"):
            pick = chosen.get(name) or account
            allowed = {c["key"] for c in info["choices"]}
            if not pick:
                problems.append(f"{name}: which account is it? ({info['label']})")
                tmp.unlink(missing_ok=True)
                continue
            if pick not in allowed:
                problems.append(f"{name}: this is {info['label'].lower()}, so it can't go to {pick}")
                tmp.unlink(missing_ok=True)
                continue
            target = pick
        if info["kind"] in ("card_csv", "deposit_csv"):
            # The account goes in the name (the ingest reads it there), once.
            name = re.sub(r"(checking|savings|credit_card)_\d{4}_?", "", name, flags=re.I) or "export.csv"
            name = f"{target}_{name}"
            folder = "bank"
        else:
            folder = {"pay": "pay", "statement": "bank", "household": "household"}.get(info["kind"], "other")
        dest = config.INBOX_DIR / folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(tmp, dest)
        saved.append({"file": tmp.name, "saved_as": str(dest.relative_to(config.INBOX_DIR)), "label": info["label"]})
    if not saved:
        raise HTTPException(400, "; ".join(problems) or "nothing to upload")
    log = await asyncio.to_thread(_run_ingest)
    result = await asyncio.to_thread(importer.run)
    db = engine.dashboard()
    msg = f"Uploaded {len(saved)} file{'s' if len(saved) != 1 else ''}: {result['added']} new transaction{'' if result['added'] == 1 else 's'}"
    if result["matched_to_logged"]:
        msg += f", {result['matched_to_logged']} matched to entries you logged"
    msg += "."
    cards = [d for d in db["debts"] if d["kind"] == "credit_card"]
    if cards:
        msg += " Card balances: " + ", ".join(f"{c['name']} ${c['balance']:,.0f}" for c in cards) + "."
    if problems:
        msg += " Skipped: " + "; ".join(problems) + "."
    return {"message": msg, "saved": saved, "problems": problems, "ingest": log, "import": result}


# ---------------------------------------------------------------- website data
@v1.get("/accounts")
def accounts():
    """Bank accounts seen in imports, for the upload page's account picker."""
    ctx = engine.load()
    seen = sorted({t.account for t in ctx.txns if t.source == "import" and t.account})
    names = {f"credit_card_{d.last4}": d.name for d in ctx.debts if d.last4}
    return [{"key": a, "name": names.get(a, a.replace("_", " ").title())} for a in seen]


@v1.get("/dashboard")
def dashboard(day: date | None = None):
    return engine.dashboard(day)


@v1.get("/budget")
def budget(month: str | None = None):
    ctx = engine.load()
    month = month or engine.month_of(ctx.today)
    return {"month": month, "lines": engine.line_status(ctx, month), "cards_extra": engine.cards_extra(ctx, month),
            "income": ctx.income}


@v1.get("/transactions")
def transactions(month: str | None = None, line: str | None = None, q: str | None = None, limit: int = 500):
    ctx = engine.load()
    month = month or engine.month_of(ctx.today)
    first, last = engine.month_bounds(month)
    rows = []
    for t in reversed(ctx.txns):
        if not first <= t.date <= last:
            continue
        key, offset = engine.resolve_line(ctx, t)
        if line and key != line:
            continue
        if q and q.lower() not in t.description.lower() and q.lower() not in (t.note or "").lower():
            continue
        ln = ctx.by_key.get(key) if key else None
        rows.append({"id": t.id, "date": t.date.isoformat(), "amount": t.amount, "description": t.description,
                     "category": t.category, "line": key, "line_name": ln.name if ln else None, "offset": offset,
                     "pinned": bool(t.line_key), "account": t.account, "source": t.source, "note": t.note})
        if len(rows) >= limit:
            break
    return {"month": month, "transactions": rows,
            "lines": [{"key": ln.key, "name": ln.name} for ln in ctx.lines if ln.active(month)]}


class TxnPatch(BaseModel):
    line: str | None = None
    note: str | None = None
    remember: bool = False  # also add a merchant rule, so future ones from here get this line


@v1.patch("/transactions/{txn_id}")
def edit_txn(txn_id: int, body: TxnPatch):
    with Session.begin() as s:
        t = s.get(Txn, txn_id)
        if not t:
            raise HTTPException(404)
        if body.line is not None:
            t.line_key = body.line or None
        if body.note is not None:
            t.note = body.note
        description = t.description
    rule = None
    if body.remember and body.line:
        rule = _remember(description, body.line)
    return {"ok": True, "rule": rule}


def _remember(description: str, line_key: str) -> str | None:
    """Add `MERCHANT KEY: category` to the merchant rules for this line's category."""
    from ingest import rules

    with Session() as s:
        ln = s.get(Line, line_key)
    if not ln or not ln.tracks:
        return None
    key = rules.merchant_key(description)
    path = rules.PERSONAL_RULES
    text = path.read_text() if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}\s*:.*$", re.M)
    entry = f"{key}: {ln.tracks[0]}"
    text = pattern.sub(entry, text) if pattern.search(text) else text.rstrip("\n") + f"\n{entry}                  # set from the website\n"
    path.write_text(text)
    rules.personal_rules.cache_clear()
    return entry


class ManualTxn(BaseModel):
    date: dt.date
    amount: float
    description: str
    line: str | None = None


@v1.post("/transactions")
def add_txn(body: ManualTxn):
    with Session.begin() as s:
        s.add(Txn(date=body.date, amount=body.amount, description=body.description, line_key=body.line,
                  source="manual", account="manual"))
    return {"ok": True}


class CardPaymentIn(BaseModel):
    account: str
    amount: float
    date: dt.date | None = None


@v1.post("/card-payments")
def mark_card_payment(body: CardPaymentIn):
    """Record a card payment you've just sent. It counts right away; when the
    bank shows the payment, the bank's row replaces this one."""
    ctx = engine.load()
    card = engine.card_accounts(ctx).get(body.account)
    if not card:
        raise HTTPException(400, "Unknown card.")
    if not 0 < body.amount < 100000:
        raise HTTPException(400, "Enter the amount you sent.")
    with Session.begin() as s:
        s.add(Txn(date=body.date or ctx.today, amount=round(body.amount, 2), description=f"Payment to {card.name} (marked on the site)",
                  category="debt_payment", source="manual", account=body.account, note="Waiting for the bank to show it"))
    return {"ok": True, "message": f"Marked ${body.amount:,.2f} sent to {card.name}."}


@v1.delete("/transactions/{txn_id}")
def delete_txn(txn_id: int):
    with Session.begin() as s:
        t = s.get(Txn, txn_id)
        if not t or t.source == "import":
            raise HTTPException(400, "Only logged or manual entries can be deleted")
        s.delete(t)
    return {"ok": True}


@v1.post("/bills/{line_key}/paid")
def mark_paid(line_key: str, month: str | None = None):
    month = month or engine.month_of(date.today())
    with Session.begin() as s:
        s.add(BillPaid(line_key=line_key, month=month, paid_on=date.today()))
    return {"ok": True}


class BalanceIn(BaseModel):
    balance: float
    as_of: dt.date | None = None


@v1.post("/debts/{key}/balance")
def set_balance(key: str, body: BalanceIn):
    with Session.begin() as s:
        s.add(DebtBalance(debt_key=key, as_of=body.as_of or date.today(), balance=body.balance, source="manual"))
    return {"ok": True}


@v1.post("/assets/{key}/balance")
def set_asset_balance(key: str, body: BalanceIn):
    """Update an investment's balance by hand (for ones bank sync doesn't cover)."""
    with Session.begin() as s:
        row = s.get(Setting, "asset_balances") or Setting(key="asset_balances", value={})
        row.value = {**(row.value or {}), key: {"balance": body.balance, "as_of": (body.as_of or date.today()).isoformat()}}
        s.merge(row)
    return {"ok": True}


@v1.get("/income")
def income_report(year: int | None = None):
    """A year of pay: gross, deductions, net, leave, and other money in."""
    from . import income
    return income.income(year)


@v1.get("/recurring")
def recurring():
    """Every recurring payment, with how often, when, and how to pay it."""
    return engine.recurring(engine.load())


@v1.get("/calendar")
def calendar(days: int = 42):
    """Day by day: money in, payments out, expected spending, and checking's projected balance."""
    return engine.forecast(engine.load(), min(max(days, 7), 120))


@v1.get("/calendar/link")
def calendar_link():
    return {"url": f"{config.PUBLIC_URL}/api/calendar.ics?key={ical.link_key()}"}


@v1.post("/calendar/link/reset")
def calendar_link_reset():
    return {"url": f"{config.PUBLIC_URL}/api/calendar.ics?key={ical.link_key(reset=True)}"}


@v1.get("/tokens")
def tokens():
    with Session() as s:
        return [{"id": t.id, "name": t.name, "created_at": t.created_at, "last_used": t.last_used}
                for t in s.scalars(select(ApiToken))]


class TokenIn(BaseModel):
    name: str


@v1.post("/tokens")
def create_token(body: TokenIn):
    return {"token": new_token(body.name), "note": "Shown once. Paste it into the Shortcut now."}


@v1.delete("/tokens/{token_id}")
def revoke_token(token_id: int):
    with Session.begin() as s:
        s.execute(delete(ApiToken).where(ApiToken.id == token_id))
    return {"ok": True}


@v1.post("/digest/send")
def send_digest():
    return {"message": digest.send(force=True)}


@v1.get("/digest/preview")
def preview_digest(day: date | None = None):
    subj, text, html = digest.render(day)
    return {"subject": subj, "text": text, "html": html}


@v1.get("/simplefin")
def simplefin_status():
    return simplefin.status()


class SetupToken(BaseModel):
    token: str


@v1.post("/simplefin/claim")
async def simplefin_claim(body: SetupToken):
    try:
        state = await asyncio.to_thread(simplefin.claim, body.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Couldn't reach SimpleFIN: {exc.__class__.__name__}")
    try:
        state["sync"] = await asyncio.to_thread(simplefin.sync)
    except Exception as exc:
        state["sync_error"] = str(exc)
    return {**simplefin.status(), "sync": state.get("sync"), "sync_error": state.get("sync_error")}


@v1.post("/simplefin/sync")
async def simplefin_sync():
    try:
        return await asyncio.to_thread(simplefin.sync)
    except Exception as exc:
        raise HTTPException(502, f"Sync failed: {exc}")


class Mapping(BaseModel):
    account_id: str
    key: str | None = None


@v1.post("/simplefin/map")
def simplefin_map(body: Mapping):
    return simplefin.set_mapping(body.account_id, body.key)


@v1.post("/simplefin/disconnect")
def simplefin_disconnect():
    return simplefin.disconnect()


@v1.get("/mail")
def mail_status():
    return mail.status()


@v1.post("/mail/check")
async def mail_check():
    try:
        return {"ok": True, **(await asyncio.to_thread(mail.check))}
    except Exception as exc:
        raise HTTPException(502, f"Couldn't read the mailbox: {exc}")


@v1.post("/reload")
def reload_budget():
    seed.seed()
    return {"ok": True, "import": importer.run(), "at": datetime.now().isoformat()}


router.include_router(v1)
