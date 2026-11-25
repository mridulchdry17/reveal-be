import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from src.drops.constants import Decision
from src.matches.constants import COMMENT_MAX
from src.profiles.schemas import CleanText, PublicProfile


class DropItemOut(BaseModel):
    id: uuid.UUID
    decision: Decision | None = Field(description="Null until liked or passed")
    profile: PublicProfile


class Tonight(BaseModel):
    drop_date: date = Field(description="College-time date this drop opened, at 9 PM")
    next_drop_at: datetime
    items: list[DropItemOut]


class LikeRequest(BaseModel):
    """Like one of their prompts, or one of their guess cards you've already guessed."""

    prompt_id: uuid.UUID | None = Field(default=None, description="Which of their prompts")
    guess_card_id: uuid.UUID | None = Field(
        default=None, description="Or which of their guess cards (guess it first)"
    )
    comment: CleanText | None = Field(default=None, max_length=COMMENT_MAX)

    @field_validator("comment")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "LikeRequest":
        if (self.prompt_id is None) == (self.guess_card_id is None):
            raise ValueError("Send exactly one of prompt_id or guess_card_id")
        return self


class LikeResult(BaseModel):
    matched: bool = Field(description="They had already liked you: it's a match")
