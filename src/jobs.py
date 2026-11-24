"""Background work inside the API process: the 9 PM alert and sending pushes.

One loop, started by the app's lifespan only when push is configured. Everything it does
is saved in Postgres first (push_outbox, drop_alert) and claimed with SKIP LOCKED, so a
restart loses nothing and a second process wouldn't double-send. Swap this for Arq when
there's a Redis to run it on.
"""

import asyncio
import contextlib
import logging

from src.clock import now
from src.database import SessionLocal
from src.drops import service as drop_service
from src.notifications import service as notification_service
from src.notifications import webpush
from src.notifications.constants import POLL_SECONDS

log = logging.getLogger(__name__)


async def tick() -> None:
    async with SessionLocal() as session:
        await drop_service.alert_tonight(session, now())
        while await notification_service.deliver(session, webpush.send):
            pass


async def run_forever() -> None:
    while True:
        try:
            await tick()
        except Exception:
            log.exception("background tick failed")
        await asyncio.sleep(POLL_SECONDS)


@contextlib.asynccontextmanager
async def running():
    task = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
