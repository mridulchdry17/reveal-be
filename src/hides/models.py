import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HiddenContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone a student never wants to see, or be seen by, on Reveal.

    Stores a fingerprint of the email, phone or Instagram handle (src/identity.py), never
    the value, plus a masked hint so the owner can tell their entries apart.
    """

    __tablename__ = "hidden_contact"
    __table_args__ = (UniqueConstraint("owner_id", "fingerprint"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    hint: Mapped[str] = mapped_column(String(60))
