"""Request guards shared across domains: admin token and per-IP rate limits."""

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Header, Request

from src.config import settings
from src.exceptions import PermissionDenied, RateLimited


async def require_admin(x_admin_token: Annotated[str, Header()] = "") -> None:
    expected = settings.admin_token.get_secret_value()
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise PermissionDenied


class RateLimiter:
    """In-memory sliding window per key.

    Fine while the API runs as a single process. Move to Redis before running
    more than one worker or server, or each process will count separately.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


def limit_by_ip(limiter: RateLimiter) -> Callable[[Request], None]:
    """Dependency factory.

    Behind a proxy (Caddy), run uvicorn with --proxy-headers so client.host is the real IP.
    """

    def dependency(request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        if not limiter.hit(key):
            raise RateLimited("Too many attempts. Try again in a while.")

    return dependency
