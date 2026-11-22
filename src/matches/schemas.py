import uuid
from datetime import datetime

from pydantic import BaseModel

from src.profiles.schemas import PublicProfile


class MatchInfo(BaseModel):
    """One of my live matches, as other domains (chat, safety) see it."""

    id: uuid.UUID
    other_user_id: uuid.UUID
    matched_at: datetime


class ReceivedLike(BaseModel):
    """Someone who liked me and is waiting for an answer."""

    id: uuid.UUID
    prompt_question: str
    prompt_answer: str
    comment: str | None
    created_at: datetime
    profile: PublicProfile
