from enum import StrEnum


class VerificationMethod(StrEnum):
    """How someone proved they're a student."""

    COLLEGE_EMAIL = "college_email"
    ID_CARD = "id_card"
    ADMIN = "admin"
