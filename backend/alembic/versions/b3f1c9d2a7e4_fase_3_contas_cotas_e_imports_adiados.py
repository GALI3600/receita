"""fase 3: contas, cotas e imports adiados

Revision ID: b3f1c9d2a7e4
Revises: d7be03933e68
Create Date: 2026-10-13 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1c9d2a7e4"
down_revision: str | Sequence[str] | None = "d7be03933e68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = ("pending", "fetching", "transcribing", "generating", "done", "failed")


def _status_check(statuses: Sequence[str]) -> str:
    return "status IN ({})".format(", ".join(f"'{status}'" for status in statuses))


def upgrade() -> None:
    # Orçamento do Claude esgotado: o import espera o dia seguinte com status `deferred`.
    op.drop_constraint(op.f("ck_imports_import_status"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_import_status"), "imports", _status_check((*_STATUSES, "deferred"))
    )

    # Cota diária: quando o import concluiu gerando receita nova com o Claude.
    op.add_column("imports", sa.Column("charged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_imports_user_id_charged_at",
        "imports",
        ["user_id", "charged_at"],
        postgresql_where=sa.text("charged_at IS NOT NULL"),
    )

    # E-mail normalizado: a unicidade não depende de maiúsculas.
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")
    op.create_check_constraint(op.f("ck_users_email_lowercase"), "users", "email = lower(email)")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_email_lowercase"), "users", type_="check")
    op.drop_index("ix_imports_user_id_charged_at", table_name="imports")
    op.drop_column("imports", "charged_at")

    # Sem `deferred` no CHECK: os adiados voltam para a fila como pendentes.
    op.execute("UPDATE imports SET status = 'pending' WHERE status = 'deferred'")
    op.drop_constraint(op.f("ck_imports_import_status"), "imports", type_="check")
    op.create_check_constraint(
        op.f("ck_imports_import_status"), "imports", _status_check(_STATUSES)
    )
