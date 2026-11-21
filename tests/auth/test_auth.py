from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from src.auth.dependencies import get_google_verifier
from src.auth.google import GoogleIdentity
from src.auth.models import AuthSession
from src.database import engine
from src.exceptions import Unauthenticated
from src.main import app

ME = "/v1/auth/me"
SIGN_IN = "/v1/auth/google"
SIGN_OUT = "/v1/auth/sign-out"


async def fake_verify(credential: str) -> GoogleIdentity:
    """Test credentials look like 'sub|email|name|verified'; 'bad' is rejected."""
    if credential == "bad":
        raise Unauthenticated("Invalid Google credential")
    sub, email, name, verified = credential.split("|")
    return GoogleIdentity(
        sub=sub, email=email, email_verified=verified == "yes", name=name, hosted_domain=None
    )


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


async def sign_in(client: AsyncClient, credential: str = "sub-1|aanya@gmail.com|Aanya|yes"):
    return await client.post(SIGN_IN, json={"credential": credential})


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_first_sign_in_creates_account_and_returns_token(client: AsyncClient) -> None:
    response = await sign_in(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["email"] == "aanya@gmail.com"
    assert body["user"]["name"] == "Aanya"
    assert body["user"]["is_admin"] is False


async def test_signing_in_again_returns_the_same_account(client: AsyncClient) -> None:
    first = (await sign_in(client)).json()
    second = (await sign_in(client, "sub-1|aanya.new@gmail.com|Aanya K|yes")).json()

    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["email"] == "aanya.new@gmail.com"
    assert second["user"]["name"] == "Aanya K"
    assert second["token"] != first["token"]


async def test_invalid_google_credential_is_rejected(client: AsyncClient) -> None:
    response = await sign_in(client, "bad")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_google_account_without_verified_email_is_rejected(client: AsyncClient) -> None:
    response = await sign_in(client, "sub-2|x@gmail.com|X|no")

    assert response.status_code == 401


async def test_me_returns_the_signed_in_account(client: AsyncClient) -> None:
    token = (await sign_in(client)).json()["token"]

    response = await client.get(ME, headers=auth(token))

    assert response.status_code == 200
    assert response.json()["email"] == "aanya@gmail.com"


async def test_me_without_token_is_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(ME)

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_me_with_unknown_token_is_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(ME, headers=auth("not-a-real-token"))

    assert response.status_code == 401


async def test_sign_out_ends_only_that_session(client: AsyncClient) -> None:
    phone = (await sign_in(client)).json()["token"]
    laptop = (await sign_in(client)).json()["token"]

    response = await client.post(SIGN_OUT, headers=auth(phone))

    assert response.status_code == 204
    assert (await client.get(ME, headers=auth(phone))).status_code == 401
    assert (await client.get(ME, headers=auth(laptop))).status_code == 200


async def test_expired_session_is_unauthenticated(client: AsyncClient) -> None:
    token = (await sign_in(client)).json()["token"]
    async with engine.begin() as conn:
        await conn.execute(
            update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    response = await client.get(ME, headers=auth(token))

    assert response.status_code == 401


async def test_admin_emails_get_admin_rights(client: AsyncClient) -> None:
    response = await sign_in(client, "sub-9|Admin@Gmail.com|Admin|yes")

    assert response.json()["user"]["is_admin"] is True


async def test_sign_in_is_rate_limited_per_ip(client: AsyncClient) -> None:
    for _ in range(20):
        await sign_in(client)

    response = await sign_in(client)

    assert response.status_code == 429
