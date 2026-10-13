"""falhas caras por usuário

Revision ID: e4a7c2b9f1d3
Revises: b3f1c9d2a7e4
Create Date: 2026-10-13 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7c2b9f1d3"
down_revision: str | Sequence[str] | None = "b3f1c9d2a7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Imports que gastaram Claude ou whisper: as falhas deles têm um limite diário por usuário.
    op.add_column(
        "imports", sa.Column("cost_incurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_imports_user_id_cost_incurred_at",
        "imports",
        ["user_id", "cost_incurred_at"],
        postgresql_where=sa.text("cost_incurred_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_imports_user_id_cost_incurred_at", table_name="imports")
    op.drop_column("imports", "cost_incurred_at")
