"""Sends one Web Push message. pywebpush is synchronous, so it runs in a thread."""

import logging
from dataclasses import dataclass
from typing import Protocol

from fastapi.concurrency import run_in_threadpool
from pywebpush import WebPushException, webpush

from src.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Device:
    endpoint: str
    p256dh: str
    auth: str


class Sender(Protocol):
    async def __call__(self, device: Device, payload: str, ttl: int) -> int:
        """Send, and return the push service's HTTP status (0 if it couldn't be reached)."""
        ...


async def send(device: Device, payload: str, ttl: int) -> int:
    return await run_in_threadpool(_send, device, payload, ttl)


def _send(device: Device, payload: str, ttl: int) -> int:
    try:
        response = webpush(
            {"endpoint": device.endpoint, "keys": {"p256dh": device.p256dh, "auth": device.auth}},
            data=payload,
            vapid_private_key=settings.vapid_private_key.get_secret_value(),
            vapid_claims={"sub": settings.vapid_subject},
            ttl=ttl,
            timeout=10,
        )
        return getattr(response, "status_code", 201)
    except WebPushException as error:
        return error.response.status_code if error.response is not None else 0
    except Exception:  # network trouble: try again later
        log.warning("push send failed", exc_info=True)
        return 0
