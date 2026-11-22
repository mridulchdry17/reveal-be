from enum import StrEnum


class ReportReason(StrEnum):
    HARASSMENT = "harassment"
    INAPPROPRIATE = "inappropriate"
    FAKE_PROFILE = "fake_profile"
    SPAM = "spam"
    UNDERAGE = "underage"
    OTHER = "other"
