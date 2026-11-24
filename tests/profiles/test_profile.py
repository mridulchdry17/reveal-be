from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from src.auth.dependencies import get_google_verifier
from src.main import app
from tests.auth.test_auth import auth, fake_verify, sign_in

STUDENT = "sub-c|aanya.0411@adgips.ac.in|Aanya Sharma|yes|adgips.ac.in"  # verified on sign-in
UNVERIFIED = "sub-u|rohan@gmail.com|Rohan|yes"

BASICS = {
    "nickname": "Quiet storm",
    "vibe": "Night owl",
    "interests": ["Music", "Films", "Trekking"],
}
PROMPTS = {
    "prompts": [
        {"question": "My ideal Sunday", "answer": "Chai, a long walk, zero plans"},
        {"question": "Hot take", "answer": "Maggi is a full meal"},
        {"question": "Green flag in people", "answer": "They remember small things"},
    ]
}
GUESSES = {
    "cards": [
        {
            "kind": "everyday",
            "question": "Chai or coffee?",
            "options": ["Chai", "Coffee", "Neither"],
            "answer": 0,
        },
        {
            "kind": "hot_take",
            "question": "Best season of the year",
            "options": ["Summer", "Monsoon", "Winter"],
            "answer": 1,
        },
        {
            "kind": "little_thing",
            "question": "What I always carry in my bag",
            "options": ["Earphones", "A book", "Snacks"],
            "answer": 2,
        },
    ]
}
CARDS = {
    "branch": "CSE",
    "year": 2,
    "hometown": "Jaipur",
    "looking_for": "serious",
}
PREFERENCES = {"gender": "woman", "interested_in": "men", "match_on": ["shared_interests"]}


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


async def student(client: AsyncClient, credential: str = STUDENT) -> dict[str, str]:
    return auth((await sign_in(client, credential)).json()["token"])


async def test_options_list_the_choices(client: AsyncClient) -> None:
    body = (await client.get("/v1/profile/options")).json()

    assert "Night owl" in body["vibes"]
    assert body["min_interests"] == 3
    assert {"value": "serious", "label": "Something serious"} in body["looking_for"]


async def test_new_profile_is_empty_with_first_name_from_google(client: AsyncClient) -> None:
    headers = await student(client)

    body = (await client.get("/v1/profile/me", headers=headers)).json()

    assert body["first_name"] == "Aanya"
    assert body["nickname"] is None
    assert "shown_cards" not in body
    assert body["complete"] is False


async def test_profile_is_for_verified_students_only(client: AsyncClient) -> None:
    headers = await student(client, UNVERIFIED)

    assert (await client.get("/v1/profile/me", headers=headers)).status_code == 403
    assert (
        await client.put("/v1/profile/me/basics", json=BASICS, headers=headers)
    ).status_code == 403


async def test_filling_every_screen_completes_the_profile(client: AsyncClient) -> None:
    headers = await student(client)

    for path, body in [
        ("basics", BASICS),
        ("prompts", PROMPTS),
        ("guesses", GUESSES),
        ("cards", CARDS),
        ("preferences", PREFERENCES),
    ]:
        response = await client.put(f"/v1/profile/me/{path}", json=body, headers=headers)
        assert response.status_code == 200, response.text

    mine = (await client.get("/v1/profile/me", headers=headers)).json()
    assert mine["complete"] is True
    assert mine["nickname"] == "Quiet storm"
    assert [p["question"] for p in mine["prompts"]] == [
        "My ideal Sunday",
        "Hot take",
        "Green flag in people",
    ]
    assert mine["hometown"] == "Jaipur"
    assert mine["gender"] == "woman"


async def test_each_screen_reports_its_own_progress(client: AsyncClient) -> None:
    headers = await student(client)

    body = (await client.put("/v1/profile/me/basics", json=BASICS, headers=headers)).json()

    assert (body["basics_done"], body["prompts_done"], body["complete"]) == (True, False, False)


async def test_saving_prompts_again_replaces_them(client: AsyncClient) -> None:
    headers = await student(client)
    await client.put("/v1/profile/me/prompts", json=PROMPTS, headers=headers)
    changed = {"prompts": [*PROMPTS["prompts"][:2], {"question": "Hot take 2", "answer": "Rain"}]}

    body = (await client.put("/v1/profile/me/prompts", json=changed, headers=headers)).json()

    assert len(body["prompts"]) == 3
    assert body["prompts"][2] == {**body["prompts"][2], "question": "Hot take 2", "answer": "Rain"}


