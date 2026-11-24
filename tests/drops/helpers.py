"""Make students with finished profiles and set the clock, for drop and like tests."""

from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient

from tests.profiles.test_profile import BASICS, CARDS, GUESSES, PROMPTS, student

# 10 PM in college time (IST = UTC+5:30): tonight's drop is open.
TONIGHT = datetime(2026, 11, 22, 16, 30, tzinfo=UTC)


async def finished(
    client: AsyncClient,
    name: str,
    gender: str = "woman",
    interested_in: str = "men",
    **cards: Any,
) -> dict[str, str]:
    """A verified student with every profile screen saved. Returns auth headers."""
    sub = name.lower()
    headers = await student(client, f"sub-{sub}|{sub}@adgips.ac.in|{name} Test|yes|adgips.ac.in")
    preferences = {"gender": gender, "interested_in": interested_in, "match_on": []}
    for path, body in [
        ("basics", {**BASICS, "nickname": f"{name} nick"}),
        ("prompts", PROMPTS),
        ("guesses", GUESSES),
        ("cards", {**CARDS, **cards}),
        ("preferences", preferences),
    ]:
        response = await client.put(f"/v1/profile/me/{path}", json=body, headers=headers)
        assert response.status_code == 200, response.text
    return headers


async def drop(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get("/v1/drops/tonight", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def nicknames(body: dict[str, Any]) -> set[str]:
    return {item["profile"]["nickname"] for item in body["items"]}


class Clock:
    """Stands in for src.clock.now. Tests move it with `clock.at = ...`."""

    def __init__(self) -> None:
        self.at = TONIGHT

    def __call__(self) -> datetime:
        return self.at


async def matched_pair(client: AsyncClient) -> tuple[dict[str, str], dict[str, str], str]:
    """Aanya and Kabir, matched: she liked his prompt, he liked her back. Returns match id."""
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    item = (await drop(client, aanya))["items"][0]
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=aanya,
    )
    like_id = (await client.get("/v1/likes", headers=kabir)).json()[0]["id"]
    await client.post(f"/v1/likes/{like_id}/match", headers=kabir)
    chats = (await client.get("/v1/chats", headers=aanya)).json()
    return aanya, kabir, chats[0]["match_id"]
