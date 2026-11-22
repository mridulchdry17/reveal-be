import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Block(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One student blocked another. Silent: the blocked person is never told."""

    __tablename__ = "block"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)

    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A report for admins to look at. Reporting also blocks and ends the match."""

    __tablename__ = "report"

    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL")
    )
    reported_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True
    )
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("match.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(20))
    details: Mapped[str | None] = mapped_column(String(500))
