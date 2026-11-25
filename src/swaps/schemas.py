from datetime import datetime

from pydantic import BaseModel, Field

from src.profiles.constants import Card
from src.swaps.constants import CardState, SwapSide


class ProposeSwap(BaseModel):
    card: Card


class CardSwap(BaseModel):
    card: Card
    state: CardState
    asked_at: datetime | None = Field(
        description="When the current request (pending or accepted) was made"
    )
    decided_at: datetime | None = Field(description="When it opened; null unless open")


class SwapBoard(BaseModel):
    """Where every swap stands in one match, from the viewer's side."""

    cards: list[CardSwap] = Field(
        description="In card order. Voice is listed only when both have a voice note."
    )
    photo_pieces: list[int] = Field(
        description="Open pieces of their photo (0-8, row by row in a 3x3 grid). "
        "Empty unless both have a photo. One per card swap plus one per right guess on "
        "their cards, up to 6; all 9 after the photo swap."
    )


class PendingSwap(BaseModel):
    card: Card
    by: SwapSide = Field(description="Who asked")


class SwapSummary(BaseModel):
    """One match's swaps in brief, for the Chats list."""

    photo_pieces: int = Field(description="How many of their 9 photo pieces are open for me")
    pending_swap: PendingSwap | None = Field(description="The most recent request waiting")
