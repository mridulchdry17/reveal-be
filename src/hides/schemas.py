import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

from src.identity import IdentityKind
from src.profiles.constants import ContactKind
from src.profiles.schemas import Contact

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class HideRequest(BaseModel):
    """Someone to hide, by an email, a 10-digit mobile number or an Instagram username."""

    kind: IdentityKind
    value: str = Field(min_length=1, max_length=320)

    @field_validator("value")
    @classmethod
    def _normalize(cls, value: str, info: ValidationInfo) -> str:
        raw = value.strip()
        kind = info.data.get("kind")
        if kind == IdentityKind.EMAIL:
            email = raw.lower()
            if not _EMAIL.fullmatch(email):
                raise ValueError("That doesn't look like an email address")
            return email
        if kind is None:  # kind itself was invalid; that error is enough
            return raw
        # Phone numbers and handles follow the same rules as card 7, so they match it.
        try:
            return Contact(kind=ContactKind(kind), value=raw).value
        except ValidationError as error:
            raise ValueError(error.errors()[0]["msg"].removeprefix("Value error, ")) from None


class HiddenOut(BaseModel):
    id: uuid.UUID
    kind: IdentityKind
    hint: str = Field(description="Masked, e.g. 98••••••10. The full value isn't stored")
    created_at: datetime


class HideList(BaseModel):
    items: list[HiddenOut]
    max: int
