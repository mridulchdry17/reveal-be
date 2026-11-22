import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Like(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One student liking one of another's prompts, with an optional comment.

    The prompt is copied, not linked: people rewrite their prompts, and the like should
    still say what it was about.
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
    prompt_question: Mapped[str] = mapped_column(String(60))
    prompt_answer: Mapped[str] = mapped_column(String(120))
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
