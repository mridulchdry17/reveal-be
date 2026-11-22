import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One chat message between two matched students. Never logged."""

    __tablename__ = "message"
    __table_args__ = (Index("message_match_id_created_at_idx", "match_id", "created_at"),)

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(String(1000))


class ChatRead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The last message each person has seen in a chat, for the unread dot."""

    __tablename__ = "chat_read"
    __table_args__ = (UniqueConstraint("match_id", "user_id"),)

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    last_read_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message.id", ondelete="CASCADE")
    )
