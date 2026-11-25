from enum import StrEnum

from src.profiles.constants import Card

# Cards 1-5 apart from "looking for", which everyone already shows. Voice only counts
# when both have a voice note.
CARD_SWAPS = (Card.FIRST_NAME, Card.BRANCH, Card.HOMETOWN, Card.VOICE)
SWAPPABLE = (*CARD_SWAPS, Card.PHOTO, Card.CONTACT)
# Photo, then contact: each needs the one before it, and both people to have one.
NEEDS_BOTH = (Card.VOICE, Card.PHOTO, Card.CONTACT)

PHOTO_PIECES = 9
PIECES_BEFORE_PHOTO_SWAP = 6
# 3x3 grid, row by row. Corners and sides first; the centre column, where a face
# usually is, last. Only the photo swap opens the last three.
PIECE_ORDER = (6, 8, 0, 2, 5, 3, 7, 1, 4)


class SwapStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"  # the asker took it back before an answer


class CardState(StrEnum):
    """One card of theirs, from where I stand."""

    OPEN = "open"  # swapped: we both see each other's
    THEY_ASKED = "they_asked"  # waiting for my Swap / Not yet
    YOU_ASKED = "you_asked"  # waiting for theirs
    CAN_ASK = "can_ask"
    LOCKED = "locked"  # photo needs a card swap first; contact needs the photo swap
    NEEDS_YOURS = "needs_yours"  # I haven't added this card yet
    NEEDS_THEIRS = "needs_theirs"  # they haven't added it yet
