# Money Doctor

A self-hosted budgeting app for getting out of debt. Log a purchase from your
iPhone in two taps, bring in bank data without typing numbers, and get a
morning email that tells you what you can spend today and what's due.

- **Safe to spend today**, per budget line, based on what's left this month
- **Paycheck plan**: which bills each paycheck covers, and the extra that goes to debt
- **Debt payoff projection** (avalanche), with a target date and an on-track check
- **Morning email**: today's spending room, bills due, the next paycheck, yesterday's spending, debt progress, what's coming up
- **iPhone Shortcuts**: log an expense, log Apple Pay purchases automatically, undo, "Hey Siri, money today", share a PDF to upload it
- **Bank sync** through [SimpleFIN Bridge](https://beta-bridge.simplefin.org) (works with most US banks)
- **Payment emails**: Venmo, Cash App, PayPal and bank alert emails become transactions within minutes
- **Document ingest**: Bank of America CSV exports and statements are parsed exactly, with no AI, and you can plug in an exact parser for your own pay statements; other PDFs go through PII redaction, then a model you choose (Claude API, headless Claude Code, or a local Ollama model)
- **Reconciliation**: a purchase you logged and the same purchase from the bank become one

One container: a FastAPI server, a SQLite database, and a SvelteKit site.

> **Scope.** This started as a personal project. Bank sync, Shortcuts, the
> budget and the email work for anyone. The exact file parsers support Bank of
> America CSV/statement formats; other banks' files need SimpleFIN, the
> model-based PDF extractor, or a new parser in `ingest/`. Pay statements
> differ by employer: write a parser in `ingest/paystub_local.py` (see
> `ingest/paystub.py`), or let the model extractor read them. Pay has to come
> weekly or every two weeks, on one schedule (see
> [Pay schedules](docs/budget-reference.md#basics)).

---

## Contents

1. [How the budget works](#how-the-budget-works)
2. [Quick start (Docker)](#quick-start-docker)
   - [Or let Claude Code set it up](#or-let-claude-code-set-it-up)
3. [Write your budget](#write-your-budget)
4. [First-run setup](#first-run-setup)
5. [Deploying it](#deploying-it)
6. [Configuration reference](#configuration-reference)
7. [Development](#development)
8. [Project layout](#project-layout)
9. [Privacy](#privacy)

---

## How the budget works

Money Doctor is built around one method, so it can give real answers ("you can
spend $40 today") instead of only drawing charts.

**Paycheck-based, zero-based budgeting.** You budget on a fixed number of
**base** paychecks a month (two, if you're paid every two weeks). Every dollar
of those paychecks goes to a budget line. Whatever isn't assigned goes to the
debt with the highest APR (avalanche).

| Line kind | What it is | Example |
|---|---|---|
| `bill` | A fixed amount with a due day; it shows as paid once a matching payment appears | rent, car payment, card minimums |
| `variable` | Everyday spending with a monthly target; feeds "safe to spend today" | groceries, gas, dining |
| `fund` | Saves a fixed amount a month for something lumpy and keeps a running balance | car insurance, gifts |
| `savings` | Money you keep | investing |

- **Extra paychecks** (the months with a third biweekly paycheck) aren't in
  the budget. You decide per month in `plan.third_paycheck` what they do,
  e.g. fill the emergency fund, or half to debt and half to a buffer.
- **Overtime and other irregular income** aren't budgeted either; they speed up payoff.
- **Safe to spend today** = what's left in each variable line ÷ the days left in the month.
- **Payoff projection** runs month by month: interest, minimums, then
  everything extra to the highest APR, until the balances reach zero.

Not financial advice. The math is only as good as the numbers you give it.

---

## Quick start (Docker)

You need Docker with the Compose plugin.

```bash
git clone https://github.com/<you>/money-doctor.git && cd money-doctor

cp .env.example .env                       # set MD_PASSWORD and MD_SECRET at least
cp compose.example.yml compose.yml
mkdir -p data && cp config/budget.example.yaml data/budget.yaml
sudo chown -R 1000:1000 data               # the container runs as uid 1000

docker compose up -d --build
```

Open <http://localhost:8000> and log in with `MD_PASSWORD`. Until you write
`data/budget.yaml`, the app runs on the example budget.

`data/` holds everything personal: the budget, merchant rules, the database,
and uploaded documents. It's git-ignored. Back it up.

### Or let Claude Code set it up

The repo comes with instructions and skills for
[Claude Code](https://claude.com/claude-code) (`CLAUDE.md` and
`.claude/skills/`). Open it in the repo folder and ask in plain words:

| Ask | Skill |
|---|---|
| "Help me set this up on my server" | `setup`: `.env`, compose profiles, email, tunnel, login, Shortcuts, bank sync |
| "Build my budget" / "I got a raise" | `budget`: interviews you or reads your statements, writes `data/budget.yaml`, checks it |
| "How am I doing this month?" | `checkin`: spending by line, payoff on track or not, options to adjust |
| "Why is this in Other?" | `categorize`: teaches it your merchants |
| "Read my pay stubs" | `paystub-parser`: an exact parser for your employer's pay statement |
| "Is it safe to push?" | `privacy-check`: makes sure none of your data is in tracked files |

It asks before anything that changes your live data, and never needs your
passwords in the chat. Note that Claude reads the files it works with,
including your budget and statements in `data/`; that's the trade for its
help. If you'd rather it didn't, do those steps by hand.

---

## Write your budget

`data/budget.yaml` is the source of truth for your income, budget lines,
debts, savings goals and dated events. Start from
[`config/budget.example.yaml`](config/budget.example.yaml); every key is in
[docs/budget-reference.md](docs/budget-reference.md). The main parts:

```yaml
timezone: America/Chicago           # when the morning email goes out

income:
  paycheck_net: 2000.00             # one base paycheck, after taxes, without overtime
  pay_anchor: 2026-03-06            # any past or future payday
  pay_every_days: 14
  budget_paychecks: 2

plan:
  start: 2026-03                    # funds start accumulating this month
  target_payoff: 2028-09-30
  third_paycheck:
    - {month: 2027-04, emergency_fund: 1000, rest: cards}

lines:                              # one per budget line (see the table above)
  - {key: groceries, name: Groceries, group: Everyday, kind: variable, amount: 350,
     tracks: [groceries], shortcut: Groceries}

debts:                              # current balances; statements and bank sync update them
  - {key: card_a, name: Card A, kind: credit_card, last4: "1111", balance: 6000,
     as_of: 2026-02-18, apr: 24.99, minimum: 150, due_day: 20, limit: 8000}
```

- `tracks` lists the transaction categories that count against a line (the
  full list is `Category` in [`ingest/schemas.py`](ingest/schemas.py)).
  `match` pins transactions whose description contains that text, and is checked first.
- `shortcut` puts the line in the iPhone "Log Expense" menu.
- `from` / `until` (YYYY-MM) limit a line to certain months, e.g. a loan that ends.
- The lines should add up to about `paycheck_net × budget_paychecks`. Anything
  left over is the monthly extra payment to debt.

Check it before loading it. This catches typos, unknown categories and lines
that add up to more than your income, and shows the monthly extra to debt
and the projected payoff date:

```bash
docker compose exec money-doctor python -m app.check
```

Then click **Settings → Reload budget & re-import** (or restart the container).
Transactions and balance history are kept; lines, debts, events and settings
are replaced from the file.

**Your own categorization rules** go in `data/merchant-rules.yaml` as
`MERCHANT KEY: category`, and override the built-in rules in
`ingest/rules.py`. For local businesses and your employer's payroll deposit,
add regexes to `data/merchant-patterns.yaml`:

```yaml
- {match: "ACME CORP DES:PAYROLL", category: income, salary: true}
- {match: "CITY OF SPRINGFIELD UTIL", category: utilities}
```

 Run `python -m ingest categorize` (or
`docker compose exec money-doctor python -m ingest categorize`) to list the
merchants that still need one.

---

## First-run setup

Everything here is on the website. **Settings → iPhone setup** (`/setup`) walks
through each step with your own URLs filled in.

1. **API token**: Settings → Shortcut tokens → Create token. Shortcuts and
   scripts send it as `Authorization: Bearer md_…`.
2. **iPhone Shortcuts**: Log Expense, automatic Apple Pay logging, Undo, Money
   Today, and Send to Money Doctor. Recipes are in [docs/shortcuts.md](docs/shortcuts.md).
3. **Bank sync** (optional, about $15/yr): create an account at
   [SimpleFIN Bridge](https://beta-bridge.simplefin.org), link your bank, make a
   setup token, and paste it in **Settings → Bank sync**. Map each SimpleFIN
   account to a debt or account in your budget. It syncs every 6 hours.
4. **Morning email**: set the `SMTP_*` variables and `digest.to` in
   `budget.yaml`. **Settings → Send now** tests it.
5. **Payment emails** (optional): a Gmail filter puts Venmo / Cash App /
   PayPal / bank alert emails in a `Money Doctor` label. Set `MAIL_USER` and
   `MAIL_PASSWORD` (a Gmail app password) and the app checks it every 2 minutes.
6. **History** (optional): upload bank CSV exports and statement PDFs on the
   **Upload** page, or share them from the iPhone. Re-uploading is safe;
   duplicates are detected.

---

## Deploying it

To use it from your phone, it needs a public HTTPS address. Set
`MD_PUBLIC_URL` to that address. The login cookie is marked secure when it
starts with `https`.

`compose.example.yml` has the pieces as optional profiles. Turn them on with
`COMPOSE_PROFILES` in `.env` (e.g. `COMPOSE_PROFILES=email,tunnel`), then
`docker compose up -d`. Each profile has an example settings file in
`deploy/`. Copy it without `.example`; the copies are git-ignored.

| Profile | Adds | Settings |
|---|---|---|
| `tunnel` | nginx + a Cloudflare Tunnel | `deploy/cloudflared.env` |
| `email` | a postfix relay for the morning email | `deploy/postfix.env` |
| `nginx` | nginx alone, for your own HTTPS or port forward | none |
| `sso` | oauth2-proxy, to log in through Keycloak, Authelia, Authentik, Google... | `deploy/oauth2-proxy.env` |

**Cloudflare Tunnel** (recommended). Free, nothing opened on your router,
HTTPS at Cloudflare. You need a domain on Cloudflare.

1. Cloudflare dashboard → Zero Trust → Networks → Tunnels → Create a tunnel
   (Cloudflared). Copy the token into `deploy/cloudflared.env`.
2. In the tunnel, add a public hostname, e.g. `money.example.com`, service
   `HTTP`, URL `nginx:8080`.
3. `.env`: `MD_PUBLIC_URL=https://money.example.com`, `COMPOSE_PROFILES=tunnel`.

nginx sits between the tunnel and the app (`deploy/nginx/money-doctor.conf`).
It adds rate limits (password guessing gets slowed down), a 50 MB upload
limit, long timeouts for statement uploads, and security headers.

**Your own reverse proxy** instead. Proxy everything to `127.0.0.1:8000`.
With Caddy, for example:

```
money.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

**Logging in.** Pick one with `MD_AUTH`:

| Mode | How | Use when |
|---|---|---|
| `password` (default) | one shared password, `MD_PASSWORD` | most setups |
| `proxy` | trust a header from an SSO proxy. With the `sso` profile: `MD_NGINX_CONF=money-doctor-sso.conf`, `MD_PROXY_HEADER=X-Auth-Request-Email`, `MD_TRUSTED_PROXIES=172.30.50.10` | you already run SSO |
| `none` | no login | local development only |

The API (`/api/v1/*`) always accepts a bearer token from **Settings**, so
Shortcuts work in every mode. Behind SSO, a request with no login session is
passed to the app without an identity, so only a valid token gets in.
Calendar apps use the secret link from Settings. If your API sits behind
Cloudflare Access, set `MD_SHORTCUT_AUTH=cloudflare-access` and the setup page
adds the service-token headers to each Shortcut.

**Email.** Mail sent straight from a home connection is usually blocked or
lands in spam, so send through a real mail account. Two ways:

- **Straight to Gmail** (no extra container). Turn on 2-Step Verification, make an
  [app password](https://myaccount.google.com/apppasswords), and in `.env`:
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_STARTTLS=true`,
  `SMTP_USER=you@gmail.com`, `SMTP_PASSWORD=<app password>`.
- **Postfix relay** (profile `email`). It queues and retries if Gmail is
  briefly unreachable. Put the app password in `deploy/postfix.env`, and in
  `.env`: `SMTP_HOST=postfix`, `SMTP_PORT=25`. Other providers (Fastmail,
  Mailgun, Resend, SES) work the same way with their SMTP host.

Then set `digest.to` in `data/budget.yaml` and click **Settings → Send now**.
`docker compose logs postfix` shows each delivery (`status=sent`, or `535` for a
wrong password).

**Network.** The compose network is `172.30.50.0/24`. Change it if it overlaps
one you have, and update the fixed addresses and `MD_TRUSTED_PROXIES` to match.

**Updating.**

```bash
git pull && docker compose up -d --build
```

The database schema is created on start; your data in `data/` is kept.

**Backups.** Copy the whole `data/` directory. For a consistent copy of the
database while the app runs:

```bash
sqlite3 data/money.db ".backup data/money-backup.db"
```

---

## Configuration reference

All server settings are environment variables, set in `.env`.
[`.env.example`](.env.example) lists every one with a comment. The main ones:

| Variable | Default | Purpose |
|---|---|---|
| `COMPOSE_PROFILES` | | Optional services: `email`, `tunnel`, `nginx`, `sso` |
| `MD_NGINX_CONF` | `money-doctor.conf` | nginx config from `deploy/nginx/` (`money-doctor-sso.conf` with `sso`) |
| `MD_PUBLIC_URL` | `http://localhost:8000` | The address you open the site at |
| `MD_AUTH` | `password` | `password`, `proxy`, or `none` |
| `MD_PASSWORD` | | Website password |
| `MD_SECRET` | random per start | Signs the login cookie; set it so logins survive restarts |
| `MD_PROXY_HEADER`, `MD_TRUSTED_PROXIES` | | `MD_AUTH=proxy` only |
| `MD_SHORTCUT_BASE`, `MD_SHORTCUT_AUTH` | `{MD_PUBLIC_URL}/api/v1`, `bearer` | Where Shortcuts send requests, and how they authenticate |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` | | Morning email |
| `MD_DIGEST` | `true` | `false` turns the email off |
| `MAIL_USER`, `MAIL_PASSWORD`, `MAIL_FOLDER`, `MAIL_IMAP_HOST`, `MAIL_POLL_SECONDS` | | Payment emails over IMAP |
| `MD_EXTRACT_BACKEND` | `none` | Model for unrecognized PDFs: `none`, `local`, `claude`, `claude-code` |
| `OLLAMA_URL`, `OLLAMA_MODEL` | `http://localhost:11434`, `qwen3:14b` | `local` backend |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | | `claude` backend |
| `MD_DATA_DIR`, `MD_INBOX_DIR`, `MD_BUDGET_FILE`, `MD_DB_URL` | `data/`, `inbox/`, `data/budget.yaml`, SQLite in `data/` | Paths (the image sets these to `/data`) |
| `TZ` | `America/New_York` in the image | Container clock |

Files in `data/`:

| File | What |
|---|---|
| `budget.yaml` | Your budget (see above) |
| `merchant-rules.yaml` | `MERCHANT KEY: category` rules that override the built-in ones |
| `merchant-patterns.yaml` | Regex rules for local businesses and your payroll deposit (`salary: true`) |
| `transaction-overrides.yaml` | One-off fixes: `{date, amount, match, category}` |
| `pii.yaml` | Names, addresses and IDs to redact before any text goes to a model (copy `ingest/pii.example.yaml`) |
| `settings.yaml` | Ingest settings, e.g. `household_me` (your name in a shared-house spreadsheet) |
| `money.db` | The database |
| `inbox/` | Uploaded documents, sorted by type |
| `ingest/` | Parsed results and `summary.md` |

---

## Development

Requirements: Python 3.12, Node 24, and `poppler-utils` (for `pdftotext`).
`tesseract-ocr` is optional, for scanned PDFs.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data && cp config/budget.example.yaml data/budget.yaml

MD_AUTH=none uvicorn app.main:app --reload       # API on :8000
cd web && npm install && npm run dev             # site on :5173, proxies /api to :8000
```

Open <http://localhost:5173>. To have uvicorn serve the site itself, run
`npm run build` in `web/` (it writes `web/build/`) and open <http://localhost:8000>.

Useful commands:

```bash
python -m app.check                         # validate data/budget.yaml and show what it adds up to
python -m app.digest                        # print today's morning email
python -m app.digest --date 2026-04-14      # ...for another day
python -m app.digest --html out.html        # write the HTML version
python -m app.digest --send                 # send it now
python -m app.tokens create my-server       # make an API token (printed once)
python -m app.mail --preview                # what the payment-email reader would log
python -m ingest run                        # parse inbox/ and summarize
python -m ingest categorize                 # merchants still in "other"
cd web && npm run check                     # type-check the site
```

The ingest has its own README: [ingest/README.md](ingest/README.md).

---

## Project layout

| Path | What |
|---|---|
| `app/` | Server: models, budget engine, API, morning email, bank sync, payment emails |
| `app/templates/` | Morning email (HTML and text) |
| `ingest/` | Document parsing, PII redaction, categorization ([README](ingest/README.md)) |
| `web/` | SvelteKit site (static build, served by the Python server) |
| `config/budget.example.yaml` | The budget format, with an example |
| `intake/budget-intake.example.yaml` | Optional questionnaire for working out a plan (with a person or an AI) before writing `budget.yaml` |
| `docs/shortcuts.md` | iPhone Shortcut recipes and the API |
| `docs/budget-reference.md` | Every key in `budget.yaml` |
| `Dockerfile`, `compose.example.yml` | The image and an example deployment with optional services |
| `deploy/` | nginx configs and example settings for postfix, cloudflared and oauth2-proxy |
| `CLAUDE.md`, `.claude/skills/` | Instructions and skills for Claude Code |

---

## Privacy

- Your data stays in `data/` on your server. Nothing is sent anywhere except
  what you turn on: SimpleFIN (bank sync), your SMTP server, your Gmail
  (read-only, one label), and a model backend if you set `MD_EXTRACT_BACKEND`.
- PDFs are never sent to a model. Text is extracted and redacted locally first,
  and only the redacted text goes out. Use the `local` backend to keep even that on your network.
- Budget lines can be `private: true`. They count in totals but show as "Personal".
- API tokens are stored as SHA-256 hashes. The SimpleFIN access URL is stored in the database and never logged.
- If you use Claude Code with it, Claude reads the files it works on (your
  budget, statements, transactions) and sends them to Anthropic to answer.
  The skills never need passwords in the chat.
- `.gitignore` keeps `data/`, `inbox/`, `intake/*.yaml`, `.env`, `deploy/*.env` and statement
  file types out of git. Keep your real data out of the repo, especially in a fork.

## License

[MIT](LICENSE). Free to use, change and share.
