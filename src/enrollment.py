"""The one place that knows what an enrollment number looks like.

Waitlist uses it now; verification and profiles will use it later. Always store the
normalised form so lookups and uniqueness work regardless of how it was typed.
"""

import re

from src.config import settings

_PATTERN = re.compile(settings.enrollment_pattern)
_SEPARATORS = re.compile(r"[\s\-/]")


def normalize(raw: str) -> str:
    return _SEPARATORS.sub("", raw).upper()


def is_valid(normalized: str) -> bool:
    return _PATTERN.fullmatch(normalized) is not None
