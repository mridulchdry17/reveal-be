import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What a verified student shows others. Filled in over the four profile screens."""

    __tablename__ = "profile"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), unique=True
    )
    # Screen 1
    nickname: Mapped[str | None] = mapped_column(String(30))
    vibe: Mapped[str | None] = mapped_column(String(30))
    interests: Mapped[list[str]] = mapped_column(ARRAY(String(24)), default=list)
    # Screen 3: card contents
    branch: Mapped[str | None] = mapped_column(String(40))
    year: Mapped[int | None] = mapped_column(SmallInteger)
    hometown: Mapped[str | None] = mapped_column(String(60))
    looking_for: Mapped[str | None] = mapped_column(String(30))
    # Card 6: storage key of the re-encoded photo (src/media.py). Opens only by photo swap.
    photo_key: Mapped[str | None] = mapped_column(String(100))
    # Card 5, optional: storage key, type and length of the voice note. Opens only by swap.
    voice_key: Mapped[str | None] = mapped_column(String(100))
    voice_type: Mapped[str | None] = mapped_column(String(20))
    voice_seconds: Mapped[int | None] = mapped_column(SmallInteger)
    # Card 7, optional and sealed: never part of what others see until the contact swap.
    contact_kind: Mapped[str | None] = mapped_column(String(20))
    contact_value: Mapped[str | None] = mapped_column(String(40))
    # Screen 4
    gender: Mapped[str | None] = mapped_column(String(20))
    interested_in: Mapped[str | None] = mapped_column(String(20))
    match_on: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    # Set once every required part is filled; the drop only shows complete profiles.
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfilePrompt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One of a profile's three prompts. Its own row so a like can point at it."""

    __tablename__ = "profile_prompt"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    question: Mapped[str] = mapped_column(String(60))
    answer: Mapped[str] = mapped_column(String(120))


class GuessCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One of a profile's three guess cards: a question, three options, the true one.

    Others guess it once each (Guess). Changing a card makes a new row, so old guesses on it
    go with the old row.
    """

    __tablename__ = "guess_card"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(20))
    question: Mapped[str] = mapped_column(String(90))
    options: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    # Index into options. Shown to a viewer only after they've guessed this card.
    answer: Mapped[int] = mapped_column(SmallInteger)


class Guess(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One viewer's one try at someone's guess card. Right guesses unblur their photo."""

    __tablename__ = "guess"
    __table_args__ = (UniqueConstraint("guesser_id", "card_id"),)

    guesser_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("guess_card.id", ondelete="CASCADE"), index=True
    )
    picked: Mapped[int] = mapped_column(SmallInteger)
    correct: Mapped[bool] = mapped_column(Boolean)
