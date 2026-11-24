from enum import StrEnum


class Event(StrEnum):
    DROP = "drop"
    LIKE = "like"
    MATCH = "match"
    MESSAGE = "message"
    SWAP_ASKED = "swap_asked"
    SWAP_OPENED = "swap_opened"


# Lock-screen copy is generic on purpose: never names, message text or photos. The title
# matches the plain home-screen label ("Cards"), so a glance at a phone gives nothing away.
TITLE = "Cards"
COPY: dict[Event, str] = {
    Event.DROP: "Tonight's drop is in.",
    Event.LIKE: "Someone liked one of your answers.",
    Event.MATCH: "It's a match. Say hi.",
    Event.MESSAGE: "New message.",
    Event.SWAP_ASKED: "Someone wants to turn a card.",
    Event.SWAP_OPENED: "A card just turned.",
}
# How long a push service keeps trying a phone that's offline. A drop alert is stale by
# midnight; the rest can wait a day.
TTL_SECONDS: dict[Event, int] = {Event.DROP: 3 * 3600}
DEFAULT_TTL_SECONDS = 24 * 3600

# The 9 PM alert goes out only until this hour (college time), so a server that was down
# at 9 doesn't wake people at 3 AM.
DROP_ALERT_UNTIL_HOUR = 23
MAX_ATTEMPTS = 3
BATCH_SIZE = 50
POLL_SECONDS = 3.0
