from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.drops.helpers import Clock, drop, finished, nicknames
from tests.profiles.test_profile import UNVERIFIED, student


async def test_drop_shows_people_who_fit_both_ways(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    await finished(client, "Dev", "man", "men")  # not interested in Aanya
    await finished(client, "Meera", "woman", "men")  # Aanya wants men
    await finished(client, "Ira", "nonbinary", "everyone")  # Aanya wants men

    assert nicknames(await drop(client, aanya)) == {"Kabir nick"}


async def test_everyone_means_every_gender_that_wants_you_back(client: AsyncClient) -> None:
    sam = await finished(client, "Sam", "nonbinary", "everyone")
    await finished(client, "Kabir", "man", "women")  # doesn't want Sam
    await finished(client, "Meera", "woman", "everyone")
    await finished(client, "Ira", "nonbinary", "everyone")

    assert nicknames(await drop(client, sam)) == {"Meera nick", "Ira nick"}


async def test_year_does_not_limit_who_you_see(client: AsyncClient) -> None:
    first_year = await finished(client, "Aanya", "woman", "men", year=1)
    await finished(client, "Kabir", "man", "women", year=4)

    assert nicknames(await drop(client, first_year)) == {"Kabir nick"}


async def test_everyone_has_the_same_hidden_cards(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women", shown_cards=["first_name", "hometown"])

    profile = (await drop(client, aanya))["items"][0]["profile"]

    assert profile["looking_for"] == "serious"
    assert profile["first_name"] is None
    assert profile["branch"] is None
    assert profile["year"] is None
    assert profile["hometown"] is None
    assert profile["shown_cards"] == ["looking_for"]
    assert profile["hidden_cards"] == ["first_name", "branch", "hometown", "photo", "contact"]
    assert len(profile["prompts"]) == 3


async def test_drop_has_at_most_five_and_stays_the_same(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    for n in range(7):
        await finished(client, f"Man{n}", "man", "women")

    first = await drop(client, aanya)
    again = await drop(client, aanya)

    assert len(first["items"]) == 5
    assert [i["id"] for i in again["items"]] == [i["id"] for i in first["items"]]


async def test_drop_tops_up_when_someone_new_finishes(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    assert (await drop(client, aanya))["items"] == []

    await finished(client, "Kabir", "man", "women")

    assert nicknames(await drop(client, aanya)) == {"Kabir nick"}


async def test_match_me_on_puts_better_fits_first(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men", hometown="Jaipur")
    await client.put(
        "/v1/profile/me/preferences",
        json={"gender": "woman", "interested_in": "men", "match_on": ["same_hometown"]},
        headers=aanya,
    )
    for n in range(6):
        await finished(client, f"Far{n}", "man", "women", hometown="Pune")
    await finished(client, "Local", "man", "women", hometown="jaipur")

    items = (await drop(client, aanya))["items"]

    assert items[0]["profile"]["nickname"] == "Local nick"


async def test_drop_opens_at_9pm_college_time(client: AsyncClient, clock: Clock) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")

    clock.at = datetime(2026, 11, 22, 15, 29, tzinfo=UTC)  # 8:59 PM IST
    before = await drop(client, aanya)
    clock.at = datetime(2026, 11, 22, 15, 30, tzinfo=UTC)  # 9:00 PM IST
    after = await drop(client, aanya)

    assert before["drop_date"] == "2026-11-21"
    assert before["next_drop_at"].startswith("2026-11-22T15:30:00")
    assert after["drop_date"] == "2026-11-22"
    assert after["next_drop_at"].startswith("2026-11-23T15:30:00")


async def test_people_passed_on_never_come_back(client: AsyncClient, clock: Clock) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    item = (await drop(client, aanya))["items"][0]

    response = await client.post(f"/v1/drops/tonight/{item['id']}/pass", headers=aanya)
    assert response.status_code == 204

    clock.at += timedelta(days=30)
    assert (await drop(client, aanya))["items"] == []


async def test_unanswered_people_return_after_two_weeks(client: AsyncClient, clock: Clock) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    assert nicknames(await drop(client, aanya)) == {"Kabir nick"}

    clock.at += timedelta(days=1)
    assert (await drop(client, aanya))["items"] == []

    clock.at += timedelta(days=14)
    assert nicknames(await drop(client, aanya)) == {"Kabir nick"}


async def test_last_nights_drop_cannot_be_answered(client: AsyncClient, clock: Clock) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    await finished(client, "Kabir", "man", "women")
    item = (await drop(client, aanya))["items"][0]

    clock.at += timedelta(days=1)
    response = await client.post(f"/v1/drops/tonight/{item['id']}/pass", headers=aanya)

    assert response.status_code == 409
    assert response.json()["code"] == "drop_item_closed"


async def test_someone_elses_drop_item_looks_missing(client: AsyncClient) -> None:
    aanya = await finished(client, "Aanya", "woman", "men")
    kabir = await finished(client, "Kabir", "man", "women")
    item = (await drop(client, aanya))["items"][0]

    response = await client.post(f"/v1/drops/tonight/{item['id']}/pass", headers=kabir)

    assert response.status_code == 404


async def test_drop_needs_a_finished_profile(client: AsyncClient) -> None:
    headers = await student(client)

    response = await client.get("/v1/drops/tonight", headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "profile_incomplete"


async def test_drop_is_for_verified_students_only(client: AsyncClient) -> None:
    headers = await student(client, UNVERIFIED)

    assert (await client.get("/v1/drops/tonight", headers=headers)).status_code == 403
