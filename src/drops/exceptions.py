from src.exceptions import Conflict, NotFound


class DropItemNotFound(NotFound):
    code = "drop_item_not_found"


class DropItemClosed(Conflict):
    """Already answered, or from a drop that has ended."""

    code = "drop_item_closed"
