import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.chats.constants import MESSAGE_MAX
from src.profiles.schemas import CleanText, PublicProfile
from src.swaps.schemas import SwapBoard


class SendMessage(BaseModel):
    # Numbers, handles and links stay out until the pair swaps contact cards.
    body: CleanText = Field(min_length=1, max_length=MESSAGE_MAX)


class MessageOut(BaseModel):
    id: uuid.UUID
    body: str
    mine: bool
    sent_at: datetime


class ChatSummary(BaseModel):
    """One row in the Chats tab."""

    match_id: uuid.UUID
    profile: PublicProfile
    matched_at: datetime
    last_message: MessageOut | None
    unread: bool = Field(description="Their latest message is newer than what I've seen")


class ChatThread(BaseModel):
    match_id: uuid.UUID
    profile: PublicProfile
    matched_at: datetime
    messages: list[MessageOut] = Field(description="Oldest first, up to the latest 200")
    swaps: SwapBoard
