import copy
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from src.auth.dependencies import get_google_verifier
from src.main import app
from tests.auth.test_auth import fake_verify
from tests.profiles.test_profile import (
    BASICS,
    CARDS,
    GUESSES,
    PREFERENCES,
    PROMPTS,
    student,
)

URL = "/v1/profile/me/guesses"


@pytest.fixture(autouse=True)
def _fake_google() -> Iterator[None]:
    app.dependency_overrides[get_google_verifier] = lambda: fake_verify
    yield
    app.dependency_overrides.pop(get_google_verifier, None)


def with_card(n: int, **change: Any) -> dict[str, Any]:
    body = copy.deepcopy(GUESSES)
    body["cards"][n].update(change)
    return body


async def test_saving_guess_cards_marks_the_step_done(client: AsyncClient) -> None:
    headers = await student(client)

    body = (await client.put(URL, json=GUESSES, headers=headers)).json()

    assert body["guesses_done"] is True
    assert [g["question"] for g in body["guess_cards"]] == [
        "Chai or coffee?",
        "Best season of the year",
        "What I always carry in my bag",
    ]
    assert body["guess_cards"][1] == {
        **body["guess_cards"][1],
        "kind": "hot_take",
        "options": ["Summer", "Monsoon", "Winter"],
        "answer": 1,
    }
    mine = (await client.get("/v1/profile/me", headers=headers)).json()
    assert mine["guess_cards"] == body["guess_cards"]


async def test_the_profile_is_not_complete_without_guess_cards(client: AsyncClient) -> None:
    headers = await student(client)
    for path, body in [
        ("basics", BASICS), ("prompts", PROMPTS), ("cards", CARDS), ("preferences", PREFERENCES)
    ]:  # fmt: skip
        response = await client.put(f"/v1/profile/me/{path}", json=body, headers=headers)

    assert response.json()["guesses_done"] is False
    assert response.json()["complete"] is False

    response = await client.put(URL, json=GUESSES, headers=headers)

    assert response.json()["complete"] is True


async def test_any_kinds_are_fine(client: AsyncClient) -> None:
    headers = await student(client)
    body = copy.deepcopy(GUESSES)
    for card in body["cards"]:
        card["kind"] = "everyday"

    assert (await client.put(URL, json=body, headers=headers)).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"cards": GUESSES["cards"][:2]},
        {"cards": [*GUESSES["cards"], GUESSES["cards"][0]]},
        with_card(0, options=["Chai", "Coffee"]),
        with_card(0, options=["Chai", "Coffee", "Tea", "Water"]),
        with_card(0, options=["Chai", "chai", "Coffee"]),
        with_card(0, options=["Chai", "", "Coffee"]),
        with_card(0, options=["Chai", "x" * 41, "Coffee"]),
        with_card(0, answer=3),
        with_card(0, answer=-1),
        with_card(0, kind="made_up"),
        with_card(0, question=""),
        with_card(0, question="   "),
        with_card(0, question="q" * 91),
    ],
)
async def test_guess_cards_follow_the_rules(client: AsyncClient, body: dict[str, Any]) -> None:
    headers = await student(client)

    assert (await client.put(URL, json=body, headers=headers)).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"question": "Text me on 98765 43210"},
        {"question": "Guess my insta"},
        {"options": ["@quietstorm", "Coffee", "Neither"]},
        {"options": ["Chai", "www.mysite.com", "Neither"]},
    ],
)
async def test_guess_cards_cannot_hold_contact_details(
    client: AsyncClient, change: dict[str, Any]
) -> None:
    headers = await student(client)

    response = await client.put(URL, json=with_card(0, **change), headers=headers)

    assert response.status_code == 422
    assert "No numbers, handles or links" in response.text


async def test_saving_again_keeps_unchanged_cards_and_replaces_changed_ones(
    client: AsyncClient,
) -> None:
    headers = await student(client)
    before = (await client.put(URL, json=GUESSES, headers=headers)).json()["guess_cards"]

    after = (
        await client.put(URL, json=with_card(2, question="My comfort show"), headers=headers)
    ).json()["guess_cards"]

    assert [g["id"] for g in after[:2]] == [g["id"] for g in before[:2]]
    assert after[2]["id"] != before[2]["id"]
    assert after[2]["question"] == "My comfort show"


async def test_options_list_guess_kinds_and_suggestions(client: AsyncClient) -> None:
    body = (await client.get("/v1/profile/options")).json()

    assert body["guess_kinds"] == [
        {"value": "everyday", "label": "Everyday choice"},
        {"value": "hot_take", "label": "Hot take"},
        {"value": "little_thing", "label": "Little thing"},
    ]
    assert set(body["guess_suggestions"]) == {"everyday", "hot_take", "little_thing"}
    assert all(body["guess_suggestions"].values())
    assert body["guess_question_max"] == 90
    assert body["guess_option_max"] == 40
