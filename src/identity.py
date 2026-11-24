"""The one place that knows how an email, phone number or Instagram handle is fingerprinted.

The hide list stores fingerprints, not the values people type, and matches them against
accounts and contact cards in SQL. Both sides must build them the same way, so both use
this module. Values must already be normalised (see hides.schemas).
"""

import hashlib
from enum import StrEnum

from sqlalchemy import String, func, literal
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement


class IdentityKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    INSTAGRAM = "instagram"


def fingerprint(kind: IdentityKind, value: str) -> str:
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()


type _Column = ColumnElement[str] | ColumnElement[str | None] | InstrumentedAttribute[str | None]


def fingerprint_sql(kind: IdentityKind | _Column, value: _Column) -> ColumnElement[str]:
    """The same fingerprint, computed by Postgres for a column (or a kind column)."""
    label = literal(str(kind), String) if isinstance(kind, IdentityKind) else kind
    return func.encode(func.sha256(func.convert_to(func.concat(label, ":", value), "UTF8")), "hex")
