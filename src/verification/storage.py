"""Verification photos as files on the server's disk.

They live outside the code checkout (settings.verification_photos_dir, e.g.
/var/lib/reveal/production/verification), so deploys, restarts and crashes keep them.
Nothing serves this folder; only admins read a photo, through the API.
"""

import os
import secrets
import uuid
from pathlib import Path

from fastapi.concurrency import run_in_threadpool

from src.config import settings


def _root() -> Path:
    return Path(settings.verification_photos_dir)


def detect_image_type(data: bytes) -> str | None:
    """File extension from the bytes themselves; never trust the browser's content type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _write(name: str, data: bytes) -> None:
    root = _root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL: never overwrite; 0o600: readable only by the API's user.
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


async def save(request_id: uuid.UUID, kind: str, data: bytes, extension: str) -> str:
    """Store a photo and return its file name (random, so it can't be guessed)."""
    name = f"{request_id}-{kind}-{secrets.token_hex(8)}.{extension}"
    await run_in_threadpool(_write, name, data)
    return name


async def delete(*names: str | None) -> None:
    for name in names:
        if name:
            await run_in_threadpool((_root() / name).unlink, True)


def path_for(name: str) -> Path:
    return _root() / name
