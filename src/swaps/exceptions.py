from src.exceptions import Conflict, NotFound


class SwapNotAllowed(Conflict):
    """Already open, already asked, not unlocked yet, or one of you hasn't added it."""

    code = "swap_not_allowed"


class SwapNotFound(NotFound):
    """No request from them for this card."""

    code = "swap_not_found"
