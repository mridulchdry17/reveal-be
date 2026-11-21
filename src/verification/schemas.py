from datetime import datetime

from pydantic import BaseModel

from src.verification.constants import RequestStatus


class VerificationStatus(BaseModel):
    status: RequestStatus
    submitted_at: datetime | None = None
    # Written by the admin for the student, e.g. "ID photo is blurry".
    reject_reason: str | None = None
