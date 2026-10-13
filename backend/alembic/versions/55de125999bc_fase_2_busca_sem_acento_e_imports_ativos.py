"""fase 2: busca sem acento e imports ativos

Revision ID: 55de125999bc
Revises: acf8be44a3f4
Create Date: 2026-10-13 12:29:56.528422

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55de125999bc"
down_revision: str | Sequence[str] | None = "acf8be44a3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Busca do livro ignora acentos ("acucar" acha "açúcar").
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_index(
        "ix_imports_active_updated_at",
        "imports",
        ["updated_at"],
        postgresql_where=sa.text("status NOT IN ('done', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("ix_imports_active_updated_at", table_name="imports")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
