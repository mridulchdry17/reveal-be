from enum import StrEnum

COMMENT_MAX = 140


class LikeStatus(StrEnum):
    PENDING = "pending"  # in their Likes list, waiting for them
    MATCHED = "matched"  # they liked back
    PASSED = "passed"  # they passed; the liker is never told
