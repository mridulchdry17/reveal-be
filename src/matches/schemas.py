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


class SentLike(BaseModel):
    """A like I sent that's still waiting for an answer, as far as I can tell."""

    id: uuid.UUID
    nickname: str
    liked: Liked
    comment: str | None
    created_at: datetime
    has_blurred_photo: bool = Field(
        description="We both have a photo: GET /v1/likes/sent/{id}/photo shows theirs, blurred"
    )


class MatchResult(BaseModel):
    match_id: uuid.UUID = Field(description="The new chat: GET /v1/chats/{match_id}")


class ReceivedLike(BaseModel):
    """Someone who liked me and is waiting for an answer."""

    id: uuid.UUID
    liked: Liked
    prompt_question: str = Field(description="Deprecated: use liked.question")
    prompt_answer: str = Field(description="Deprecated: use liked.answer")
    comment: str | None
    created_at: datetime
    profile: PublicProfile
    their_right_guesses: int = Field(description="How many of my guess cards they got right")
    my_cards_total: int = Field(description="How many guess cards I have")
