from enum import StrEnum

COMMENT_MAX = 140


class LikedKind(StrEnum):
    PROMPT = "prompt"
    GUESS = "guess"  # one of their guess cards, after guessing it


class LikeStatus(StrEnum):
    PENDING = "pending"  # in their Likes list, waiting for them
    MATCHED = "matched"  # they liked back
    PASSED = "passed"  # they passed; the liker is never told
    WITHDRAWN = "withdrawn"  # the liker took it back before an answer


# What the liker sees as "waiting for an answer": a pass is never shown to them.
LOOKS_PENDING = (LikeStatus.PENDING, LikeStatus.PASSED)
