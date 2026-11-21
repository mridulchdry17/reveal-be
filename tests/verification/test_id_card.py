import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from src.auth.dependencies import get_google_verifier
from src.config import settings
from src.database import engine
from src.main import app
from src.verification.models import VerificationRequest
from tests.auth.test_auth import auth, fake_verify, sign_in

STATUS = "/v1/verification/me"
SUBMIT = "/v1/verification/id-card"

JPEG = b"\xff\xd8\xff\xe0" + b"selfie" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"idcard" * 100


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


def photos() -> list[Path]:
    root = Path(settings.verification_photos_dir)
    return sorted(root.iterdir()) if root.exists() else []


async def submit(client: AsyncClient, token: str, selfie: bytes = JPEG, id_card: bytes = PNG):
    return await client.post(
        SUBMIT,
        files={
            "selfie": ("selfie.jpg", selfie, "image/jpeg"),
            "id_card": ("id.png", id_card, "image/png"),
        },
        headers=auth(token),
    )


async def token_for(client: AsyncClient, credential: str = "sub-1|aanya@gmail.com|Aanya|yes"):
    return (await sign_in(client, credential)).json()["token"]


async def test_status_is_none_before_sending(client: AsyncClient) -> None:
    token = await token_for(client)

    response = await client.get(STATUS, headers=auth(token))

    assert response.status_code == 200
    assert response.json() == {"status": "none", "submitted_at": None, "reject_reason": None}


async def test_sending_photos_stores_them_privately_and_waits_for_review(
    client: AsyncClient,
) -> None:
    token = await token_for(client)

    response = await submit(client, token)

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert (await client.get(STATUS, headers=auth(token))).json()["status"] == "pending"
    stored = photos()
    assert len(stored) == 2
    assert {p.read_bytes() for p in stored} == {JPEG, PNG}
    assert all(os.stat(p).st_mode & 0o777 == 0o600 for p in stored)
    # Still not a verified student until a person approves.
    assert (await client.get("/v1/auth/me", headers=auth(token))).json()["verified"] is False


async def test_cannot_send_again_while_waiting(client: AsyncClient) -> None:
    token = await token_for(client)
    await submit(client, token)

    response = await submit(client, token)

    assert response.status_code == 409
    assert response.json()["code"] == "already_submitted"
    assert len(photos()) == 2


async def test_verified_students_do_not_send_photos(client: AsyncClient) -> None:
    token = await token_for(client, "sub-c|aanya.1@adgips.ac.in|Aanya|yes|adgips.ac.in")

    response = await submit(client, token)

    assert response.status_code == 409
    assert response.json()["code"] == "already_verified"
    assert photos() == []


async def test_files_that_are_not_photos_are_rejected(client: AsyncClient) -> None:
    token = await token_for(client)

    response = await submit(client, token, id_card=b"%PDF-1.7 not a photo")

    assert response.status_code == 422
    assert response.json()["code"] == "not_a_photo"
    assert photos() == []


async def test_photos_over_the_size_limit_are_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "verification_photo_max_bytes", 100)
    token = await token_for(client)

    response = await submit(client, token)

    assert response.status_code == 413
    assert response.json()["code"] == "photo_too_large"
    assert photos() == []


async def test_sending_photos_needs_sign_in(client: AsyncClient) -> None:
    response = await client.post(
        SUBMIT,
        files={"selfie": ("s.jpg", JPEG, "image/jpeg"), "id_card": ("i.png", PNG, "image/png")},
    )

    assert response.status_code == 401


async def test_sending_again_after_rejection_replaces_the_old_photos(client: AsyncClient) -> None:
    token = await token_for(client)
    await submit(client, token)
    old = photos()
    async with engine.begin() as conn:
        await conn.execute(
            update(VerificationRequest).values(status="rejected", reject_reason="Blurry")
        )
    assert (await client.get(STATUS, headers=auth(token))).json()["reject_reason"] == "Blurry"

    response = await submit(client, token)

    assert response.status_code == 201
    assert response.json() == {
        "status": "pending",
        "submitted_at": response.json()["submitted_at"],
        "reject_reason": None,
    }
    assert len(photos()) == 2
    assert not any(p.exists() for p in old)


async def test_unreviewed_photos_are_deleted_after_the_time_limit(client: AsyncClient) -> None:
    first = await token_for(client)
    await submit(client, first)
    async with engine.begin() as conn:
        await conn.execute(
            update(VerificationRequest).values(
                submitted_at=datetime.now(UTC)
                - timedelta(days=settings.verification_photo_days, minutes=1)
            )
        )
    second = await token_for(client, "sub-2|rohan@gmail.com|Rohan|yes")

    await submit(client, second)  # any new upload sweeps expired ones

    assert (await client.get(STATUS, headers=auth(first))).json()["status"] == "expired"
    assert len(photos()) == 2  # only the second student's


async def test_uploads_are_rate_limited_per_ip(client: AsyncClient) -> None:
    token = await token_for(client)
    for _ in range(settings.verification_uploads_per_ip_per_hour):
        await submit(client, token, id_card=b"nope")

    response = await submit(client, token)

    assert response.status_code == 429
