from typing import Any

from httpx import AsyncClient

from tests.drops.helpers import drop, finished
from tests.hides.test_hides import hide
from tests.matches.test_likes import first_item, like, likes
from tests.swaps.test_swaps import add_photo

Headers = dict[str, str]


async def sent(client: AsyncClient, headers: Headers) -> list[dict[str, Any]]:
    response = await client.get("/v1/likes/sent", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def liked_kabir(client: AsyncClient) -> tuple[Headers, Headers, dict[str, Any]]:
    """Aanya liked Kabir's second prompt with a comment. Returns her sent like."""
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await like(client, aanya, await first_item(client, aanya), "Maggi at 2am?")
    [mine] = await sent(client, aanya)
    return aanya, kabir, mine


async def test_my_waiting_likes_are_listed(client: AsyncClient) -> None:
    _, kabir, mine = await liked_kabir(client)

    assert mine["nickname"] == "Kabir nick"
    assert mine["liked"] == {
        "kind": "prompt",
        "question": "Hot take",
        "answer": "Maggi is a full meal",
        "guess_kind": None,
    }
    assert mine["comment"] == "Maggi at 2am?"
    assert mine["has_blurred_photo"] is False
    assert mine["id"] == (await likes(client, kabir))[0]["id"]
    assert await sent(client, kabir) == []


async def test_a_pass_still_looks_like_waiting_to_the_liker(client: AsyncClient) -> None:
    aanya, kabir, mine = await liked_kabir(client)

    await client.post(f"/v1/likes/{mine['id']}/pass", headers=kabir)

    assert [s["id"] for s in await sent(client, aanya)] == [mine["id"]]


async def test_a_match_leaves_the_sent_list(client: AsyncClient) -> None:
    aanya, kabir, mine = await liked_kabir(client)

    await client.post(f"/v1/likes/{mine['id']}/match", headers=kabir)

    assert await sent(client, aanya) == []


async def test_taking_a_like_back_hides_it_from_them(client: AsyncClient) -> None:
    aanya, kabir, mine = await liked_kabir(client)

    response = await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)

    assert response.status_code == 204
    assert await sent(client, aanya) == []
    assert await likes(client, kabir) == []
    answer = await client.post(f"/v1/likes/{mine['id']}/match", headers=kabir)
    assert answer.status_code == 409
    again = await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)
    assert again.status_code == 404


async def test_a_withdrawn_like_never_turns_into_a_match(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    kabirs_item = await first_item(client, kabir)
    await like(client, aanya, await first_item(client, aanya))
    [mine] = await sent(client, aanya)
    await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)

    result = await like(client, kabir, kabirs_item)

    assert result.json() == {"matched": False, "match_id": None}
    assert len(await likes(client, aanya)) == 1


async def test_only_my_waiting_likes_can_be_taken_back(client: AsyncClient) -> None:
    aanya, kabir, mine = await liked_kabir(client)
    meera = await finished(client, "Meera", "woman", "men")

    for headers in (kabir, meera):
        response = await client.delete(f"/v1/likes/sent/{mine['id']}", headers=headers)
        assert response.status_code == 404
    await client.post(f"/v1/likes/{mine['id']}/match", headers=kabir)
    response = await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)
    assert response.status_code == 404


async def test_hidden_people_leave_the_sent_list(client: AsyncClient) -> None:
    aanya, _, mine = await liked_kabir(client)

    await hide(client, aanya, "email", "kabir@adgips.ac.in")

    assert await sent(client, aanya) == []
    response = await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)
    assert response.status_code == 404
    photo = await client.get(f"/v1/likes/sent/{mine['id']}/photo", headers=aanya)
    assert photo.status_code == 404


async def test_their_blurred_photo_only_when_we_both_have_one(client: AsyncClient) -> None:
    aanya, kabir, mine = await liked_kabir(client)
    path = f"/v1/likes/sent/{mine['id']}/photo"
    await add_photo(client, kabir)

    assert (await client.get(path, headers=aanya)).status_code == 404

    await add_photo(client, aanya)
    response = await client.get(path, headers=aanya)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "no-store" in response.headers["cache-control"]
    assert (await sent(client, aanya))[0]["has_blurred_photo"] is True
    assert (await client.get(path, headers=kabir)).status_code == 404


async def test_drop_stays_marked_liked_after_taking_back(client: AsyncClient) -> None:
    aanya, _, mine = await liked_kabir(client)

    await client.delete(f"/v1/likes/sent/{mine['id']}", headers=aanya)

    [item] = (await drop(client, aanya))["items"]
    assert item["decision"] == "liked"
