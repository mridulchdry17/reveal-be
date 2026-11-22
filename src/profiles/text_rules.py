"""Keep contact details out of the parts of a profile everyone can see.

Phone numbers, @handles, links and "insta/snap" mentions belong on card 7, which only
opens after the photo swap. This catches the obvious cases; moderation catches the rest.
"""

import re

_PATTERNS = [
    re.compile(r"(?:\d[\s.-]?){7,}"),  # 7+ digits, allowing spaces or dashes between
    re.compile(r"@\w{2,}"),
    re.compile(r"https?://|www\.|\.(?:com|in|me|io|co)\b", re.IGNORECASE),
    re.compile(r"\b(?:insta(?:gram)?|ig|snap(?:chat)?|whatsapp|wa\.me|telegram|t\.me)\b", re.I),
]


def has_contact_info(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


CONTACT_INFO_MESSAGE = "No numbers, handles or links here. Those go on your last card."
