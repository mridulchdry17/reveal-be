import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VerificationRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A student's ID card + selfie, waiting for a person to check them.

    One row per user; sending again after a rejection replaces it. The photos are files
    on the server (see storage.py), deleted as soon as the request is reviewed or expires.
    """

    __tablename__ = "verification_request"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    # File names inside settings.verification_photos_dir. None once deleted.
    selfie_file: Mapped[str | None] = mapped_column(String(100))
    id_card_file: Mapped[str | None] = mapped_column(String(100))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String(300))
