import uuid

from pydantic import BaseModel, Field

from src.profiles.constants import GUESS_OPTION_COUNT


class GuessIn(BaseModel):
    pick: int = Field(ge=0, lt=GUESS_OPTION_COUNT, description="Index of the option I pick")


class HintResult(BaseModel):
    card_id: uuid.UUID
    struck: int = Field(description="Index of one wrong option; never the true one")


class GuessResult(BaseModel):
    correct: bool
    answer: int = Field(description="Index of the true option")
    picked: int
