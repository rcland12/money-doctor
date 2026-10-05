# CLAUDE.md

Guide for Claude Code sessions working on Money Doctor. The user-facing docs
are [README.md](README.md) (setup, deploy, config),
[docs/budget-reference.md](docs/budget-reference.md) (every budget.yaml key) and
[ingest/README.md](ingest/README.md). A person's own setup notes, if any, are
in `CLAUDE.local.md` (git-ignored, loaded automatically when present).

Sessions are usually one of two things: helping someone **run their own
copy** (set it up, write their budget, check in on it), or **changing the
code**. For the first, use the skills in `.claude/skills/`:

| Skill | For |
|---|---|
| `setup` | First deployment: `.env`, compose profiles (email, tunnel, sso), first login, Shortcuts, bank sync |
| `budget` | Write or change `data/budget.yaml` from an interview or their documents, then check it |
| `checkin` | How the month is going, whether the payoff is on track, what to adjust |
| `categorize` | Teach it merchants that land in "other" |
| `paystub-parser` | Write `ingest/paystub_local.py` for their employer's pay statement |
| `privacy-check` | Before a commit or push: make sure no personal data is in tracked files |

## Working with someone's own money

- Their data is in `data/` (and `inbox/`). It's real: names, balances,
  account numbers. Read it to help them, but never copy it into tracked files,
  and don't repeat account numbers or passwords back in chat.
- Never ask for secrets in chat (passwords, app passwords, tunnel tokens,
  SimpleFIN tokens). Tell them which file and key to paste it into.
- Ask before anything that writes to their live instance: reload, `--send`,
  `app.mail --check`, uploads, token creation. Reading is fine.
- After any budget.yaml edit, run `python -m app.check` (or
  `docker compose exec money-doctor python -m app.check`) and fix errors before
  they reload. Explain the result in plain words: what's left over, where it
  goes, when the debt is gone.
- It's their plan. Suggest, show the trade-off in months and dollars, and let
  them decide. Not financial advice; don't judge spending.

## Ground rules

- **This repo is public.** Personal financial data never goes in a tracked
  file: no real names, account digits, balances, APRs, pay amounts, dates
  from someone's real plan, merchants that identify a place, email
  addresses or domains. Examples use obviously fake values (`Alex`, card
  `1111`, `example.com`, round numbers). Real data lives in git-ignored paths:
  `data/`, `inbox/`, `intake/*.yaml`, `.env`, `PLAN.md`, `CLAUDE.local.md`,
  `compose.yml`, `ingest/paystub_local.py`, `data/merchant-patterns.yaml`.
- Keep built-in rules and examples generic: national chains only, no regional
  utilities or local businesses, nothing that points to a specific employer
  or employer type. Those belong in `data/merchant-patterns.yaml` or `paystub_local.py`.
  Deployment secrets live in `.env` and `deploy/*.env`, also git-ignored.
- Before suggesting a commit or push, grep the changes for personal values.
- UI, email and notification copy: plain text, no emoji. Icons are line icons
  from `web/src/lib/components/Icon.svelte`.
- Match the existing style: short module docstrings that start with what the
  module does and show its CLI usage, compact code, few comments that explain why.
- There's no test suite. Check changes by running the relevant CLI (see
  Commands) and, for the site, `npm run check` and a quick look in the browser.

## What it is

A self-hosted, single-user budgeting app for paying off debt. It has one
container (FastAPI + SQLite + a static SvelteKit build) and one data
directory. Data comes in from:

1. **iPhone Shortcuts** calling `/api/v1/tx` (manual and Apple Pay automation)
2. **SimpleFIN Bridge** bank sync (every 6 hours)
3. **Payment emails** (Venmo, Cash App, PayPal, BoA alerts) read from a Gmail label over IMAP
4. **Uploaded documents** (BoA CSVs and statements, pay statements,
   a shared-house .xlsx, other PDFs via a model), through the website or a share-sheet Shortcut

It answers: what can I spend today, what's due, what should each paycheck do,
and when is the debt gone. It sends a morning email with that.

## Architecture

