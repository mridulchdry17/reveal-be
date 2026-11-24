import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PushSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One device that said yes to notifications (a browser's Web Push subscription)."""

    __tablename__ = "push_subscription"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    # The push service's URL for this device. One device, one row, whoever's signed in.
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))


class PushOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A notification waiting to go out. Written in the same transaction as the event, so a
    crash or restart can't lose it; the sender deletes it once it's delivered or given up."""

    __tablename__ = "push_outbox"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(20))
    url: Mapped[str] = mapped_column(String(200))
    # Same tag = replaces the earlier notification on the phone (one per chat, not one per
    # message), and only one waits here per user and tag.
    tag: Mapped[str] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)


class DropAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The 9 PM alert for one night has been queued. Makes it once per night, even with
    restarts or two processes."""

    __tablename__ = "drop_alert"

    drop_date: Mapped[date] = mapped_column(Date, unique=True)
