import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.matches.constants import LikedKind
from src.profiles.constants import GuessKind
from src.profiles.schemas import PublicProfile


class Liked(BaseModel):
    """What a like was about, copied when it was sent."""

    kind: LikedKind
    question: str
    answer: str = Field(description="The prompt's answer, or the guess card's true option")
    guess_kind: GuessKind | None = Field(description="Null for a prompt")


class MatchInfo(BaseModel):
    """One of my live matches, as other domains (chat, safety) see it."""

    id: uuid.UUID
    other_user_id: uuid.UUID
    matched_at: datetime


class ReceivedLike(BaseModel):
    """Someone who liked me and is waiting for an answer."""

    id: uuid.UUID
    liked: Liked
    prompt_question: str = Field(description="Deprecated: use liked.question")
    prompt_answer: str = Field(description="Deprecated: use liked.answer")
    comment: str | None
    created_at: datetime
    profile: PublicProfile
