import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AdminAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every admin decision, so there's a record of who let whom in and why."""

    __tablename__ = "admin_action"

    admin_email: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(20))
    # Kept as an email too, so the log still reads well if the account is deleted.
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), index=True
    )
    target_email: Mapped[str] = mapped_column(String(320))
    note: Mapped[str | None] = mapped_column(String(300))
