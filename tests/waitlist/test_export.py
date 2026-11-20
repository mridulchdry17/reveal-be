from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS


async def test_export_requires_admin_token(client: AsyncClient) -> None:
    missing = await client.get("/v1/waitlist/export")
    wrong = await client.get("/v1/waitlist/export", headers={"X-Admin-Token": "nope"})

    assert missing.status_code == 403
    assert wrong.status_code == 403


async def test_export_lists_entries_in_signup_order(client: AsyncClient) -> None:
    for enrollment, email in [("22EC1047", "aanya@gmail.com"), ("21CS0417", "arjun@gmail.com")]:
        await client.post(
            "/v1/waitlist",
            json={"enrollment_number": enrollment, "email": email, "confirmed_adult": True},
        )

    response = await client.get("/v1/waitlist/export", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "enrollment_number,email,source,joined_at"
    assert lines[1].startswith("22EC1047,aanya@gmail.com,")
    assert lines[2].startswith("21CS0417,arjun@gmail.com,")
