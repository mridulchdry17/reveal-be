from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from src.auth.dependencies import get_google_verifier
from src.config import settings
from src.main import app
from tests.auth.test_auth import auth, fake_verify, sign_in

STUDENT = "sub-aanya|aanya@adgips.ac.in|Aanya Sharma|yes|adgips.ac.in"
URL = "/v1/profile/me/voice"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 2000  # EBML header, like MediaRecorder in Chrome
MP4 = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 2000  # like MediaRecorder in Safari


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


async def student(client: AsyncClient) -> dict[str, str]:
    return auth((await sign_in(client, STUDENT)).json()["token"])


async def upload(client: AsyncClient, headers: dict[str, str], data: bytes, seconds: int = 12):
    files = {"voice": ("v.webm", data, "audio/webm")}
    return await client.put(URL, files=files, data={"seconds": str(seconds)}, headers=headers)


def stored_files() -> list[Path]:
    root = Path(settings.media_dir)
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


async def test_voice_note_is_saved_and_played_back_to_me(client: AsyncClient) -> None:
    headers = await student(client)

    response = await upload(client, headers, WEBM, seconds=12)
    played = await client.get(URL, headers=headers)

    assert response.status_code == 200
    assert response.json()["voice_seconds"] == 12
    assert played.content == WEBM
    assert played.headers["content-type"] == "audio/webm"
    assert played.headers["cache-control"] == "no-store, private"


async def test_safari_recording_comes_back_as_mp4(client: AsyncClient) -> None:
    headers = await student(client)

    await upload(client, headers, MP4)

    assert (await client.get(URL, headers=headers)).headers["content-type"] == "audio/mp4"


async def test_a_new_note_replaces_the_old_file(client: AsyncClient) -> None:
    headers = await student(client)

    await upload(client, headers, WEBM)
    first = stored_files()
    await upload(client, headers, MP4)

    assert len(stored_files()) == 1
    assert stored_files() != first


async def test_voice_note_can_be_removed(client: AsyncClient) -> None:
    headers = await student(client)
    await upload(client, headers, WEBM)

    response = await client.delete(URL, headers=headers)

    assert response.json()["voice_seconds"] is None
    assert stored_files() == []
    assert (await client.get(URL, headers=headers)).status_code == 404


async def test_not_audio_is_refused(client: AsyncClient) -> None:
    headers = await student(client)

    response = await upload(client, headers, b"\xff\xd8\xff a jpeg")

    assert response.status_code == 422
    assert response.json()["code"] == "not_a_voice_note"


async def test_too_large_is_refused(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "voice_note_max_bytes", 1000)
    headers = await student(client)

    response = await upload(client, headers, WEBM)

    assert response.status_code == 413


@pytest.mark.parametrize("seconds", [0, 31])
async def test_length_must_be_1_to_30_seconds(client: AsyncClient, seconds: int) -> None:
    headers = await student(client)

    response = await upload(client, headers, WEBM, seconds=seconds)

    assert response.status_code == 422
