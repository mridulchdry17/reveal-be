"""Make students with finished profiles and set the clock, for drop and like tests."""

from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient

from tests.profiles.test_profile import BASICS, CARDS, PROMPTS, student

# 10 PM in college time (IST = UTC+5:30): tonight's drop is open.
TONIGHT = datetime(2026, 11, 22, 16, 30, tzinfo=UTC)


async def finished(
    client: AsyncClient,
    name: str,
    gender: str = "woman",
    interested_in: str = "men",
    **cards: Any,
) -> dict[str, str]:
    """A verified student with all four profile screens saved. Returns auth headers."""
    sub = name.lower()
    headers = await student(client, f"sub-{sub}|{sub}@adgips.ac.in|{name} Test|yes|adgips.ac.in")
    preferences = {"gender": gender, "interested_in": interested_in, "match_on": []}
    for path, body in [
        ("basics", {**BASICS, "nickname": f"{name} nick"}),
        ("prompts", PROMPTS),
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
