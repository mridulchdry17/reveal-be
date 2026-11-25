import pytest
from httpx import AsyncClient

from tests.drops.helpers import drop, finished, matched_pair
from tests.swaps.test_swaps import add_photo, ask, swap


async def send(client: AsyncClient, headers: dict[str, str], match_id: str, body: str):
    return await client.post(f"/v1/chats/{match_id}/messages", json={"body": body}, headers=headers)


async def chats(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.get("/v1/chats", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_match_shows_up_in_both_chat_lists(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)

    [hers] = await chats(client, aanya)
    [his] = await chats(client, kabir)

    assert hers["match_id"] == his["match_id"] == match_id
    assert hers["profile"]["nickname"] == "Kabir nick"
    assert his["profile"]["nickname"] == "Aanya nick"
    assert hers["last_message"] is None
    assert hers["unread"] is False


async def test_chat_shows_only_what_they_chose_to_show(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)

    profile = (await client.get(f"/v1/chats/{match_id}", headers=aanya)).json()["profile"]

    assert profile["first_name"] is None
    assert "contact" in profile["hidden_cards"]


@pytest.mark.parametrize("first", ["aanya", "kabir"])
async def test_either_person_can_write_first(client: AsyncClient, first: str) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    headers = aanya if first == "aanya" else kabir

    response = await send(client, headers, match_id, "hi!")

    assert response.status_code == 201
    assert response.json()["mine"] is True


async def test_messages_arrive_in_order_for_both(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)

    await send(client, aanya, match_id, "ok wait you're also into films??")
    await send(client, kabir, match_id, "yes. last thing you watched?")
    await send(client, aanya, match_id, "  Laapataa   Ladies  ")

    thread = (await client.get(f"/v1/chats/{match_id}", headers=kabir)).json()
    assert [(m["body"], m["mine"]) for m in thread["messages"]] == [
        ("ok wait you're also into films??", False),
        ("yes. last thing you watched?", True),
        ("Laapataa Ladies", False),
    ]


async def test_unread_until_they_open_the_chat(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await send(client, aanya, match_id, "hey")

    [his] = await chats(client, kabir)
    [hers] = await chats(client, aanya)
    assert his["unread"] is True
    assert his["last_message"]["body"] == "hey"
    assert hers["unread"] is False  # her own message

    assert (await client.post(f"/v1/chats/{match_id}/read", headers=kabir)).status_code == 204
    [his] = await chats(client, kabir)
    assert his["unread"] is False


async def test_latest_chat_comes_first(client: AsyncClient) -> None:
    aanya, _, first = await matched_pair(client)
    dev = await finished(client, "Dev", "man", "women")
    # Dev likes Aanya; she likes him back.
    item = (await drop(client, dev))["items"][0]
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=dev,
    )
    like_id = (await client.get("/v1/likes", headers=aanya)).json()[0]["id"]
    await client.post(f"/v1/likes/{like_id}/match", headers=aanya)

    await send(client, aanya, first, "back to you")

    order = [c["match_id"] for c in await chats(client, aanya)]
    assert len(order) == 2
    assert order[0] == first


@pytest.mark.parametrize(
    "body", ["", "   ", "my number is 98765 43210", "add me on insta", "x" * 1001]
)
async def test_messages_follow_the_rules(client: AsyncClient, body: str) -> None:
    aanya, _, match_id = await matched_pair(client)

    assert (await send(client, aanya, match_id, body)).status_code == 422


async def test_outsiders_cannot_read_or_write_a_chat(client: AsyncClient) -> None:
    _, _, match_id = await matched_pair(client)
    meera = await finished(client, "Meera", "woman", "men")

    assert (await client.get(f"/v1/chats/{match_id}", headers=meera)).status_code == 404
    assert (await send(client, meera, match_id, "hi")).status_code == 404


async def test_unmatch_closes_the_chat_for_both(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await send(client, aanya, match_id, "hi")

    response = await client.post(f"/v1/matches/{match_id}/unmatch", headers=kabir)

    assert response.status_code == 204
    assert await chats(client, aanya) == []
    assert await chats(client, kabir) == []
    assert (await client.get(f"/v1/chats/{match_id}", headers=aanya)).status_code == 404
    assert (await send(client, aanya, match_id, "hello?")).status_code == 404
    again = await client.post(f"/v1/matches/{match_id}/unmatch", headers=aanya)
    assert again.status_code == 404


async def test_the_chat_list_shows_photo_pieces_and_the_waiting_swap(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await add_photo(client, aanya)
    await add_photo(client, kabir)
    [row] = (await client.get("/v1/chats", headers=aanya)).json()
    assert (row["photo_pieces"], row["pending_swap"]) == (0, None)

    await swap(client, aanya, kabir, match_id, "branch")
    await ask(client, kabir, match_id, "hometown")
    await ask(client, aanya, match_id, "first_name")

    [hers] = (await client.get("/v1/chats", headers=aanya)).json()
    [his] = (await client.get("/v1/chats", headers=kabir)).json()
    assert hers["photo_pieces"] == his["photo_pieces"] == 1
    assert hers["pending_swap"] == {"card": "first_name", "by": "me"}
    assert his["pending_swap"] == {"card": "first_name", "by": "them"}
