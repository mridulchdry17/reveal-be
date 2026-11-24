from typing import Any

import pytest
from httpx import AsyncClient

from src.hides import service as hide_service
from tests.drops.helpers import drop, finished, matched_pair, nicknames

Headers = dict[str, str]


async def hide(client: AsyncClient, headers: Headers, kind: str, value: str):
    return await client.post("/v1/hides", json={"kind": kind, "value": value}, headers=headers)


async def likes(client: AsyncClient, headers: Headers) -> list[dict[str, Any]]:
    response = await client.get("/v1/likes", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_hiding_by_email_works_both_ways(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    assert (await hide(client, aanya, "email", " Kabir@ADGIPS.ac.in ")).status_code == 200

    assert nicknames(await drop(client, aanya)) == set()
    assert nicknames(await drop(client, kabir)) == set()


async def test_hiding_by_phone_or_instagram_matches_card_seven(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    dev = await finished(client, "Dev", "man", "women")
    for headers, contact in [
        (kabir, {"kind": "phone", "value": "9876543210"}),
        (dev, {"kind": "instagram", "value": "dev.codes"}),
    ]:
        response = await client.put("/v1/profile/me/contact", json=contact, headers=headers)
        assert response.status_code == 200, response.text

    await hide(client, aanya, "phone", "+91 98765 43210")
    await hide(client, aanya, "instagram", "@Dev.Codes")

    assert nicknames(await drop(client, aanya)) == set()


async def test_someone_hidden_after_the_drop_was_built_leaves_it(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    [item] = (await drop(client, aanya))["items"]

    await hide(client, aanya, "email", "kabir@adgips.ac.in")

    assert (await drop(client, aanya))["items"] == []
    like = await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=aanya,
    )
    assert like.status_code == 404
    card = item["profile"]["guess_cards"][0]["id"]
    guess = await client.post(f"/v1/guesses/{card}", json={"pick": 0}, headers=aanya)
    assert guess.status_code == 404


async def test_a_waiting_like_disappears_once_either_side_hides(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    [item] = (await drop(client, aanya))["items"]
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=aanya,
    )
    [like] = await likes(client, kabir)

    # She hid him: he must not see her like, even though only she has him on a list.
    await hide(client, aanya, "email", "kabir@adgips.ac.in")

    assert await likes(client, kabir) == []
    assert (await client.post(f"/v1/likes/{like['id']}/match", headers=kabir)).status_code == 404
    assert (await client.get(f"/v1/likes/{like['id']}/photo", headers=kabir)).status_code == 404


async def test_live_matches_carry_on(client: AsyncClient) -> None:
    aanya, _kabir, match_id = await matched_pair(client)
    await hide(client, aanya, "email", "kabir@adgips.ac.in")
    thread = await client.get(f"/v1/chats/{match_id}", headers=aanya)
    assert thread.status_code == 200


async def test_list_shows_only_masked_hints(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await hide(client, aanya, "phone", "9876543210")
    await hide(client, aanya, "email", "someone.else@gmail.com")
    response = await hide(client, aanya, "phone", "098765 43210")  # same person again

    body = response.json()
    assert [i["hint"] for i in body["items"]] == ["so•••@gmail.com", "98••••••10"]
    assert "9876543210" not in response.text


async def test_hiding_someone_not_on_reveal_looks_the_same(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    response = await hide(client, aanya, "email", "nobody@adgips.ac.in")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


async def test_unhide_brings_them_back(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    entry = (await hide(client, aanya, "email", "kabir@adgips.ac.in")).json()["items"][0]

    response = await client.delete(f"/v1/hides/{entry['id']}", headers=aanya)
    assert response.json()["items"] == []
    assert nicknames(await drop(client, aanya)) == {"Kabir nick"}


async def test_someone_elses_entry_looks_missing(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    entry = (await hide(client, aanya, "email", "x@gmail.com")).json()["items"][0]
    assert (await client.delete(f"/v1/hides/{entry['id']}", headers=kabir)).status_code == 404


@pytest.mark.parametrize(
    ("kind", "value"),
    [("email", "not-an-email"), ("phone", "12345"), ("instagram", "has space")],
)
async def test_bad_values_are_rejected(client: AsyncClient, kind: str, value: str) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    response = await hide(client, aanya, kind, value)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "value"]


async def test_list_has_a_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hide_service, "HIDE_LIST_MAX", 1)
    aanya = await finished(client, "Aanya", "woman", "men")
    await hide(client, aanya, "email", "a@gmail.com")
    response = await hide(client, aanya, "email", "b@gmail.com")
    assert response.status_code == 409
    assert response.json()["code"] == "hide_list_full"
