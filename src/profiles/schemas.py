import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator

from src.profiles import constants as c
from src.profiles.text_rules import CONTACT_INFO_MESSAGE, has_contact_info


def _no_contact_info(value: str) -> str:
    value = " ".join(value.split())
    if has_contact_info(value):
        raise ValueError(CONTACT_INFO_MESSAGE)
    return value


CleanText = Annotated[str, AfterValidator(_no_contact_info)]


class BasicsUpdate(BaseModel):
    nickname: CleanText = Field(min_length=2, max_length=30)
    vibe: str
    interests: list[CleanText] = Field(min_length=c.MIN_INTERESTS, max_length=c.MAX_INTERESTS)

    @field_validator("vibe")
    @classmethod
    def _known_vibe(cls, value: str) -> str:
        if value not in c.VIBES:
            raise ValueError("Pick one of the vibes")
        return value

    @field_validator("interests")
    @classmethod
    def _clean_interests(cls, value: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for item in value:
            if not 1 <= len(item) <= 24:
                raise ValueError("Keep each interest under 24 characters")
            seen.setdefault(item.lower(), item)
        if len(seen) < c.MIN_INTERESTS:
            raise ValueError(f"Pick at least {c.MIN_INTERESTS} different interests")
        return list(seen.values())


class PromptIn(BaseModel):
    question: CleanText = Field(min_length=3, max_length=60)
    answer: CleanText = Field(min_length=2, max_length=c.PROMPT_ANSWER_MAX)


class PromptsUpdate(BaseModel):
    prompts: list[PromptIn] = Field(min_length=c.PROMPT_COUNT, max_length=c.PROMPT_COUNT)

    @field_validator("prompts")
    @classmethod
    def _different_questions(cls, value: list[PromptIn]) -> list[PromptIn]:
        if len({p.question.lower() for p in value}) != len(value):
            raise ValueError("Pick three different prompts")
        return value


class CardsUpdate(BaseModel):
    branch: CleanText = Field(min_length=2, max_length=40)
    year: int = Field(ge=1, le=5, description="Year of study, 1 = first-year")
    hometown: CleanText = Field(min_length=2, max_length=60)
    looking_for: c.LookingFor
    shown_cards: list[c.Card] = Field(description="Cards shown without a swap")

    @field_validator("shown_cards")
    @classmethod
    def _only_showable(cls, value: list[c.Card]) -> list[c.Card]:
        if any(card not in c.SHOWABLE_CARDS for card in value):
            raise ValueError("Photo and contact open only through swaps")
        return list(dict.fromkeys(value))


class PreferencesUpdate(BaseModel):
    gender: c.Gender
    interested_in: c.InterestedIn
    match_on: list[c.MatchOn] = Field(default_factory=list)
    women_write_first: bool = Field(
        default=False, description="Only applies to women: matches wait for her to start"
    )


class PromptOut(BaseModel):
    id: uuid.UUID
    question: str
    answer: str


class MyProfile(BaseModel):
    """Everything the owner sees about their own profile, including locked cards."""

    first_name: str = Field(description="From the Google account; card 1")
    nickname: str | None
    vibe: str | None
    interests: list[str]
    prompts: list[PromptOut]
    branch: str | None
    year: int | None
    hometown: str | None
    looking_for: c.LookingFor | None
    shown_cards: list[c.Card]
    gender: c.Gender | None
    interested_in: c.InterestedIn | None
    match_on: list[c.MatchOn]
    women_write_first: bool
    # Which of the four screens are done, so the app can resume where they left off.
    basics_done: bool
    prompts_done: bool
    cards_done: bool
    preferences_done: bool
    complete: bool


class Option(BaseModel):
    value: str
    label: str


class ProfileOptions(BaseModel):
    vibes: list[str]
    interest_suggestions: list[str]
    min_interests: int
    max_interests: int
    prompt_questions: list[str]
    prompt_answer_max: int
    nickname_suggestions: list[str]
    looking_for: list[Option]
