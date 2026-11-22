import uuid
from datetime import datetime

from pydantic import BaseModel

from src.profiles.schemas import PublicProfile


class ReceivedLike(BaseModel):
    """Someone who liked me and is waiting for an answer."""

    id: uuid.UUID
    prompt_question: str
    prompt_answer: str
    comment: str | None
    created_at: datetime
    profile: PublicProfile