```
iPhone Shortcuts ─┐                        ┌─ app/engine.py (all budget math, read-only)
Website (web/) ───┼─> FastAPI app/api.py ──┤
                  │   /api/v1/* (auth)     └─ SQLite data/money.db (app/models.py)
                  │                               ▲
data/budget.yaml ─┴─ app/seed.py on start ────────┤ lines, debts, events, settings
SimpleFIN ────────── app/simplefin.py ────────────┤ transactions, balances
Gmail label ──────── app/mail.py ─────────────────┤ transactions
Uploads ─> inbox/ ─> ingest/ (subprocess) ─> data/ingest/*.json ─> app/importer.py
                                                  │
app/digest.py <── scheduler in app/main.py ───────┘ morning email via SMTP
```

`app/main.py` starts three background loops in the FastAPI lifespan:
the digest (sleeps until `digest.send_at` in the budget's timezone), the mail
check (only when `MAIL_USER`/`MAIL_PASSWORD` are set, every `MAIL_POLL_SECONDS`),
and SimpleFIN sync (when connected, every 6 h). On start it runs
`init_db()`, `seed.seed()`, then `importer.run()`. It serves `web/build`
with an SPA fallback to `index.html`.

## The budget model

`data/budget.yaml` is the **source of truth** (format: `config/budget.example.yaml`;
if the file is missing, the example is loaded). `seed.seed()` runs on every start and
on `POST /api/v1/reload`. It **replaces** lines, events and savings goals, and
upserts debts (removing ones no longer in the file). **Transactions and debt
balance history are kept.** Top-level keys copied into the `settings` table:
`owner, timezone, income, plan, digest, wallet_cards, paid_with, card_numbers,
small_purchases, assets, cash, cash_bills, recurring, autopay`.

- **income**: `paycheck_net` (base, no overtime), `pay_anchor` (any payday),
  `pay_every_days`, `budget_paychecks` (usually 2). `engine.paydays()` steps from the anchor.
- **lines**: `kind` is `variable | bill | fund | savings`.
  - `tracks`: transaction categories that count against the line. `offsets`:
    categories that reduce its spending (e.g. roommates paying back rent).
    `match`: description substrings, checked before `tracks`, upper-cased on seed.
  - `bill`: `due_day`, optional `due_amount`. It counts as paid at 90% of the
    amount in outgoing matches, or when marked paid (`bills_paid` table).
  - `fund`: running balance = `start_balance` + monthly contributions since
    `plan.start` (or `from`) − spending.
  - `pay_from`: which paycheck of the month (1 or 2) covers it.
  - `from`/`until` (YYYY-MM) set when the line is active. `shortcut` puts it in the
    Shortcut menu. `private` shows it as "Personal". `debt` links a minimum-payment line to a debt.
- **cards_extra** = `paycheck_net × budget_paychecks − sum(active line amounts)`.
  It goes to `top_debt()` (the highest APR whose `payoff_order` isn't `last`).
- **plan.third_paycheck**: per-month rules for months with an extra payday:
  `{month, emergency_fund, rest: cards}` or `{month, split: {cards, life_happens}}`.
  The default is a 50/50 split.
- **projection()**: monthly avalanche starting the month after the latest
  balance `as_of`. Interest, then minimums (max of $35 or 1% + interest), then
  everything to the highest APR. Up to 120 months. Compared with `plan.target_payoff`.
- **safe_to_spend()**: each variable line's remaining amount ÷ days left in the month.
- **due_soon()** only calls a bill late once bank data covers its due date
  (`freshness()`), so a sync lag doesn't look like a missed payment.
- Only avalanche is implemented, even though `plan.strategy` exists.

### How a transaction gets its line (`engine.resolve_line`)

`Txn.line_key` (set by hand or by the Shortcut) wins. After that, the first
line whose `match` substring is in the description (active lines first), then
the first active line that `tracks` the category, then `offsets`. Finally
`small_purchases` can move a small charge (e.g. under $15 on Gas becomes Dining).

### How a transaction gets its category (`ingest/rules.py`)

`data/transaction-overrides.yaml` (exact date + amount + substring) first, then
`data/merchant-rules.yaml` (`MERCHANT KEY: category`), then
`data/merchant-patterns.yaml` (regexes; `salary: true` feeds `is_salary`), then the built-in
`BUILTIN` regexes (first match wins; money-movement rules come before merchant rules),
then a model's guess, then `other`. `rules.merchant_key()` normalizes
descriptions. The category list is the `Category` Literal in `ingest/schemas.py`.

## Data conventions

- **Sign**: `Txn.amount < 0` is money out (spending), `> 0` is money in (refunds, paybacks, income).
- `Txn.source`: `shortcut | manual | email | import`. Imports have a `ref`:
  `{account}:{bank reference}` or `{account}:{sha1 of date|amount|description}`.
  SimpleFIN rows use refs starting with `sfin:`.
- `Txn.account`: `checking_1234`, `credit_card_1234`, `savings_1234`, or
  `logged` for Shortcut entries with no card. `wallet_cards` maps an Apple
  Wallet card name to an account. `card_numbers` maps a debit card's last 4 to an account.
- **Reconciliation** (`importer._reconcile`): a shortcut/manual/email entry
  and a bank row with the same amount, where the bank date is between 1 day
  before and 5 days after, become one. The logged row gets `superseded_by` = the
  bank row, and the bank row keeps its line and note. CSV rows that SimpleFIN
  already brought in are skipped (same account and amount, within ±3 days).
- Debt balances are a history (`debt_balances`, with `source` = `budget |
  statement | simplefin | manual`). The latest `as_of` wins.
- Amount strings like `"$1,234.56"` are accepted on `/tx` (Apple Wallet sends those).

## Code map

### `app/` (server)

| File | Role |
|---|---|
| `config.py` | Every env var (see `.env.example`). Paths default to `./data` and `./inbox`; the image sets `/data`. |
| `main.py` | FastAPI app, lifespan (seed, import, background loops), session middleware, `/healthz`, SPA serving |
| `api.py` | `/api/auth/*` (login, logout, me) and `/api/v1/*` (behind `require_user`): tx/fix/undo, categories, summary, documents (+inspect), dashboard, budget, transactions CRUD, bills paid, balances, tokens, digest send/preview, simplefin claim/sync/map/disconnect, mail status/check, reload |
| `auth.py` | Session cookie (password or trusted proxy header) or `Authorization: Bearer md_…` (SHA-256 stored) |
| `engine.py` | All budget math, computed per request from a `Ctx` snapshot; nothing here writes. `dashboard()` puts it all together. |
| `models.py` | SQLAlchemy tables: `lines, debts, debt_balances, transactions, events, savings_goals, bills_paid, api_tokens, settings, mail_seen, digest_log`. `init_db()` runs `create_all` (no migrations). |
| `seed.py` | budget.yaml → database (see above) |
| `importer.py` | `data/ingest/*.json` → transactions, statement balances, savings balances, and reconciliation. Idempotent. |
| `identify.py` | Works out an uploaded file's kind and account from its contents (file name, overlap with known transactions, payment confirmation codes) |
| `simplefin.py` | Claim a setup token for an access URL (stored in `settings`, never logged), sync accounts and transactions (40-day window), account mapping |
| `mail.py` | IMAP reader for payment receipts. Pattern-based parsing; anything that doesn't parse cleanly is kept for review, never guessed. `--preview` / `--check`. |
| `income.py` | Income report for a year from the stored pay statements: gross, deductions, net, leave history, other money in (`GET /api/v1/income`) |
| `digest.py` + `templates/digest.{html,txt}` | Morning email (Jinja2). CLI: `--date`, `--html`, `--send`. |
| `ical.py` | Calendar feed (`/api/calendar.ics`), reached through a secret key in the link |
| `check.py` | `python -m app.check [file]`: validates a budget file in a throwaway database and prints what it adds up to |
| `tokens.py` | CLI to create or list API tokens |

### `ingest/` (document pipeline; runs as subprocesses of the app, or by hand)

`python -m ingest {run|parse|redact|extract|categorize|summarize}`. Results
are cached per file hash in `data/ingest/`.

| File | Role |
|---|---|
| `__main__.py` | CLI and orchestration |
| `boa_csv.py` | BoA checking/savings (must reconcile to the running balance) and card CSVs. The account comes from the file or folder name (`credit_card_1234`). |
| `boa_statement.py` | BoA card statement PDF: balance, APR, minimum, due date |
| `paystub.py` | Pay statement hook: loads the optional, git-ignored `paystub_local.py` (`matches(pdf)`, `parse(pdf) -> PayStatement`). Without it, pay PDFs go to the model extractor. |
| `household.py` | Shared-house Google Sheet exported as .xlsx (Payments + Balance Sheet tabs) |
| `pdftext.py` | `pdftotext`, with a tesseract OCR fallback |
| `redact.py` | Removes PII (SSNs, account numbers, emails, phones, addresses, plus the terms in `data/pii.yaml`) before any model call |
| `llm.py` | Extraction backends: `claude` (API, `CLAUDE_MODEL`), `claude-code` (`claude -p`), `local` (Ollama) |
| `schemas.py` | Pydantic models (`DocumentExtraction`, `AccountStatement`, `Transaction`, `Category`, …) |
| `rules.py` | Categorization (see above) |
| `validate.py` | Arithmetic checks on extractions |
| `summarize.py` | `data/ingest/summary.md` + `intake-draft.yaml`, and `all_transactions()` used by the importer |
| `store.py`, `paths.py` | Cached results, and paths (from `MD_DATA_DIR` / `MD_INBOX_DIR`, shared with the app) |

Upload flow (`POST /api/v1/documents`): `identify` → move into
`inbox/{bank|pay|household|other}/` (CSV names are
prefixed with the account) → `_run_ingest()` (`parse`, plus
`redact` + `extract` if `MD_EXTRACT_BACKEND` isn't `none`, then `summarize`) → `importer.run()` → reply message.

### `web/` (SvelteKit 2, Svelte 5 runes, Tailwind 4, adapter-static SPA)

Routes: `/` dashboard, `/calendar` (cash forecast), `/recurring` (every repeating
payment and how to pay it; budget.yaml `recurring:` + bills), `/budget`, `/debt` (payoff chart),
`/income` (pay, deductions, leave), `/transactions`,
`/upload`, `/settings` (tokens, email, SimpleFIN, mail, reload), `/setup`
(step-by-step iPhone, Gmail and bank setup with the user's URLs filled in from
`GET /api/v1/setup`). `lib/api.svelte.ts` wraps fetch for `/api`.
`lib/format.ts` formats money and dates. Components: `Icon` (line icons),
`Meter`, `PayoffChart`, `Action` (a setup step), `Copy` (copy-to-clipboard).
In dev, Vite proxies `/api` to `127.0.0.1:8000`.

## Commands

```bash
pip install -r requirements.txt                    # Python 3.12; needs poppler-utils
MD_AUTH=none uvicorn app.main:app --reload         # API + built site on :8000
cd web && npm install && npm run dev               # site on :5173 with HMR
cd web && npm run check                            # svelte-check / TypeScript
cd web && npm run build                            # -> web/build, served by uvicorn
python -m app.check [data/budget.yaml]             # validate a budget, show the totals and payoff
python -m app.digest [--date YYYY-MM-DD] [--html out.html] [--send]
python -m app.mail --preview
python -m app.tokens create <name> | list
python -m ingest run | categorize
cp compose.example.yml compose.yml && docker compose up -d --build
docker compose --profile email --profile tunnel up -d   # optional services
docker compose exec money-doctor python -m app.check   # any CLI, inside the container
```

## Deployment files

`compose.example.yml` runs the app alone, plus optional profiles: `email`
(postfix relay, `deploy/postfix.env`), `tunnel` (nginx + cloudflared,
`deploy/cloudflared.env`), `nginx`, and `sso` (oauth2-proxy,
`deploy/oauth2-proxy.env`, with `MD_NGINX_CONF=money-doctor-sso.conf`). The
nginx configs are in `deploy/nginx/`. The network is `172.30.50.0/24` with
fixed addresses below `.128` (app `.2`, nginx `.10`, cloudflared `.20`);
automatic ones come from `.128/25` so they never collide.

The compose file mounts `./data`, the same directory the CLIs use when run
from the checkout. So in a checkout that is also someone's deployment,
anything that writes (`--send`, `--check`, uploads, reload) acts on real data.

## Gotchas

- `seed()` deletes and recreates lines, events and goals on every start and
  reload. Never store user edits only in those tables; they belong in budget.yaml.
- No migrations: `create_all` adds new tables but not new columns on existing
  ones. Adding a column to an existing table needs a manual `ALTER TABLE` or a
  small migration step at startup.
- SimpleFIN asks clients to stay under 24 requests a day, so keep the 6-hour cadence.
- The container runs as uid 1000 without `--proxy-headers`. `MD_TRUSTED_PROXIES`
  is checked against the raw peer address.
- `claude-code` extraction needs the `claude` CLI, so it doesn't work inside the image.
- Dates in the engine use `date.today()` in the container's `TZ`. The digest
  schedule uses `timezone` from budget.yaml.
