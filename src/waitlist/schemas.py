import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src import enrollment

_SOURCE = re.compile(r"[a-z0-9_-]{1,20}")


class WaitlistJoinRequest(BaseModel):
    enrollment_number: str = Field(max_length=40, examples=["22EC1047"])
    email: EmailStr
    confirmed_adult: bool = Field(description="The person confirmed they are 18 or older")
    source: str | None = Field(
        default=None,
        description="Where the visitor came from (e.g. 'wa', 'ig'). Invalid values are dropped.",
    )

    @field_validator("enrollment_number")
    @classmethod
    def _normalize_enrollment(cls, value: str) -> str:
        normalized = enrollment.normalize(value)
        if not enrollment.is_valid(normalized):
            raise ValueError("Check it against your ID card")
        return normalized

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("confirmed_adult")
    @classmethod
    def _must_be_adult(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Reveal is only for people 18 or older")
        return value

    @field_validator("source", mode="before")
    @classmethod
    def _clean_source(cls, value: object) -> str | None:
        # Tracking must never block a join: anything unexpected becomes None.
        if not isinstance(value, str):
            return None
        cleaned = value.strip().lower()
        return cleaned if _SOURCE.fullmatch(cleaned) else None


class WaitlistJoinResponse(BaseModel):
    position: int = Field(description="1-based place in line")
    already_joined: bool


class WaitlistExportRow(BaseModel):
    enrollment_number: str
    email: str
    source: str | None
    joined_at: datetime
