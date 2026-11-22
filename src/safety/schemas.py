import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.safety.constants import ReportReason


class ReportRequest(BaseModel):
    reason: ReportReason
    details: str | None = Field(default=None, max_length=500, description="What happened")

    @field_validator("details")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return " ".join(value.split()) or None if value else None


class ReportOut(BaseModel):
    """A report as admins see it."""

    id: uuid.UUID
    reason: ReportReason
    details: str | None
    reporter_id: uuid.UUID | None
    reported_id: uuid.UUID | None
    created_at: datetime
