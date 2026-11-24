import re
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, ValidationError, model_validator

from src.identity import IdentityKind
from src.profiles.constants import ContactKind
from src.profiles.schemas import Contact

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class HideRequest(BaseModel):
    """Someone to hide, by an email, a 10-digit mobile number or an Instagram username."""

    kind: IdentityKind
    value: str = Field(min_length=1, max_length=320)

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        raw = self.value.strip()
        if self.kind == IdentityKind.EMAIL:
            email = raw.lower()
            if not _EMAIL.fullmatch(email):
                raise ValueError("That doesn't look like an email address")
            self.value = email
            return self
        # Phone numbers and handles follow the same rules as card 7, so they match it.
        try:
            self.value = Contact(kind=ContactKind(self.kind), value=raw).value
        except ValidationError as error:
            raise ValueError(error.errors()[0]["msg"].removeprefix("Value error, ")) from None
        return self


class HiddenOut(BaseModel):
    id: uuid.UUID
    kind: IdentityKind
    hint: str = Field(description="Masked, e.g. 98••••••10. The full value isn't stored")
    created_at: datetime


class HideList(BaseModel):
    items: list[HiddenOut]
    max: int
