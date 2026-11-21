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

COLLEGE_EMAIL = "/v1/auth/college-email"
ME = "/v1/auth/me"
SIGN_IN = "/v1/auth/google"
SIGN_OUT = "/v1/auth/sign-out"


async def fake_verify(credential: str) -> GoogleIdentity:
    """Test credentials look like 'sub|email|name|verified[|hosted domain]'; 'bad' is rejected."""
    if credential == "bad":
        raise Unauthenticated("Invalid Google credential")
    sub, email, name, verified, *hd = credential.split("|")
    return GoogleIdentity(
        sub=sub,
        email=email,
        email_verified=verified == "yes",
        name=name,
        hosted_domain=hd[0] if hd else None,
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
    assert body["user"]["verified"] is False
    assert body["user"]["verified_via"] is None


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


# College email verification

COLLEGE = "sub-c|aanya.0411@adgips.ac.in|Aanya|yes|adgips.ac.in"


async def verify_college(client: AsyncClient, token: str, credential: str = COLLEGE):
    return await client.post(COLLEGE_EMAIL, json={"credential": credential}, headers=auth(token))


async def test_college_google_account_verifies_the_signed_in_user(client: AsyncClient) -> None:
    token = (await sign_in(client)).json()["token"]

    response = await verify_college(client, token)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "aanya@gmail.com"  # still signed in with personal Gmail
    assert body["verified"] is True
    assert body["verified_via"] == "college_email"
    assert (await client.get(ME, headers=auth(token))).json()["verified"] is True


@pytest.mark.parametrize(
    "credential",
    [
        "sub-c|aanya@gmail.com|Aanya|yes",  # personal Gmail
        "sub-c|aanya@adgips.ac.in|Aanya|yes",  # college address, but no hd claim
        "sub-c|aanya@other.edu|Aanya|yes|other.edu",  # another college's Workspace
        "sub-c|aanya@adgips.ac.in|Aanya|no|adgips.ac.in",  # email not verified by Google
    ],
)
async def test_only_a_college_workspace_account_verifies(
    client: AsyncClient, credential: str
) -> None:
    token = (await sign_in(client)).json()["token"]

    response = await verify_college(client, token, credential)

    assert response.status_code == 403
    assert response.json()["code"] == "not_college_account"
    assert (await client.get(ME, headers=auth(token))).json()["verified"] is False


async def test_one_college_email_verifies_one_account(client: AsyncClient) -> None:
    first = (await sign_in(client)).json()["token"]
    second = (await sign_in(client, "sub-2|rohan@gmail.com|Rohan|yes")).json()["token"]
    await verify_college(client, first)

    response = await verify_college(client, second)

    assert response.status_code == 409
    assert response.json()["code"] == "college_email_taken"
    assert (await client.get(ME, headers=auth(second))).json()["verified"] is False


async def test_verifying_again_changes_nothing(client: AsyncClient) -> None:
    token = (await sign_in(client)).json()["token"]
    await verify_college(client, token)

    response = await verify_college(
        client, token, "sub-d|other.0412@adgips.ac.in|Other|yes|adgips.ac.in"
    )

    assert response.status_code == 200
    assert response.json()["verified"] is True
    # The first college email still holds the claim; the second is free for its owner.
    other = (await sign_in(client, "sub-d|other.0412@adgips.ac.in|Other|yes|adgips.ac.in")).json()
    assert other["user"]["verified"] is True


async def test_college_email_needs_sign_in(client: AsyncClient) -> None:
    response = await client.post(COLLEGE_EMAIL, json={"credential": COLLEGE})

    assert response.status_code == 401


async def test_signing_in_with_a_college_account_verifies_straight_away(
    client: AsyncClient,
) -> None:
    response = await sign_in(client, COLLEGE)

    assert response.json()["user"]["verified"] is True
    assert response.json()["user"]["verified_via"] == "college_email"


async def test_college_sign_in_does_not_steal_a_claimed_email(client: AsyncClient) -> None:
    token = (await sign_in(client)).json()["token"]
    await verify_college(client, token)

    response = await sign_in(client, COLLEGE)

    assert response.status_code == 200
    assert response.json()["user"]["verified"] is False
