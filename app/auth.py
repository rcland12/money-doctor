"""Who's allowed in.

- The website: a session cookie after logging in with MD_PASSWORD, or, when
  MD_AUTH=proxy, a header set by an SSO proxy in front of the app.
- Shortcuts and scripts: `Authorization: Bearer <token>`, tokens made on the
  Settings page. Only a SHA-256 of each token is stored.
"""

import hashlib
import hmac
import secrets
from datetime import datetime

from fastapi import HTTPException, Request
from sqlalchemy import select

from . import config
from .models import ApiToken, Session


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(name: str) -> str:
    token = "md_" + secrets.token_urlsafe(32)
    with Session.begin() as s:
        s.add(ApiToken(name=name, token_hash=hash_token(token)))
    return token


def _bearer_ok(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    digest = hash_token(header[7:].strip())
    with Session.begin() as s:
        row = s.scalar(select(ApiToken).where(ApiToken.token_hash == digest))
        if row:
            row.last_used = datetime.now()
        return row is not None


def _browser_ok(request: Request) -> bool:
    if config.AUTH_MODE == "none":
        return True
    if config.AUTH_MODE == "proxy" and request.headers.get(config.PROXY_HEADER):
        # Trust the SSO header only from the reverse proxy itself. The app runs
        # without --proxy-headers, so client.host is the real peer address.
        peer = request.client.host if request.client else ""
        if not config.TRUSTED_PROXIES or peer in config.TRUSTED_PROXIES:
            return True
    return bool(request.session.get("user"))


def require_user(request: Request) -> None:
    """For the website's own API calls."""
    if not (_browser_ok(request) or _bearer_ok(request)):
        raise HTTPException(401, "Not logged in")


def check_password(password: str) -> bool:
    return bool(config.PASSWORD) and hmac.compare_digest(password.encode(), config.PASSWORD.encode())
