from src.exceptions import Conflict, NotFound


class LikeNotFound(NotFound):
    code = "like_not_found"


class AlreadyLiked(Conflict):
    code = "already_liked"


class LikeAlreadyAnswered(Conflict):
    code = "like_already_answered"


class MatchNotFound(NotFound):
    """Not yours, never existed, or ended: all look the same."""

    code = "match_not_found"
