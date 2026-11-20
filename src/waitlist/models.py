from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WaitlistEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "waitlist_entry"

    # Stored normalised (see src/enrollment.py) so uniqueness ignores formatting.
    enrollment_number: Mapped[str] = mapped_column(String(32), unique=True)
    # Stored lowercased.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Where they came from ('wa', 'ig', ...), for seeing which channel works.
    source: Mapped[str | None] = mapped_column(String(20))
