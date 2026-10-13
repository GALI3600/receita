"""tentativas do whisper por vídeo

Revision ID: d7be03933e68
Revises: 55de125999bc
Create Date: 2026-10-13 13:29:11.247963

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7be03933e68"
down_revision: str | Sequence[str] | None = "55de125999bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # O vídeo não volta para o whisper depois de falhas que se repetiriam.
    op.add_column(
        "videos", sa.Column("whisper_attempts", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("videos", sa.Column("whisper_error_code", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "whisper_error_code")
    op.drop_column("videos", "whisper_attempts")
