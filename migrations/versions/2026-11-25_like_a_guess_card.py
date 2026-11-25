"""like_a_guess_card

A like can be about a guess card as well as a prompt. The copied prompt columns become
generic `question` / `answer` (renamed, so existing likes keep their text), the question
widens to fit a guess card's, and `kind` / `guess_kind` say what was liked.

Revision ID: 0a6b56f7a41c
Revises: c7886f0cf92d
Create Date: 2026-11-25 17:44:22.435439

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a6b56f7a41c"
down_revision: str | Sequence[str] | None = "c7886f0cf92d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "profile_like",
        "prompt_question",
        new_column_name="question",
        type_=sa.String(length=90),
        existing_type=sa.String(length=60),
        existing_nullable=False,
    )
    op.alter_column(
        "profile_like",
        "prompt_answer",
        new_column_name="answer",
        existing_type=sa.String(length=120),
        existing_nullable=False,
    )
    op.add_column(
        "profile_like",
        sa.Column("kind", sa.String(length=10), server_default="prompt", nullable=False),
    )
    op.add_column("profile_like", sa.Column("guess_kind", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema. Guess-card likes keep their text, cut to the old prompt length."""
    op.drop_column("profile_like", "guess_kind")
    op.drop_column("profile_like", "kind")
    op.alter_column(
        "profile_like",
        "answer",
        new_column_name="prompt_answer",
        existing_type=sa.String(length=120),
        existing_nullable=False,
    )
    op.alter_column(
        "profile_like",
        "question",
        new_column_name="prompt_question",
        type_=sa.String(length=60),
        existing_type=sa.String(length=90),
        existing_nullable=False,
        postgresql_using="left(question, 60)",
    )
