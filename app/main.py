"""The app: API + website + the morning email scheduler.

  uvicorn app.main:app --port 8000
"""

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, digest, engine, importer, mail, seed, simplefin
from .api import router
from .models import init_db

log = logging.getLogger("money-doctor")


async def digest_loop() -> None:
    while True:
        ctx = engine.load()
        tz = ZoneInfo(ctx.settings.get("timezone") or "UTC")
        send_at = (ctx.settings.get("digest") or {}).get("send_at", "06:30")
        await asyncio.sleep(digest.seconds_until(send_at, datetime.now(tz)))
        try:
            today = datetime.now(tz).date()
            log.info("digest: %s", await asyncio.to_thread(digest.send, today))
        except Exception:
            log.exception("digest failed")
        await asyncio.sleep(60)


async def mail_loop() -> None:
    while True:
        try:
            result = await asyncio.to_thread(mail.check)
            if result.get("logged"):
                log.info("mail: %s", result)
        except Exception as exc:
            log.warning("mail check failed: %s", exc)
        await asyncio.sleep(config.MAIL_POLL_SECONDS)


async def bank_sync_loop() -> None:
    """SimpleFIN a few times a day (it asks apps to stay under 24 requests a day)."""
    await asyncio.sleep(60)
    while True:
        if simplefin.status()["connected"]:
            try:
                log.info("simplefin: %s", await asyncio.to_thread(simplefin.sync))
            except Exception as exc:
                log.warning("simplefin sync failed: %s", exc.__class__.__name__)
        await asyncio.sleep(6 * 60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.AUTH_MODE == "proxy" and not config.TRUSTED_PROXIES:
        log.warning("MD_AUTH=proxy without MD_TRUSTED_PROXIES: any client that reaches the app can set %s", config.PROXY_HEADER)
    if config.AUTH_MODE == "password" and not config.PASSWORD:
        log.warning("MD_AUTH=password but MD_PASSWORD is empty: nobody can log in to the website")
    init_db()
    seed.seed()
    log.info("import: %s", importer.run())
    tasks = [asyncio.create_task(digest_loop())] if config.DIGEST_ENABLED else []
    if config.MAIL_USER and config.MAIL_PASSWORD:
        tasks.append(asyncio.create_task(mail_loop()))
    tasks.append(asyncio.create_task(bank_sync_loop()))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Money Doctor", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET or secrets.token_hex(32), same_site="lax",
                   https_only=config.PUBLIC_URL.startswith("https"), max_age=60 * 60 * 24 * 30)
app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# The built website (web/build). Unknown paths fall back to index.html so the
# app's own routes work on reload.
if config.WEB_DIR.exists():
    app.mount("/_app", StaticFiles(directory=config.WEB_DIR / "_app"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = (config.WEB_DIR / path).resolve()
        if path and file.is_file() and config.WEB_DIR in file.parents:
            return FileResponse(file)
        return FileResponse(config.WEB_DIR / "index.html")
