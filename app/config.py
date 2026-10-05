"""Settings, all from environment variables (see .env.example)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, default)).resolve()


DATA_DIR = _path("MD_DATA_DIR", ROOT / "data")
INBOX_DIR = _path("MD_INBOX_DIR", ROOT / "inbox")
os.environ.setdefault("MD_DATA_DIR", str(DATA_DIR))  # the ingest subprocesses read these
os.environ.setdefault("MD_INBOX_DIR", str(INBOX_DIR))
BUDGET_FILE = _path("MD_BUDGET_FILE", DATA_DIR / "budget.yaml")
DB_URL = os.environ.get("MD_DB_URL", f"sqlite:///{DATA_DIR / 'money.db'}")
WEB_DIR = _path("MD_WEB_DIR", ROOT / "web" / "build")
PUBLIC_URL = os.environ.get("MD_PUBLIC_URL", "http://localhost:8000").rstrip("/")

# Auth. MD_AUTH: "password" (default), "proxy" (trust a header set by an SSO
# proxy such as oauth2-proxy), or "none" (local development only).
AUTH_MODE = os.environ.get("MD_AUTH", "password")
PASSWORD = os.environ.get("MD_PASSWORD", "")
PROXY_HEADER = os.environ.get("MD_PROXY_HEADER", "X-Auth-Request-Email")
# MD_AUTH=proxy only: the addresses allowed to set PROXY_HEADER (your reverse
# proxy). Without this, anything that can reach the app could claim a login.
TRUSTED_PROXIES = {ip.strip() for ip in os.environ.get("MD_TRUSTED_PROXIES", "").split(",") if ip.strip()}
SECRET = os.environ.get("MD_SECRET", "")

# Where iPhone Shortcuts send requests, and how they authenticate. Direct:
# {PUBLIC_URL}/api/v1 with a bearer token from Settings. Behind a gateway
# (e.g. an API that adds its own token and sits behind Cloudflare Access):
# MD_SHORTCUT_BASE=https://api.example.com/money MD_SHORTCUT_AUTH=cloudflare-access
SHORTCUT_BASE = os.environ.get("MD_SHORTCUT_BASE", "").rstrip("/") or f"{PUBLIC_URL}/api/v1"
SHORTCUT_AUTH = os.environ.get("MD_SHORTCUT_AUTH", "bearer")  # bearer | cloudflare-access

# Email digest
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "false").lower() == "true"
SMTP_FROM = os.environ.get("SMTP_FROM", "Money Doctor <money@localhost>")
DIGEST_ENABLED = os.environ.get("MD_DIGEST", "true").lower() == "true"

# Payment emails (app/mail.py): a Gmail label read over IMAP with an app password.
MAIL_IMAP_HOST = os.environ.get("MAIL_IMAP_HOST", "imap.gmail.com")
MAIL_USER = os.environ.get("MAIL_USER", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FOLDER = os.environ.get("MAIL_FOLDER", "Money Doctor")
MAIL_POLL_SECONDS = int(os.environ.get("MAIL_POLL_SECONDS", "120"))
MAIL_SINCE_DAYS = int(os.environ.get("MAIL_SINCE_DAYS", "7"))

# Which model backend reads PDFs that aren't pay statements (see ingest/llm.py):
# claude-code | claude | local | none
EXTRACT_BACKEND = os.environ.get("MD_EXTRACT_BACKEND", "none")