@pytest.mark.parametrize(
    "answer",
    ["Call me 98765 43210", "Find me @quietstorm", "insta: quiet.storm", "www.mysite.com"],
)
async def test_prompts_cannot_hold_contact_details(client: AsyncClient, answer: str) -> None:
    headers = await student(client)
    body = {"prompts": [*PROMPTS["prompts"][:2], {"question": "Hot take", "answer": answer}]}

    response = await client.put("/v1/profile/me/prompts", json=body, headers=headers)

    assert response.status_code == 422
    assert "No numbers, handles or links" in response.text


async def test_nickname_cannot_be_a_handle(client: AsyncClient) -> None:
    headers = await student(client)

    response = await client.put(
        "/v1/profile/me/basics", json={**BASICS, "nickname": "@aanya.s"}, headers=headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"vibe": "Made up vibe"},
        {"interests": ["Music", "Films"]},
        {"interests": ["Music", "music", "MUSIC"]},
        {"interests": ["a", "b", "c", "d", "e", "f", "g"]},
    ],
)
async def test_basics_follow_the_rules(client: AsyncClient, change: dict[str, object]) -> None:
    headers = await student(client)

    response = await client.put("/v1/profile/me/basics", json={**BASICS, **change}, headers=headers)

    assert response.status_code == 422


async def test_three_different_prompts_are_needed(client: AsyncClient) -> None:
    headers = await student(client)
    same = {"prompts": [PROMPTS["prompts"][0]] * 3}

    response = await client.put("/v1/profile/me/prompts", json=same, headers=headers)

    assert response.status_code == 422


async def test_old_apps_sending_shown_cards_still_save(client: AsyncClient) -> None:
    headers = await student(client)

    response = await client.put(
        "/v1/profile/me/cards", json={**CARDS, "shown_cards": ["photo"]}, headers=headers
    )

    assert response.status_code == 200
    assert "shown_cards" not in response.json()


async def test_blank_nickname_is_refused(client: AsyncClient) -> None:
    headers = await student(client)

    response = await client.put(
        "/v1/profile/me/basics", json={**BASICS, "nickname": "     "}, headers=headers
    )

    assert response.status_code == 422


async def test_contact_is_saved_cleaned_up_and_only_shown_to_me(client: AsyncClient) -> None:
    headers = await student(client)

    url = "/v1/profile/me/contact"
    insta_body = {"kind": "instagram", "value": " @Aanya.Reads "}
    insta = await client.put(url, json=insta_body, headers=headers)
    phone_body = {"kind": "phone", "value": "+91 98765-43210"}
    phone = await client.put(url, json=phone_body, headers=headers)

    assert insta.status_code == 200
    assert insta.json()["contact"] == {"kind": "instagram", "value": "aanya.reads"}
    assert phone.json()["contact"] == {"kind": "phone", "value": "9876543210"}
    me = (await client.get("/v1/profile/me", headers=headers)).json()
    assert me["contact"] == {"kind": "phone", "value": "9876543210"}


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("instagram", "has space"),
        ("instagram", "a..b"),
        ("phone", "12345"),
        ("phone", "5876543210"),
    ],
)
async def test_bad_contact_is_refused_on_the_field(
    client: AsyncClient, kind: str, value: str
) -> None:
    headers = await student(client)

    response = await client.put(
        "/v1/profile/me/contact", json={"kind": kind, "value": value}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "value"]


async def test_contact_can_be_removed(client: AsyncClient) -> None:
    headers = await student(client)
    await client.put(
        "/v1/profile/me/contact", json={"kind": "instagram", "value": "aanya"}, headers=headers
    )

    response = await client.delete("/v1/profile/me/contact", headers=headers)

    assert response.status_code == 200
    assert response.json()["contact"] is None


async def test_contact_is_optional_for_a_complete_profile(client: AsyncClient) -> None:
    headers = await student(client)
    for path, body in [
        ("basics", BASICS), ("prompts", PROMPTS), ("guesses", GUESSES), ("cards", CARDS),
        ("preferences", PREFERENCES),
    ]:  # fmt: skip
        response = await client.put(f"/v1/profile/me/{path}", json=body, headers=headers)

    assert response.json()["complete"] is True
    assert response.json()["contact"] is None
