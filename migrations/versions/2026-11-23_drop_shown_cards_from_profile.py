"""drop_shown_cards_from_profile

Revision ID: 2370ec1920df
Revises: d8c06c4b969e
Create Date: 2026-11-23 00:23:31.266469

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2370ec1920df"
down_revision: str | Sequence[str] | None = "d8c06c4b969e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Everyone has the same card layout now, so the per-profile choice goes."""
    op.drop_column("profile", "shown_cards")


def downgrade() -> None:
    op.add_column(
        "profile",
        sa.Column(
            "shown_cards",
            postgresql.ARRAY(sa.VARCHAR(length=20)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
