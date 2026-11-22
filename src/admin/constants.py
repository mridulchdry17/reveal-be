from enum import StrEnum


class AdminActionKind(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    LET_IN = "let_in"
