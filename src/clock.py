from datetime import UTC, datetime


def now() -> datetime:
    """The current time as a dependency, so tests can set the clock (e.g. to 9 PM)."""
    return datetime.now(UTC)
