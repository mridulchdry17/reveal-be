from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from src import enrollment


class WaitlistJoinRequest(BaseModel):
    enrollment_number: str = Field(max_length=40, examples=["22EC1047"])
    email: EmailStr

    @field_validator("enrollment_number")
    @classmethod
    def _normalize_enrollment(cls, value: str) -> str:
        normalized = enrollment.normalize(value)
        if not enrollment.is_valid(normalized):
            raise ValueError("Enter your enrollment number as it appears on your ID card")
        return normalized

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()


class WaitlistJoinResponse(BaseModel):
    position: int = Field(description="1-based place in line")
    already_joined: bool


class WaitlistExportRow(BaseModel):
    enrollment_number: str
    email: str
    joined_at: datetime
