"""Private files for profiles (photos now, voice notes next): put, get and delete by key.

On servers (settings.media_storage_account set) they live in Azure Blob Storage. The
VM's managed identity authorises every call, so no storage key exists anywhere; we call
the Blob REST API with httpx rather than pulling in the Azure SDKs, to stay light on the
small VM. Locally and in tests they're files under settings.media_dir. Nothing here is
ever public: the API streams a file only to someone allowed to see it.
"""

import os
import time
from pathlib import Path

import httpx
from fastapi.concurrency import run_in_threadpool

from src.config import settings

_IMDS_TOKEN_URL = "http://169.254.169.254/metadata/identity/oauth2/token"
_BLOB_API_VERSION = "2023-11-03"
_token: tuple[str, float] | None = None  # (access token, expires at), reused until near expiry


class MediaError(RuntimeError):
    """Storage answered with something unexpected. Becomes a 500; never shown to users."""


async def put(key: str, data: bytes, content_type: str) -> None:
    if not settings.media_storage_account:
        await run_in_threadpool(_write_local, key, data)
        return
    response = await _blob("PUT", key, content=data, content_type=content_type)
    if response.status_code != 201:
        raise MediaError(f"Storing a file failed with {response.status_code}")


async def get(key: str) -> bytes | None:
    if not settings.media_storage_account:
        return await run_in_threadpool(_read_local, key)
    response = await _blob("GET", key)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise MediaError(f"Reading a file failed with {response.status_code}")
    return response.content


async def delete(key: str) -> None:
    """Gone already counts as deleted."""
    if not settings.media_storage_account:
        await run_in_threadpool(_local_path(key).unlink, True)
        return
    response = await _blob("DELETE", key)
    if response.status_code not in (202, 404):
        raise MediaError(f"Deleting a file failed with {response.status_code}")


async def _blob(
    method: str, key: str, *, content: bytes | None = None, content_type: str | None = None
) -> httpx.Response:
    url = (
        f"https://{settings.media_storage_account}.blob.core.windows.net/"
        f"{settings.media_container}/{key}"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        headers = {
            "Authorization": f"Bearer {await _access_token(client)}",
            "x-ms-version": _BLOB_API_VERSION,
        }
        if content is not None:
            headers["x-ms-blob-type"] = "BlockBlob"
            headers["Content-Type"] = content_type or "application/octet-stream"
        return await client.request(method, url, headers=headers, content=content)


async def _access_token(client: httpx.AsyncClient) -> str:
    """A token for Azure Storage from the VM's managed identity (instance metadata service)."""
    global _token
    if _token and _token[1] - 300 > time.time():
        return _token[0]
    response = await client.get(
        _IMDS_TOKEN_URL,
        params={"api-version": "2018-02-01", "resource": "https://storage.azure.com/"},
        headers={"Metadata": "true"},
    )
    if response.status_code != 200:
        raise MediaError(f"Managed identity token failed with {response.status_code}")
    body = response.json()
    _token = (body["access_token"], float(body["expires_on"]))
    return _token[0]


def _local_path(key: str) -> Path:
    root = Path(settings.media_dir).resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root):
        raise MediaError("Key points outside the media folder")
    return path


def _write_local(key: str, data: bytes) -> None:
    path = _local_path(key)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _read_local(key: str) -> bytes | None:
    path = _local_path(key)
    return path.read_bytes() if path.exists() else None
