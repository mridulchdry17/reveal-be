import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DropItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One profile in one viewer's drop for one night, and what they did with it."""

    __tablename__ = "drop_item"
    __table_args__ = (UniqueConstraint("viewer_id", "shown_user_id", "drop_date"),)

    viewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    shown_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    # The college-time date the drop opened (at 9 PM).
    drop_date: Mapped[date] = mapped_column(Date)
    position: Mapped[int] = mapped_column(SmallInteger)
    # None until they like or pass. See Decision.
    decision: Mapped[str | None] = mapped_column(String(10))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
