from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from src.database import engine
from src.safety.models import Block
from tests.drops.helpers import Clock, matched_pair
from tests.profiles.test_profile import student

ADMIN = "sub-admin|admin@gmail.com|Admin|yes"


async def block_count() -> int:
    async with engine.connect() as conn:
        return (await conn.execute(select(func.count()).select_from(Block))).scalar_one()


async def test_block_ends_the_chat_for_both(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)

    response = await client.post(f"/v1/matches/{match_id}/block", headers=aanya)

    assert response.status_code == 204
    assert (await client.get("/v1/chats", headers=aanya)).json() == []
    assert (await client.get("/v1/chats", headers=kabir)).json() == []
    assert await block_count() == 1


async def test_blocked_people_never_reappear_in_drops(client: AsyncClient, clock: Clock) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await client.post(f"/v1/matches/{match_id}/block", headers=kabir)
    clock.at += timedelta(days=60)
    assert (await client.get("/v1/drops/tonight", headers=aanya)).json()["items"] == []
    assert (await client.get("/v1/drops/tonight", headers=kabir)).json()["items"] == []


async def test_report_blocks_and_reaches_admins(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)

    response = await client.post(
        f"/v1/matches/{match_id}/report",
        json={"reason": "harassment", "details": "  kept   asking for my number "},
        headers=aanya,
    )

    assert response.status_code == 204
    assert (await client.get("/v1/chats", headers=kabir)).json() == []
    assert await block_count() == 1
    admin = await student(client, ADMIN)
    [report] = (await client.get("/v1/admin/reports", headers=admin)).json()
    assert report["reason"] == "harassment"
    assert report["details"] == "kept asking for my number"
    assert report["reporter_email"] == "aanya@adgips.ac.in"
    assert report["reported_email"] == "kabir@adgips.ac.in"


async def test_reports_are_for_admins_only(client: AsyncClient) -> None:
    aanya, _, _ = await matched_pair(client)

    assert (await client.get("/v1/admin/reports", headers=aanya)).status_code == 403


@pytest.mark.parametrize("action", ["block", "report"])
async def test_cannot_act_on_someone_elses_match(client: AsyncClient, action: str) -> None:
    _, _, match_id = await matched_pair(client)
    outsider = await student(client, "sub-x|x@adgips.ac.in|X Y|yes|adgips.ac.in")

    response = await client.post(
        f"/v1/matches/{match_id}/{action}", json={"reason": "spam"}, headers=outsider
    )

    assert response.status_code == 404


async def test_report_needs_a_known_reason(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)

    response = await client.post(
        f"/v1/matches/{match_id}/report", json={"reason": "vibes"}, headers=aanya
    )

    assert response.status_code == 422


async def test_my_block_list_shows_who_i_blocked(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    assert (await client.get("/v1/blocks", headers=aanya)).json() == []

    await client.post(f"/v1/matches/{match_id}/block", headers=aanya)

    [blocked] = (await client.get("/v1/blocks", headers=aanya)).json()
    assert blocked["nickname"] == "Kabir nick"
    assert set(blocked) == {"id", "nickname", "blocked_at"}
    assert (await client.get("/v1/blocks", headers=kabir)).json() == []  # silent


async def test_reporting_also_lists_them_as_blocked(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)

    await client.post(f"/v1/matches/{match_id}/report", json={"reason": "spam"}, headers=aanya)

    assert [b["nickname"] for b in (await client.get("/v1/blocks", headers=aanya)).json()] == [
        "Kabir nick"
    ]
