from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from src.auth.dependencies import get_google_verifier
from src.main import app
from tests.auth.test_auth import auth, fake_verify, sign_in
from tests.verification.test_id_card import JPEG, PNG, photos, submit

ADMIN = "sub-a|admin@gmail.com|Admin|yes"
STUDENT = "sub-s|rohan@gmail.com|Rohan|yes"


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


async def token(client: AsyncClient, credential: str) -> str:
    return (await sign_in(client, credential)).json()["token"]


async def waiting_review(client: AsyncClient) -> tuple[str, str, str]:
    """A student who sent photos, and an admin. Returns (admin, student, review id)."""
    admin = await token(client, ADMIN)
    student = await token(client, STUDENT)
    await submit(client, student)
    reviews = (await client.get("/v1/admin/reviews", headers=auth(admin))).json()
    return admin, student, reviews[0]["id"]


async def test_admin_sees_waiting_reviews_with_the_student(client: AsyncClient) -> None:
    admin, _, _ = await waiting_review(client)

    response = await client.get("/v1/admin/reviews", headers=auth(admin))

    assert response.status_code == 200
    [review] = response.json()
    assert review["user"]["email"] == "rohan@gmail.com"
    assert review["user"]["name"] == "Rohan"


async def test_admin_can_view_both_photos_uncached(client: AsyncClient) -> None:
    admin, _, review = await waiting_review(client)

    selfie = await client.get(f"/v1/admin/reviews/{review}/photos/selfie", headers=auth(admin))
    id_card = await client.get(f"/v1/admin/reviews/{review}/photos/id_card", headers=auth(admin))

    assert selfie.status_code == 200
    assert selfie.content == JPEG
    assert selfie.headers["cache-control"] == "no-store, private"
    assert id_card.content == PNG


@pytest.mark.parametrize(
    "path",
    ["/v1/admin/reviews", "/v1/admin/actions"],
)
async def test_students_cannot_use_admin_endpoints(client: AsyncClient, path: str) -> None:
    student = await token(client, STUDENT)

    response = await client.get(path, headers=auth(student))

    assert response.status_code == 403


async def test_students_cannot_see_review_photos(client: AsyncClient) -> None:
    _, student, review = await waiting_review(client)

    response = await client.get(f"/v1/admin/reviews/{review}/photos/selfie", headers=auth(student))

    assert response.status_code == 403


async def test_approving_verifies_the_student_and_deletes_the_photos(
    client: AsyncClient,
) -> None:
    admin, student, review = await waiting_review(client)

    response = await client.post(f"/v1/admin/reviews/{review}/approve", headers=auth(admin))

    assert response.status_code == 204
    me = (await client.get("/v1/auth/me", headers=auth(student))).json()
    assert me["verified"] is True
    assert me["verified_via"] == "id_card"
    status = (await client.get("/v1/verification/me", headers=auth(student))).json()
    assert status["status"] == "approved"
    assert photos() == []
    assert (await client.get("/v1/admin/reviews", headers=auth(admin))).json() == []


async def test_rejecting_shows_the_reason_and_deletes_the_photos(client: AsyncClient) -> None:
    admin, student, review = await waiting_review(client)

    response = await client.post(
        f"/v1/admin/reviews/{review}/reject",
        json={"reason": "ID photo is blurry"},
        headers=auth(admin),
    )

    assert response.status_code == 204
    status = (await client.get("/v1/verification/me", headers=auth(student))).json()
    assert status == {
        "status": "rejected",
        "submitted_at": status["submitted_at"],
        "reject_reason": "ID photo is blurry",
    }
    assert (await client.get("/v1/auth/me", headers=auth(student))).json()["verified"] is False
    assert photos() == []
    # They can send new photos.
    assert (await submit(client, student)).status_code == 201


async def test_a_review_can_only_be_decided_once(client: AsyncClient) -> None:
    admin, _, review = await waiting_review(client)
    await client.post(f"/v1/admin/reviews/{review}/approve", headers=auth(admin))

    response = await client.post(
        f"/v1/admin/reviews/{review}/reject", json={"reason": "x"}, headers=auth(admin)
    )

    assert response.status_code == 409
    assert response.json()["code"] == "already_reviewed"


async def test_admin_can_let_a_signed_in_student_in(client: AsyncClient) -> None:
    admin = await token(client, ADMIN)
    student = await token(client, STUDENT)

    response = await client.post(
        "/v1/admin/let-in",
        json={"email": " Rohan@Gmail.com ", "note": "First-year, CSE"},
        headers=auth(admin),
    )

    assert response.status_code == 200
    assert response.json()["email"] == "rohan@gmail.com"
    me = (await client.get("/v1/auth/me", headers=auth(student))).json()
    assert me["verified"] is True
    assert me["verified_via"] == "admin"


async def test_letting_in_an_unknown_email_explains(client: AsyncClient) -> None:
    admin = await token(client, ADMIN)

    response = await client.post(
        "/v1/admin/let-in", json={"email": "nobody@gmail.com"}, headers=auth(admin)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "account_not_found"


async def test_letting_in_someone_already_verified_changes_nothing(client: AsyncClient) -> None:
    admin = await token(client, ADMIN)
    await token(client, "sub-c|asha.1@adgips.ac.in|Asha|yes|adgips.ac.in")

    response = await client.post(
        "/v1/admin/let-in", json={"email": "asha.1@adgips.ac.in"}, headers=auth(admin)
    )

    assert response.status_code == 409
    assert response.json()["code"] == "already_verified"


async def test_every_decision_is_logged(client: AsyncClient) -> None:
    admin, _, review = await waiting_review(client)
    await client.post(
        f"/v1/admin/reviews/{review}/reject", json={"reason": "Blurry"}, headers=auth(admin)
    )
    await client.post("/v1/admin/let-in", json={"email": "rohan@gmail.com"}, headers=auth(admin))

    log = (await client.get("/v1/admin/actions", headers=auth(admin))).json()

    assert [(a["action"], a["target_email"], a["note"]) for a in log] == [
        ("let_in", "rohan@gmail.com", None),
        ("reject", "rohan@gmail.com", "Blurry"),
    ]
    assert {a["admin_email"] for a in log} == {"admin@gmail.com"}
