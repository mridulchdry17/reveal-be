from io import BytesIO
from typing import Any

from httpx import AsyncClient
from PIL import Image

from tests.drops.helpers import finished, matched_pair
from tests.profiles.test_photo import jpeg

Headers = dict[str, str]


async def thread(client: AsyncClient, headers: Headers, match_id: str) -> dict[str, Any]:
    response = await client.get(f"/v1/chats/{match_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def states(body: dict[str, Any]) -> dict[str, str]:
    board = body.get("swaps", body)
    return {c["card"]: c["state"] for c in board["cards"]}


async def ask(client: AsyncClient, headers: Headers, match_id: str, card: str):
    return await client.post(f"/v1/chats/{match_id}/swaps", json={"card": card}, headers=headers)


async def answer(client: AsyncClient, headers: Headers, match_id: str, card: str, yes: bool):
    action = "accept" if yes else "decline"
    return await client.post(f"/v1/chats/{match_id}/swaps/{card}/{action}", headers=headers)


async def swap(client: AsyncClient, a: Headers, b: Headers, match_id: str, card: str) -> None:
    assert (await ask(client, a, match_id, card)).status_code == 200
    assert (await answer(client, b, match_id, card, yes=True)).status_code == 200


async def add_photo(client: AsyncClient, headers: Headers) -> None:
    files = {"photo": ("p.jpg", jpeg(300, 300), "image/jpeg")}
    assert (await client.put("/v1/profile/me/photo", files=files, headers=headers)).is_success


async def add_voice(client: AsyncClient, headers: Headers, seconds: int = 9) -> None:
    files = {"voice": ("v.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 100, "audio/webm")}
    data = {"seconds": str(seconds)}
    response = await client.put("/v1/profile/me/voice", files=files, data=data, headers=headers)
    assert response.is_success


async def add_contact(client: AsyncClient, headers: Headers, handle: str) -> None:
    body = {"kind": "instagram", "value": handle}
    assert (await client.put("/v1/profile/me/contact", json=body, headers=headers)).is_success


async def test_a_card_opens_only_when_both_say_yes(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)

    asked = await ask(client, aanya, match_id, "first_name")
    before = await thread(client, kabir, match_id)

    assert states(asked.json())["first_name"] == "you_asked"
    assert states(before)["first_name"] == "they_asked"
    assert before["profile"]["first_name"] is None
    assert (await thread(client, aanya, match_id))["profile"]["first_name"] is None

    await answer(client, kabir, match_id, "first_name", yes=True)

    hers = await thread(client, aanya, match_id)
    his = await thread(client, kabir, match_id)
    assert hers["profile"]["first_name"] == "Kabir"
    assert his["profile"]["first_name"] == "Aanya"
    assert states(hers)["first_name"] == states(his)["first_name"] == "open"
    assert "first_name" in hers["profile"]["shown_cards"]
    assert "first_name" not in hers["profile"]["hidden_cards"]


async def test_not_yet_opens_nothing_and_they_can_ask_again(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "hometown")

    declined = await answer(client, kabir, match_id, "hometown", yes=False)

    assert states(declined.json())["hometown"] == "can_ask"
    assert (await thread(client, aanya, match_id))["profile"]["hometown"] is None
    assert (await ask(client, aanya, match_id, "hometown")).status_code == 200


async def test_asking_for_a_card_they_already_asked_for_says_yes(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "branch")

    both = await ask(client, kabir, match_id, "branch")

    assert states(both.json())["branch"] == "open"
    assert (await thread(client, aanya, match_id))["profile"]["branch"] == "CSE"


async def test_you_cannot_answer_your_own_request_or_ask_twice(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "branch")

    assert (await answer(client, aanya, match_id, "branch", yes=True)).status_code == 404
    assert (await ask(client, aanya, match_id, "branch")).status_code == 409


async def test_voice_is_offered_only_when_both_have_a_voice_note(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_voice(client, aanya)

    assert "voice" not in states(await thread(client, aanya, match_id))
    assert (await ask(client, aanya, match_id, "voice")).status_code == 409

    await add_voice(client, kabir, seconds=14)
    await swap(client, aanya, kabir, match_id, "voice")

    assert (await thread(client, aanya, match_id))["profile"]["voice_seconds"] == 14


async def test_photo_needs_a_card_swap_and_a_photo_from_both(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_photo(client, aanya)

    assert states(await thread(client, aanya, match_id))["photo"] == "needs_theirs"
    assert states(await thread(client, kabir, match_id))["photo"] == "needs_yours"

    await add_photo(client, kabir)
    assert states(await thread(client, aanya, match_id))["photo"] == "locked"
    assert (await ask(client, aanya, match_id, "photo")).status_code == 409

    await swap(client, aanya, kabir, match_id, "first_name")
    assert states(await thread(client, aanya, match_id))["photo"] == "can_ask"


async def test_each_card_swap_opens_one_piece_and_the_photo_swap_opens_all(
    client: AsyncClient,
) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_photo(client, aanya)
    await add_photo(client, kabir)
    assert (await thread(client, aanya, match_id))["swaps"]["photo_pieces"] == []

    for card in ["first_name", "branch", "hometown"]:
        await swap(client, aanya, kabir, match_id, card)
    hers = await thread(client, aanya, match_id)
    his = await thread(client, kabir, match_id)

    assert hers["swaps"]["photo_pieces"] == his["swaps"]["photo_pieces"] == [0, 6, 8]
    assert "photo" in hers["profile"]["hidden_cards"]

    await swap(client, kabir, aanya, match_id, "photo")

    hers = await thread(client, aanya, match_id)
    assert hers["swaps"]["photo_pieces"] == list(range(9))
    assert "photo" in hers["profile"]["shown_cards"]


async def test_no_pieces_open_unless_both_have_a_photo(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_photo(client, kabir)

    await swap(client, aanya, kabir, match_id, "first_name")

    assert (await thread(client, aanya, match_id))["swaps"]["photo_pieces"] == []


async def test_contact_opens_only_after_the_photo_swap(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers, handle in [(aanya, "aanya.reads"), (kabir, "kabir.k")]:
        await add_photo(client, headers)
        await add_contact(client, headers, handle)

    assert states(await thread(client, aanya, match_id))["contact"] == "locked"
    await swap(client, aanya, kabir, match_id, "hometown")
    assert (await ask(client, aanya, match_id, "contact")).status_code == 409
    await swap(client, aanya, kabir, match_id, "photo")
    await swap(client, aanya, kabir, match_id, "contact")

    hers = await thread(client, aanya, match_id)
    his = await thread(client, kabir, match_id)
    assert hers["profile"]["contact"] == {"kind": "instagram", "value": "kabir.k"}
    assert his["profile"]["contact"] == {"kind": "instagram", "value": "aanya.reads"}


async def test_unmatch_closes_everything_for_both(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await swap(client, aanya, kabir, match_id, "first_name")
    await ask(client, kabir, match_id, "branch")

    await client.post(f"/v1/matches/{match_id}/unmatch", headers=kabir)

    assert (await client.get(f"/v1/chats/{match_id}", headers=aanya)).status_code == 404
    assert (await answer(client, aanya, match_id, "branch", yes=True)).status_code == 404
    assert (await ask(client, aanya, match_id, "hometown")).status_code == 404
    assert await (await client.get("/v1/chats", headers=aanya)).aread() == b"[]"


async def test_chat_list_shows_swapped_cards(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await swap(client, aanya, kabir, match_id, "first_name")

    [row] = (await client.get("/v1/chats", headers=aanya)).json()

    assert row["profile"]["first_name"] == "Kabir"


async def test_someone_outside_the_match_cannot_swap(client: AsyncClient) -> None:
    _, _, match_id = await matched_pair(client)
    meera = await finished(client, "Meera", "woman", "men")

    assert (await ask(client, meera, match_id, "first_name")).status_code == 404


def pixel(data: bytes, x: float, y: float) -> tuple[int, int, int]:
    """Colour at a fraction of the image's width and height."""
    image = Image.open(BytesIO(data)).convert("RGB")
    return image.getpixel((int(image.width * x), int(image.height * y)))  # type: ignore[return-value]


async def test_their_photo_shows_only_open_pieces(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_photo(client, aanya)
    files = {"photo": ("p.jpg", jpeg(900, 900, colour=(20, 120, 220)), "image/jpeg")}
    await client.put("/v1/profile/me/photo", files=files, headers=kabir)
    url = f"/v1/chats/{match_id}/photo"

    assert (await client.get(url, headers=aanya)).status_code == 404

    await swap(client, aanya, kabir, match_id, "first_name")  # opens piece 6: bottom left
    response = await client.get(url, headers=aanya)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    blue = pixel(response.content, 1 / 6 - 0.05, 5 / 6 + 0.05)
    centre = pixel(response.content, 0.5, 0.5)
    assert blue[2] > 180 and blue[0] < 80  # open piece: the photo
    assert abs(centre[0] - 234) < 12 and abs(centre[2] - 211) < 12  # closed: painted over
    assert max(Image.open(BytesIO(response.content)).size) <= 900


async def test_their_voice_plays_only_after_the_voice_swap(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_voice(client, aanya)
    await add_voice(client, kabir)
    url = f"/v1/chats/{match_id}/voice"

    assert (await client.get(url, headers=aanya)).status_code == 404
    await swap(client, aanya, kabir, match_id, "voice")
    response = await client.get(url, headers=aanya)

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/webm"


async def test_photo_and_voice_close_when_the_match_ends(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    for headers in (aanya, kabir):
        await add_photo(client, headers)
        await add_voice(client, headers)
    await swap(client, aanya, kabir, match_id, "voice")
    await swap(client, aanya, kabir, match_id, "photo")

    await client.post(f"/v1/matches/{match_id}/block", headers=kabir)

    assert (await client.get(f"/v1/chats/{match_id}/photo", headers=aanya)).status_code == 404
    assert (await client.get(f"/v1/chats/{match_id}/voice", headers=aanya)).status_code == 404


async def withdraw(client: AsyncClient, headers: Headers, match_id: str, card: str):
    return await client.delete(f"/v1/chats/{match_id}/swaps/{card}", headers=headers)


async def test_i_can_take_back_my_request_before_they_answer(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "hometown")

    response = await withdraw(client, aanya, match_id, "hometown")

    assert response.status_code == 200
    assert states(response.json())["hometown"] == "can_ask"
    assert states(await thread(client, kabir, match_id))["hometown"] == "can_ask"
    assert (await answer(client, kabir, match_id, "hometown", yes=True)).status_code == 404
    assert (await ask(client, aanya, match_id, "hometown")).status_code == 200


async def test_only_the_asker_takes_back_and_only_while_pending(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "branch")

    theirs = await withdraw(client, kabir, match_id, "branch")
    assert theirs.status_code == 409
    assert theirs.json()["code"] == "swap_not_yours"
    assert (await withdraw(client, aanya, match_id, "hometown")).status_code == 404

    await answer(client, kabir, match_id, "branch", yes=True)
    opened = await withdraw(client, aanya, match_id, "branch")
    assert opened.status_code == 404
    assert (await thread(client, aanya, match_id))["profile"]["branch"] == "CSE"


async def test_no_take_back_in_someone_elses_match(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)
    await ask(client, aanya, match_id, "branch")
    meera = await finished(client, "Meera", "woman", "men")

    assert (await withdraw(client, meera, match_id, "branch")).status_code == 404
