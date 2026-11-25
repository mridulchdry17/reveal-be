import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Like(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One student liking one of another's prompts or guess cards, with an optional comment.

    What was liked is copied, not linked: people rewrite their prompts and cards, and the
    like should still say what it was about. For a guess card, `answer` is the true option.
    """

    # "like" is a reserved word in Postgres.
    __tablename__ = "profile_like"
    __table_args__ = (UniqueConstraint("from_user_id", "to_user_id"),)

    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE")
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    # See LikedKind: a prompt, or a guess card the liker has guessed.
    kind: Mapped[str] = mapped_column(String(10), server_default="prompt")
    question: Mapped[str] = mapped_column(String(90))
    answer: Mapped[str] = mapped_column(String(120))
    # The guess card's kind (GuessKind); None for a prompt.
    guess_kind: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(String(140))
    status: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Two students who liked each other. Stored once per pair, smaller id first.

    Unmatch, block and report end it for both. The row stays (reports point at it), but an
    ended match is gone from both sides: no chat, no list entry.
    """

    __tablename__ = "match"
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id"),
        CheckConstraint("user_a_id < user_b_id", name="ordered_pair"),
    )

    user_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
