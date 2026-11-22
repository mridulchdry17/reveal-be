import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.admin.constants import AdminActionKind
from src.safety.constants import ReportReason


class ReviewUser(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class Review(BaseModel):
    id: uuid.UUID
    user: ReviewUser
    submitted_at: datetime


class RejectRequest(BaseModel):
    reason: str = Field(
        min_length=1, max_length=300, description="Shown to the student, e.g. 'ID photo is blurry'"
    )


class LetInRequest(BaseModel):
    email: str = Field(
        min_length=3, max_length=320, description="The Google email they signed in with"
    )
    note: str | None = Field(default=None, max_length=300, description="Why, for the log")


class LetInResult(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class AdminActionOut(BaseModel):
    id: uuid.UUID
    action: AdminActionKind
    admin_email: str
    target_email: str
    note: str | None
    created_at: datetime


class AdminReport(BaseModel):
    """A student's report. Reporting already blocked them and ended the match."""

    id: uuid.UUID
    reason: ReportReason
    details: str | None
    reporter_email: str | None = Field(description="Null if that account was deleted")
    reported_email: str | None
    created_at: datetime
