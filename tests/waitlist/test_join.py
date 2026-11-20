from typing import Any

from httpx import AsyncClient, Response

from tests.conftest import ADMIN_HEADERS

URL = "/v1/waitlist"


async def join(client: AsyncClient, enrollment: str, email: str, **extra: Any) -> Response:
    body = {"enrollment_number": enrollment, "email": email, "confirmed_adult": True, **extra}
    return await client.post(URL, json=body)


async def export_rows(client: AsyncClient) -> list[str]:
    response = await client.get(f"{URL}/export", headers=ADMIN_HEADERS)
    return response.text.strip().splitlines()[1:]


async def test_first_person_is_first_in_line(client: AsyncClient) -> None:
    response = await join(client, "22EC1047", "aanya@gmail.com")

    assert response.status_code == 201
    assert response.json() == {"position": 1, "already_joined": False}


async def test_positions_follow_signup_order(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")
    response = await join(client, "21CS0417", "arjun@gmail.com")

    assert response.json()["position"] == 2


async def test_joining_again_with_same_details_returns_existing_place(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")
    await join(client, "21CS0417", "arjun@gmail.com")

    response = await join(client, "22ec-1047", "AANYA@gmail.com")

    assert response.status_code == 200
    assert response.json() == {"position": 1, "already_joined": True}


async def test_someone_elses_enrollment_looks_like_a_normal_join(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")

    taken = await join(client, "22EC1047", "prankster@gmail.com")
    fresh = await join(client, "21CS0417", "arjun@gmail.com")

    # Same status and shape as a genuine new join, so nobody can learn who signed up.
    assert taken.status_code == fresh.status_code == 201
    assert taken.json() == {"position": 2, "already_joined": False}
    assert fresh.json() == {"position": 2, "already_joined": False}


async def test_someone_elses_entry_is_not_overwritten(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")

    await join(client, "22EC1047", "prankster@gmail.com")
    await join(client, "30ME0001", "aanya@gmail.com")

    rows = await export_rows(client)
    assert len(rows) == 1
    assert rows[0].startswith("22EC1047,aanya@gmail.com,")


async def test_source_is_saved_and_bad_values_are_dropped(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com", source="WA")
    response = await join(client, "21CS0417", "arjun@gmail.com", source="<script>")

    assert response.status_code == 201
    rows = await export_rows(client)
    assert rows[0].startswith("22EC1047,aanya@gmail.com,wa,")
    assert rows[1].startswith("21CS0417,arjun@gmail.com,,")


async def test_must_confirm_18_or_older(client: AsyncClient) -> None:
    response = await join(client, "22EC1047", "aanya@gmail.com", confirmed_adult=False)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "confirmed_adult"]


async def test_invalid_enrollment_number_is_rejected(client: AsyncClient) -> None:
    response = await join(client, "abc", "aanya@gmail.com")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "enrollment_number"]


async def test_invalid_email_is_rejected(client: AsyncClient) -> None:
    response = await join(client, "22EC1047", "not-an-email")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]


async def test_too_many_attempts_from_one_ip_are_blocked(client: AsyncClient) -> None:
    for i in range(5):
        response = await join(client, f"22EC10{i:02d}", f"student{i}@gmail.com")
        assert response.status_code == 201

    response = await join(client, "22EC1099", "student99@gmail.com")

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
