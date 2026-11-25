import json
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import text

from src.config import settings
from src.database import SessionLocal, engine
from src.drops import service as drop_service
from src.notifications import service
from src.notifications.webpush import Device
from tests.drops.helpers import drop, finished, matched_pair
from tests.swaps.test_swaps import answer, ask

Headers = dict[str, str]


class FakeSender:
    """Stands in for the push service. `codes` answers per endpoint (default 201)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.codes: dict[str, int] = {}

    async def __call__(self, device: Device, payload: str, ttl: int) -> int:
        self.sent.append((device.endpoint, json.loads(payload)))
        return self.codes.get(device.endpoint, 201)


def endpoint(name: str) -> str:
    return f"https://push.example.com/{name}"


async def subscribe(client: AsyncClient, headers: Headers, name: str):
    body = {"endpoint": endpoint(name), "keys": {"p256dh": "p" * 20, "auth": "a" * 16}}
    response = await client.put("/v1/notifications/subscription", json=body, headers=headers)
    assert response.status_code == 204, response.text
    return response


async def deliver() -> FakeSender:
    send = FakeSender()
    async with SessionLocal() as session:
        while await service.deliver(session, send):
            pass
    return send


async def waiting() -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM push_outbox"))).scalar_one()


async def like_first(client: AsyncClient, liker: Headers) -> None:
    [item] = (await drop(client, liker))["items"]
    response = await client.post(
        f"/v1/drops/tonight/{item['id']}/like",
        json={"prompt_id": item["profile"]["prompts"][0]["id"]},
        headers=liker,
    )
    assert response.status_code == 200, response.text


async def test_a_like_sends_generic_copy(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "kabir-phone")

    await like_first(client, aanya)
    send = await deliver()

    [(to, payload)] = send.sent
    assert to == endpoint("kabir-phone")
    assert payload == {
        "title": "Cards",
        "body": "Someone liked one of your answers.",
        "url": "/app/likes",
        "tag": "like",
    }
    assert "Aanya" not in json.dumps(payload)
    assert await waiting() == 0


async def test_nothing_queues_without_a_device(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    await like_first(client, aanya)
    assert await waiting() == 0


async def test_nothing_queues_when_push_is_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vapid_private_key", SecretStr(""))
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "kabir-phone")
    await like_first(client, aanya)
    assert await waiting() == 0
    assert (await client.get("/v1/notifications/config")).json() == {"public_key": None}


async def test_matching_back_tells_the_liker(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, aanya, "aanya-phone")
    await like_first(client, aanya)
    like_id = (await client.get("/v1/likes", headers=kabir)).json()[0]["id"]
    await client.post(f"/v1/likes/{like_id}/match", headers=kabir)

    [(to, payload)] = (await deliver()).sent
    assert (to, payload["body"], payload["url"]) == (
        endpoint("aanya-phone"),
        "It's a match. Say hi.",
        "/app/chats",
    )


async def test_messages_in_a_row_are_one_notification(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await subscribe(client, kabir, "kabir-phone")
    for text_ in ["hey", "you there?", "okay bye"]:
        sent = await client.post(
            f"/v1/chats/{match_id}/messages", json={"body": text_}, headers=aanya
        )
        assert sent.status_code == 201, sent.text

    [(_, payload)] = (await deliver()).sent
    assert payload == {
        "title": "Cards",
        "body": "New message.",
        "url": f"/app/chats/{match_id}",
        "tag": f"chat-{match_id}",
    }


async def test_swap_asked_then_opened(client: AsyncClient) -> None:
    aanya, kabir, match_id = await matched_pair(client)
    await subscribe(client, aanya, "aanya-phone")
    await subscribe(client, kabir, "kabir-phone")

    await ask(client, aanya, match_id, "branch")
    [(to, payload)] = (await deliver()).sent
    assert (to, payload["body"]) == (endpoint("kabir-phone"), "Someone wants to turn a card.")

    await answer(client, kabir, match_id, "branch", yes=True)
    [(to, payload)] = (await deliver()).sent
    assert (to, payload["body"]) == (endpoint("aanya-phone"), "A card just turned.")


async def test_a_device_that_left_is_forgotten(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "kabir-phone")
    await like_first(client, aanya)

    send = FakeSender()
    send.codes[endpoint("kabir-phone")] = 410
    async with SessionLocal() as session:
        await service.deliver(session, send)

    async with engine.connect() as conn:
        count = await conn.execute(text("SELECT count(*) FROM push_subscription"))
        assert count.scalar_one() == 0
    assert await waiting() == 0


async def test_failures_retry_three_times_then_give_up(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "kabir-phone")
    await like_first(client, aanya)

    send = FakeSender()
    send.codes[endpoint("kabir-phone")] = 503
    for left in [1, 1, 0]:
        async with SessionLocal() as session:
            await service.deliver(session, send)
        assert await waiting() == left
    assert len(send.sent) == 3


async def test_the_nine_pm_alert_goes_once_to_finished_profiles(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await subscribe(client, aanya, "aanya-phone")
    # Signed in and subscribed, but no profile yet: no drop to open, so no alert.
    half = await client.post(
        "/v1/auth/google",
        json={"credential": "sub-dev|dev@adgips.ac.in|Dev Test|yes|adgips.ac.in"},
    )
    await subscribe(client, {"Authorization": f"Bearer {half.json()['token']}"}, "dev-phone")

    nine_fifteen = datetime(2026, 11, 22, 15, 45, tzinfo=UTC)  # 9:15 PM IST
    async with SessionLocal() as session:
        assert await drop_service.alert_tonight(session, nine_fifteen) == 1
    async with SessionLocal() as session:
        assert await drop_service.alert_tonight(session, nine_fifteen) == 0

    [(to, payload)] = (await deliver()).sent
    assert (to, payload["body"], payload["url"]) == (
        endpoint("aanya-phone"),
        "Tonight's drop is in.",
        "/app/tonight",
    )


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 11, 22, 14, 0, tzinfo=UTC),  # 7:30 PM IST: too early
        datetime(2026, 11, 22, 20, 30, tzinfo=UTC),  # 2 AM IST: too late to wake anyone
    ],
)
async def test_no_alert_outside_the_evening(client: AsyncClient, at: datetime) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await subscribe(client, aanya, "aanya-phone")
    async with SessionLocal() as session:
        assert await drop_service.alert_tonight(session, at) == 0


async def test_a_shared_phone_follows_whoever_subscribed_last(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "one-phone")
    await subscribe(client, aanya, "one-phone")

    await like_first(client, aanya)  # a like for Kabir
    assert (await deliver()).sent == []


async def test_turning_off_stops_notifications(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    await subscribe(client, kabir, "kabir-phone")
    off = await client.post(
        "/v1/notifications/subscription/remove",
        json={"endpoint": endpoint("kabir-phone")},
        headers=kabir,
    )
    assert off.status_code == 204
    await like_first(client, aanya)
    assert await waiting() == 0


async def test_config_gives_the_public_key(client: AsyncClient) -> None:
    response = await client.get("/v1/notifications/config")
    assert response.json() == {"public_key": "test-public-key"}


async def test_subscriptions_must_be_https(client: AsyncClient) -> None:
    kabir = await finished(client, "Kabir", "man", "women")
    body = {"endpoint": "http://evil.local/x", "keys": {"p256dh": "p", "auth": "a"}}
    response = await client.put("/v1/notifications/subscription", json=body, headers=kabir)
    assert response.status_code == 422


async def test_taking_back_a_like_or_a_swap_request_sends_nothing(client: AsyncClient) -> None:
    aanya, _, match_id = await matched_pair(client)
    await client.post(f"/v1/chats/{match_id}/swaps", json={"card": "branch"}, headers=aanya)
    meera = await finished(client, "Meera", "woman", "men")
    dev = await finished(client, "Dev", "man", "women")
    [item] = [
        i for i in (await drop(client, dev))["items"] if i["profile"]["nickname"] == "Meera nick"
    ]
    prompt_id = item["profile"]["prompts"][0]["id"]
    await client.post(
        f"/v1/drops/tonight/{item['id']}/like", json={"prompt_id": prompt_id}, headers=dev
    )
    [sent] = (await client.get("/v1/likes/sent", headers=dev)).json()
    before = await waiting()

    await client.delete(f"/v1/chats/{match_id}/swaps/branch", headers=aanya)
    await client.delete(f"/v1/likes/sent/{sent['id']}", headers=dev)

    assert await waiting() == before
    assert (await client.get("/v1/likes", headers=meera)).json() == []
