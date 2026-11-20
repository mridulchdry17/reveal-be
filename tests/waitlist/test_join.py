from httpx import AsyncClient

URL = "/v1/waitlist"


async def join(client: AsyncClient, enrollment: str, email: str):
    return await client.post(URL, json={"enrollment_number": enrollment, "email": email})


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


async def test_enrollment_taken_by_someone_else_is_refused(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")

    response = await join(client, "22EC1047", "someone-else@gmail.com")

    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"


async def test_email_taken_by_someone_else_is_refused(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")

    response = await join(client, "21CS0417", "aanya@gmail.com")

    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"


async def test_refusal_does_not_say_which_detail_matched(client: AsyncClient) -> None:
    await join(client, "22EC1047", "aanya@gmail.com")

    by_enrollment = await join(client, "22EC1047", "x@gmail.com")
    by_email = await join(client, "21CS0417", "aanya@gmail.com")

    assert by_enrollment.json() == by_email.json()


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
