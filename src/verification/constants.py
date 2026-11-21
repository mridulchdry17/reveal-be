from enum import StrEnum


class RequestStatus(StrEnum):
    """Where an ID card check is. NONE means the user never sent one."""

    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # Never reviewed within settings.verification_photo_days; photos deleted, send again.
    EXPIRED = "expired"
