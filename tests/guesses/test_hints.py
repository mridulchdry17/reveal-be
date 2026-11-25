from datetime import timedelta

from httpx import AsyncClient

from tests.drops.helpers import Clock, drop, finished, matched_pair
from tests.guesses.test_guesses import RIGHT, card_ids, guess, in_drop
from tests.swaps.test_swaps import thread

Headers = dict[str, str]


async def hint(client: AsyncClient, headers: Headers, card_id: str):
    return await client.post(f"/v1/guesses/{card_id}/hint", headers=headers)


async def test_a_hint_strikes_one_wrong_option(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    cards = card_ids(item["profile"])
    assert (await drop(client, aanya))["hint_used"] is False

    response = await hint(client, aanya, cards[1])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["card_id"] == cards[1]
    assert body["struck"] in {0, 1, 2} - {RIGHT[1]}
    tonight = await drop(client, aanya)
    assert tonight["hint_used"] is True
    shown = tonight["items"][0]["profile"]["guess_cards"]
    assert [g["struck"] for g in shown] == [None, body["struck"], None]


async def test_asking_again_for_the_same_card_gives_the_same_option(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    card = card_ids(item["profile"])[0]

    first = (await hint(client, aanya, card)).json()
    for _ in range(5):
        assert (await hint(client, aanya, card)).json() == first


async def test_one_hint_a_night(client: AsyncClient, clock: Clock) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])
    assert (await hint(client, aanya, cards[0])).status_code == 200

    second = await hint(client, aanya, cards[1])

    assert second.status_code == 409
    assert second.json()["code"] == "hint_already_used"
    his_cards = card_ids((await thread(client, kabir, match_id))["profile"])
    assert (await hint(client, kabir, his_cards[0])).status_code == 200  # his own hint
    clock.at += timedelta(days=1)
    assert (await hint(client, aanya, cards[1])).status_code == 200


async def test_the_night_turns_at_nine_pm(client: AsyncClient, clock: Clock) -> None:
    aanya, _, match_id = await matched_pair(client)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])
    await hint(client, aanya, cards[0])

    clock.at += timedelta(hours=4)  # 2 AM: still the same drop night
    assert (await hint(client, aanya, cards[1])).status_code == 409
    clock.at += timedelta(hours=19)  # 9 PM next day
    assert (await hint(client, aanya, cards[1])).status_code == 200


async def test_no_hint_on_a_card_already_guessed(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    card = card_ids(item["profile"])[0]
    await guess(client, aanya, card, RIGHT[0])

    response = await hint(client, aanya, card)

    assert response.status_code == 409
    assert response.json()["code"] == "already_guessed"
    assert (await drop(client, aanya))["hint_used"] is False


async def test_a_hint_then_a_guess_keeps_the_struck_option(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    card = card_ids(item["profile"])[2]
    struck = (await hint(client, aanya, card)).json()["struck"]

    await guess(client, aanya, card, RIGHT[2])

    [shown] = (await drop(client, aanya))["items"]
    assert shown["profile"]["guess_cards"][2]["struck"] == struck
    assert (await hint(client, aanya, card)).json()["struck"] == struck


async def test_hints_follow_who_may_guess(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    cards = card_ids(item["profile"])
    meera = await finished(client, "Meera", "woman", "men")  # Kabir isn't in her drop yet

    assert (await hint(client, meera, cards[0])).status_code == 404
    assert (await hint(client, kabir, cards[0])).status_code == 404  # his own card
    missing = await hint(client, aanya, "00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_struck_shows_in_the_chat_too(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)
    card = card_ids((await thread(client, aanya, match_id))["profile"])[1]

    struck = (await hint(client, aanya, card)).json()["struck"]

    shown = (await thread(client, aanya, match_id))["profile"]["guess_cards"]
    assert [g["struck"] for g in shown] == [None, struck, None]
