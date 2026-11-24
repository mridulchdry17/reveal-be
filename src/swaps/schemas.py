from pydantic import BaseModel, Field

from src.profiles.constants import Card
from src.swaps.constants import CardState


class ProposeSwap(BaseModel):
    card: Card


class CardSwap(BaseModel):
    card: Card
    state: CardState


class SwapBoard(BaseModel):
    """Where every swap stands in one match, from the viewer's side."""

    cards: list[CardSwap] = Field(
        description="In card order. Voice is listed only when both have a voice note."
    )
    photo_pieces: list[int] = Field(
        description="Open pieces of their photo (0-8, row by row in a 3x3 grid). "
        "Empty unless both have a photo."
    )
