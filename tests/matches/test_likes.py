from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from src.database import engine
from src.matches.models import Match
from tests.drops.helpers import drop, finished


async def first_item(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    return (await drop(client, headers))["items"][0]


async def like(
    client: AsyncClient, headers: dict[str, str], item: dict[str, Any], comment: str | None = None
):
    prompt_id = item["profile"]["prompts"][1]["id"]
    return await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": prompt_id, "comment": comment},
        headers=headers,
    )


async def likes(client: AsyncClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = await client.get("/v1/likes", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def match_count() -> int:
    async with engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(Match))).scalar_one()


async def test_a_like_reaches_them_with_the_prompt_and_comment(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")

    response = await like(client, aanya, await first_item(client, aanya), "Maggi at 2am?")

    assert response.status_code == 200
    assert response.json() == {"matched": False}
    [received] = await likes(client, kabir)
    assert received["prompt_question"] == "Hot take"
    assert received["prompt_answer"] == "Maggi is a full meal"
    assert received["comment"] == "Maggi at 2am?"
    assert received["profile"]["nickname"] == "Aanya nick"
    assert received["profile"]["first_name"] is None  # names open only by swap


async def test_liked_item_is_marked_and_cannot_be_answered_twice(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    item = await first_item(client, aanya)

    await like(client, aanya, item)

    assert (await first_item(client, aanya))["decision"] == "liked"
    again = await like(client, aanya, item)
    assert again.status_code == 409


async def test_someone_who_liked_you_is_in_likes_not_your_drop(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await like(client, aanya, await first_item(client, aanya))  # before Kabir opens his drop

    assert (await drop(client, kabir))["items"] == []
    assert len(await likes(client, kabir)) == 1


async def test_liking_back_is_a_match(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await like(client, aanya, await first_item(client, aanya))
    [received] = await likes(client, kabir)

    response = await client.post(f"/v1/likes/{received['id']}/match", headers=kabir)

    assert response.status_code == 204
    assert await likes(client, kabir) == []
    assert await match_count() == 1


async def test_liking_each_other_from_both_drops_is_a_match(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    aanyas_item = await first_item(client, aanya)
    kabirs_item = await first_item(client, kabir)

    assert (await like(client, aanya, aanyas_item)).json() == {"matched": False}
    assert (await like(client, kabir, kabirs_item)).json() == {"matched": True}
    assert await likes(client, aanya) == []
    assert await likes(client, kabir) == []
    assert await match_count() == 1


async def test_passing_on_a_like_is_silent_and_final(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    kabirs_item = await first_item(client, kabir)
    await like(client, aanya, await first_item(client, aanya))
    [received] = await likes(client, kabir)

    response = await client.post(f"/v1/likes/{received['id']}/pass", headers=kabir)

    assert response.status_code == 204
    assert await likes(client, kabir) == []
    # Even if he later likes her from his drop, it's not a match and she isn't told.
    assert (await like(client, kabir, kabirs_item)).json() == {"matched": False}
    assert await likes(client, aanya) == []
    assert await match_count() == 0


async def test_an_answered_like_cannot_be_answered_again(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await like(client, aanya, await first_item(client, aanya))
    [received] = await likes(client, kabir)
    await client.post(f"/v1/likes/{received['id']}/pass", headers=kabir)

    response = await client.post(f"/v1/likes/{received['id']}/match", headers=kabir)

    assert response.status_code == 409


async def test_someone_elses_like_looks_missing(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    meera = await finished(client, "Meera", "woman", "men")
    await like(client, aanya, await first_item(client, aanya))
    [received] = await likes(client, kabir)

    for headers in (aanya, meera):
        response = await client.post(f"/v1/likes/{received['id']}/match", headers=headers)
        assert response.status_code == 404


@pytest.mark.parametrize("comment", ["call me 98765 43210", "insta me", "@quietstorm", "x" * 141])
async def test_comments_follow_the_rules(client: AsyncClient, comment: str) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")

    response = await like(client, aanya, await first_item(client, aanya), comment)

    assert response.status_code == 422


async def test_blank_comment_is_no_comment(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")

    await like(client, aanya, await first_item(client, aanya), "   ")

    assert (await likes(client, kabir))[0]["comment"] is None


async def test_you_can_only_like_their_own_prompt(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    meera = await finished(client, "Meera", "woman", "men")
    item = await first_item(client, aanya)
    meeras_prompt = (await client.get("/v1/profile/me", headers=meera)).json()["prompts"][0]

    response = await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": meeras_prompt["id"]},
        headers=aanya,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "prompt_not_found"
