import re
import uuid
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    ValidationInfo,
    field_validator,
)

from src.profiles import constants as c
from src.profiles.text_rules import CONTACT_INFO_MESSAGE, has_contact_info


def _collapse_spaces(value: object) -> object:
    # Before the length checks, so "   " counts as empty.
    return " ".join(value.split()) if isinstance(value, str) else value


def _no_contact_info(value: str) -> str:
    if has_contact_info(value):
        raise ValueError(CONTACT_INFO_MESSAGE)
    return value


CleanText = Annotated[str, BeforeValidator(_collapse_spaces), AfterValidator(_no_contact_info)]


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


_INSTAGRAM = re.compile(r"^(?!.*\.\.)(?!\.)[a-z0-9._]{1,30}(?<!\.)$")
_PHONE = re.compile(r"^[6-9]\d{9}$")


class Contact(BaseModel):
    """Card 7: an Instagram handle (no @) or a 10-digit Indian mobile number."""

    kind: c.ContactKind
    value: str = Field(max_length=40)

    @field_validator("value")
    @classmethod
    def _normalize(cls, value: str, info: ValidationInfo) -> str:
        raw = value.strip()
        if info.data.get("kind") == c.ContactKind.INSTAGRAM:
            handle = raw.removeprefix("@").lower()
            if not _INSTAGRAM.match(handle):
                raise ValueError("That doesn't look like an Instagram username")
            return handle
        digits = re.sub(r"[\s()-]", "", raw).removeprefix("+91")
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not _PHONE.match(digits):
            raise ValueError("Enter a 10-digit Indian mobile number")
        return digits


class PreferencesUpdate(BaseModel):
    gender: c.Gender
    interested_in: c.InterestedIn
    match_on: list[c.MatchOn] = Field(default_factory=list)


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
    has_photo: bool = Field(description="Card 6; fetch it with GET /v1/profile/me/photo")
    contact: Contact | None = Field(description="Card 7, optional; only ever shown to its owner")
    gender: c.Gender | None
    interested_in: c.InterestedIn | None
    match_on: list[c.MatchOn]
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


class PublicProfile(BaseModel):
    """Another student's profile as one viewer may see it.

    Built only by profiles.service.public_profiles. A hidden card's value is null here,
    never sent and hidden by the app.
    """

    nickname: str
    vibe: str
    interests: list[str]
    prompts: list[PromptOut]
    first_name: str | None
    branch: str | None
    year: int | None = Field(description="Part of the branch card")
    hometown: str | None
    looking_for: c.LookingFor | None
    shown_cards: list[c.Card]
    hidden_cards: list[c.Card]
