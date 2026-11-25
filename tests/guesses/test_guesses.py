from datetime import timedelta
from io import BytesIO
from typing import Any

from httpx import AsyncClient
from PIL import Image, ImageDraw, ImageStat
from sqlalchemy import text

from src.database import engine
from tests.drops.helpers import Clock, drop, finished, matched_pair
from tests.swaps.test_swaps import add_photo, add_voice, swap, thread

Headers = dict[str, str]
# GUESSES in tests/profiles/test_profile.py: the true options are 0, 1 and 2.
RIGHT = [0, 1, 2]


async def guess(client: AsyncClient, headers: Headers, card_id: str, pick: int):
    return await client.post(f"/v1/guesses/{card_id}", json={"pick": pick}, headers=headers)


async def in_drop(client: AsyncClient) -> tuple[Headers, Headers, dict[str, Any]]:
    """Aanya and Kabir; he's in her drop tonight. Returns her drop item for him."""
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    [item] = (await drop(client, aanya))["items"]
    return aanya, kabir, item


def card_ids(profile: dict[str, Any]) -> list[str]:
    return [g["id"] for g in profile["guess_cards"]]


async def test_answers_stay_hidden_until_you_guess(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    cards = item["profile"]["guess_cards"]

    assert [g["question"] for g in cards] == [
        "Chai or coffee?",
        "Best season of the year",
        "What I always carry in my bag",
    ]
    assert cards[0]["options"] == ["Chai", "Coffee", "Neither"]
    assert all(g["answer"] is None and g["picked"] is None for g in cards)
    assert item["profile"]["right_guesses"] == 0

    response = await guess(client, aanya, cards[1]["id"], 2)

    assert response.status_code == 200
    assert response.json() == {"correct": False, "answer": 1, "picked": 2}
    [item] = (await drop(client, aanya))["items"]
    after = item["profile"]["guess_cards"]
    assert (after[1]["picked"], after[1]["answer"]) == (2, 1)
    assert all(g["answer"] is None for g in (after[0], after[2]))


async def test_a_right_guess_counts(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)

    response = await guess(client, aanya, card_ids(item["profile"])[0], RIGHT[0])

    assert response.json() == {"correct": True, "answer": 0, "picked": 0}
    [item] = (await drop(client, aanya))["items"]
    assert item["profile"]["right_guesses"] == 1


async def test_one_try_per_card(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)
    card = card_ids(item["profile"])[0]
    await guess(client, aanya, card, 1)

    again = await guess(client, aanya, card, 0)

    assert again.status_code == 409
    assert again.json()["code"] == "already_guessed"


async def test_pick_must_be_one_of_three(client: AsyncClient) -> None:
    aanya, _, item = await in_drop(client)

    assert (await guess(client, aanya, card_ids(item["profile"])[0], 3)).status_code == 422


async def test_you_cannot_guess_your_own_cards(client: AsyncClient) -> None:
    _, kabir, item = await in_drop(client)

    response = await guess(client, kabir, card_ids(item["profile"])[0], 0)

    assert response.status_code == 404
    assert response.json()["code"] == "guess_card_not_found"


async def test_strangers_cannot_guess(client: AsyncClient) -> None:
    _, _, item = await in_drop(client)
    meera = await finished(client, "Meera", "woman", "men")  # Kabir isn't in her drop yet

    assert (await guess(client, meera, card_ids(item["profile"])[0], 0)).status_code == 404


async def test_a_missing_card_looks_the_same(client: AsyncClient) -> None:
    aanya, _, _ = await in_drop(client)

    response = await guess(client, aanya, "00000000-0000-0000-0000-000000000000", 0)

    assert response.status_code == 404


async def test_last_nights_drop_no_longer_lets_you_guess(client: AsyncClient, clock: Clock) -> None:
    aanya, _, item = await in_drop(client)
    clock.at += timedelta(days=1)

    assert (await guess(client, aanya, card_ids(item["profile"])[0], 0)).status_code == 404


async def test_someone_whose_like_waits_for_you_can_be_guessed(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=aanya,
    )
    [like] = (await client.get("/v1/likes", headers=kabir)).json()
    her_card = card_ids(like["profile"])[0]

    assert (await guess(client, kabir, her_card, 0)).status_code == 200
    [like] = (await client.get("/v1/likes", headers=kabir)).json()
    assert like["profile"]["right_guesses"] == 1

    # Once he's passed, she's gone from his view.
    await client.post(f"/v1/likes/{like['id']}/pass", headers=kabir)
    assert (await guess(client, kabir, card_ids(like["profile"])[1], 1)).status_code == 404


async def test_a_live_match_can_be_guessed_until_it_ends(client: AsyncClient, clock: Clock) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    clock.at += timedelta(days=1)  # no longer in tonight's drop
    cards = card_ids((await thread(client, kabir, match_id))["profile"])

    assert (await guess(client, kabir, cards[0], 0)).status_code == 200

    await client.post(f"/v1/matches/{match_id}/unmatch", headers=aanya)

    assert (await guess(client, kabir, cards[1], 1)).status_code == 404


async def test_changing_a_card_drops_the_guesses_on_it(client: AsyncClient) -> None:
    from tests.profiles.test_guess_cards import with_card

    aanya, kabir, item = await in_drop(client)
    cards = card_ids(item["profile"])
    await guess(client, aanya, cards[0], RIGHT[0])
    await guess(client, aanya, cards[2], RIGHT[2])

    await client.put(
        "/v1/profile/me/guesses", json=with_card(2, question="My comfort show"), headers=kabir
    )

    [item] = (await drop(client, aanya))["items"]
    after = item["profile"]["guess_cards"]
    assert after[0]["id"] == cards[0] and after[0]["picked"] == 0
    assert after[2]["id"] != cards[2] and after[2]["picked"] is None
    assert item["profile"]["right_guesses"] == 1


async def test_profiles_without_guess_cards_are_unfinished(client: AsyncClient) -> None:
    """Profiles finished before guess cards existed drop out until their owner adds them."""
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM guess_card"))

    mine = (await client.get("/v1/profile/me", headers=kabir)).json()
    assert (mine["guesses_done"], mine["complete"]) == (False, False)
    assert (await client.get("/v1/drops/tonight", headers=aanya)).status_code == 409


# Blurred photo before matching


def face(colour: tuple[int, int, int] = (230, 190, 160)) -> bytes:
    image = Image.new("RGB", (800, 1000), (30, 30, 40))
    draw = ImageDraw.Draw(image)
    draw.ellipse((250, 250, 550, 600), fill=colour)
    draw.ellipse((330, 370, 370, 410), fill=(0, 0, 0))
    draw.ellipse((430, 370, 470, 410), fill=(0, 0, 0))
    out = BytesIO()
    image.save(out, "JPEG")
    return out.getvalue()


async def add_face(client: AsyncClient, headers: Headers) -> None:
    files = {"photo": ("p.jpg", face(), "image/jpeg")}
    assert (await client.put("/v1/profile/me/photo", files=files, headers=headers)).is_success


def contrast(data: bytes) -> float:
    """Higher means more detail survives the blur."""
    return ImageStat.Stat(Image.open(BytesIO(data)).convert("L")).stddev[0]


async def test_blurred_photo_needs_a_photo_from_both(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    url = f"/v1/drops/tonight/{item['id']}/photo"

    assert (await client.get(url, headers=aanya)).json()["code"] == "photo_not_found"
    await add_face(client, kabir)
    assert (await client.get(url, headers=aanya)).status_code == 404
    [item] = (await drop(client, aanya))["items"]
    assert item["profile"]["has_blurred_photo"] is False

    await add_photo(client, aanya)
    response = await client.get(url, headers=aanya)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store, private"
    image = Image.open(BytesIO(response.content))
    assert max(image.size) == 600
    [item] = (await drop(client, aanya))["items"]
    assert item["profile"]["has_blurred_photo"] is True


async def test_each_right_guess_makes_it_a_little_clearer(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    await add_photo(client, aanya)
    await add_face(client, kabir)
    url = f"/v1/drops/tonight/{item['id']}/photo"
    cards = card_ids(item["profile"])
    original = contrast(face())

    seen = [contrast((await client.get(url, headers=aanya)).content)]
    await guess(client, aanya, cards[0], (RIGHT[0] + 1) % 3)  # wrong: no change
    assert contrast((await client.get(url, headers=aanya)).content) == seen[0]
    for n, card in enumerate(cards[1:], start=1):
        await guess(client, aanya, card, RIGHT[n])
        seen.append(contrast((await client.get(url, headers=aanya)).content))

    assert seen == sorted(seen) and len(set(seen)) == 3
    assert seen[-1] < original * 0.75  # still far from the real photo


async def test_blurred_photo_for_a_like_waiting_for_you(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    await add_photo(client, aanya)
    await add_photo(client, kabir)
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=aanya,
    )
    [like] = (await client.get("/v1/likes", headers=kabir)).json()
    url = f"/v1/likes/{like['id']}/photo"

    assert like["profile"]["has_blurred_photo"] is True
    assert (await client.get(url, headers=kabir)).status_code == 200
    assert (await client.get(url, headers=aanya)).status_code == 404  # not a like to her

    await client.post(f"/v1/likes/{like['id']}/pass", headers=kabir)

    assert (await client.get(url, headers=kabir)).status_code == 404


async def test_strangers_never_get_the_blurred_photo(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    meera = await finished(client, "Meera", "woman", "men")
    for headers in (aanya, kabir, meera):
        await add_photo(client, headers)

    response = await client.get(f"/v1/drops/tonight/{item['id']}/photo", headers=meera)

    assert response.status_code == 404


# Photo pieces in a chat


async def test_right_guesses_open_pieces_for_the_guesser_only(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers in (aanya, kabir):
        await add_photo(client, headers)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])

    for card, pick in zip(cards, RIGHT, strict=True):
        await guess(client, aanya, card, pick)

    assert (await thread(client, aanya, match_id))["swaps"]["photo_pieces"] == [0, 6, 8]
    assert (await thread(client, kabir, match_id))["swaps"]["photo_pieces"] == []


async def test_wrong_guesses_open_nothing(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers in (aanya, kabir):
        await add_photo(client, headers)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])

    await guess(client, aanya, cards[0], (RIGHT[0] + 1) % 3)

    assert (await thread(client, aanya, match_id))["swaps"]["photo_pieces"] == []


async def test_swaps_and_guesses_together_stop_at_six_and_the_photo_swap_opens_all(
    client: AsyncClient,
) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers in (aanya, kabir):
        await add_photo(client, headers)
        await add_voice(client, headers)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])
    for card, pick in zip(cards, RIGHT, strict=True):
        await guess(client, aanya, card, pick)

    for card in ["first_name", "branch", "hometown", "voice"]:
        await swap(client, aanya, kabir, match_id, card)

    hers = (await thread(client, aanya, match_id))["swaps"]["photo_pieces"]
    his = (await thread(client, kabir, match_id))["swaps"]["photo_pieces"]
    assert hers == [0, 2, 3, 5, 6, 8]  # 4 swaps + 3 right guesses, capped at 6
    assert his == [0, 2, 6, 8]  # 4 swaps

    await swap(client, aanya, kabir, match_id, "photo")

    assert (await thread(client, aanya, match_id))["swaps"]["photo_pieces"] == list(range(9))
    assert (await thread(client, kabir, match_id))["swaps"]["photo_pieces"] == list(range(9))


async def test_guess_pieces_close_when_the_match_ends(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers in (aanya, kabir):
        await add_photo(client, headers)
    cards = card_ids((await thread(client, aanya, match_id))["profile"])
    await guess(client, aanya, cards[0], RIGHT[0])
    assert (await client.get(f"/v1/chats/{match_id}/photo", headers=aanya)).status_code == 200

    await client.post(f"/v1/matches/{match_id}/unmatch", headers=kabir)

    assert (await client.get(f"/v1/chats/{match_id}/photo", headers=aanya)).status_code == 404


async def test_my_cards_count_who_guessed_and_who_got_it_right(client: AsyncClient) -> None:
    aanya, kabir, item = await in_drop(client)
    meera = await finished(client, "Meera", "woman", "men")
    [meeras_item] = (await drop(client, meera))["items"]
    first = card_ids(item["profile"])[0]
    assert card_ids(meeras_item["profile"])[0] == first

    await guess(client, aanya, first, RIGHT[0])
    await guess(client, meera, first, RIGHT[0] + 1)

    mine = (await client.get("/v1/profile/me", headers=kabir)).json()["guess_cards"]
    assert [(g["guessed_count"], g["right_count"]) for g in mine] == [(2, 1), (0, 0), (0, 0)]
