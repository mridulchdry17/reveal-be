from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image

from src.auth.dependencies import get_google_verifier
from src.config import settings
from src.main import app
from tests.auth.test_auth import auth, fake_verify, sign_in

STUDENT = "sub-aanya|aanya@adgips.ac.in|Aanya Sharma|yes|adgips.ac.in"
URL = "/v1/profile/me/photo"


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


def jpeg(width: int = 3000, height: int = 2000, *, gps: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (200, 120, 90))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {2: (28.0, 36.0, 0.0), 4: (77.0, 12.0, 0.0)}  # GPSInfo
    exif[0x0112] = 6  # Orientation: rotate 90° to show upright
    out = BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


async def student(client: AsyncClient) -> dict[str, str]:
    return auth((await sign_in(client, STUDENT)).json()["token"])


async def upload(client: AsyncClient, headers: dict[str, str], data: bytes):
    return await client.put(URL, files={"photo": ("p.jpg", data, "image/jpeg")}, headers=headers)


def stored_files() -> list[Path]:
    root = Path(settings.media_dir)
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


async def test_photo_is_reencoded_upright_small_and_without_exif(client: AsyncClient) -> None:
    headers = await student(client)

    response = await upload(client, headers, jpeg(gps=True))
    photo = await client.get(URL, headers=headers)

    assert response.status_code == 200
    assert response.json()["has_photo"] is True
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["cache-control"] == "no-store, private"
    image = Image.open(BytesIO(photo.content))
    assert image.size == (1067, 1600)  # 3000x2000 turned upright, longer side 1600
    assert not image.getexif()


async def test_a_new_photo_replaces_the_old_file(client: AsyncClient) -> None:
    headers = await student(client)

    await upload(client, headers, jpeg())
    first = stored_files()
    await upload(client, headers, jpeg(800, 800))

    assert len(first) == 1
    assert len(stored_files()) == 1
    assert stored_files() != first


async def test_photo_can_be_removed(client: AsyncClient) -> None:
    headers = await student(client)
    await upload(client, headers, jpeg())

    response = await client.delete(URL, headers=headers)

    assert response.json()["has_photo"] is False
    assert stored_files() == []
    assert (await client.get(URL, headers=headers)).status_code == 404


async def test_not_a_photo_is_refused(client: AsyncClient) -> None:
    headers = await student(client)

    response = await upload(client, headers, b"%PDF-1.7 not an image")

    assert response.status_code == 422
    assert response.json()["code"] == "not_a_photo"
    assert stored_files() == []


async def test_too_large_is_refused(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "profile_photo_max_bytes", 1000)
    headers = await student(client)

    response = await upload(client, headers, jpeg())

    assert response.status_code == 413
    assert response.json()["code"] == "photo_too_large"
