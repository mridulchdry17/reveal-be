import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Swap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One request to swap a card within a match, and what came of it.

    Accepted opens the card for both people at once. A match holds at most one pending or
    accepted swap per card; declined ones stay as history and can be asked again. Ending the
    match closes everything, because only live matches are ever read.
    """

    __tablename__ = "swap"
    __table_args__ = (
        Index(
            "swap_one_open_per_card",
            "match_id",
            "card",
            unique=True,
            postgresql_where=text("status IN ('pending', 'accepted')"),
        ),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("match.id", ondelete="CASCADE"), index=True
    )
    card: Mapped[str] = mapped_column(String(20))
    proposed_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
