"""custo fase 0: contabilidade do claude

Revision ID: f2a6d8c4e1b7
Revises: e4a7c2b9f1d3
Create Date: 2026-10-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a6d8c4e1b7"
down_revision: str | Sequence[str] | None = "e4a7c2b9f1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSES = ("import", "deferred", "backfill", "eval", "cli")


def upgrade() -> None:
    # Para que serve cada chamada: o orçamento de produção ignora `eval`. As linhas antigas
    # vieram de imports e do CLI, sem como separar: contam como `import`, como antes. O default
    # fica: durante o deploy o worker antigo ainda grava sem `purpose`.
    op.add_column(
        "llm_calls",
        sa.Column("purpose", sa.String(length=8), server_default="import", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_llm_calls_llm_purpose"),
        "llm_calls",
        "purpose IN ({})".format(", ".join(f"'{p}'" for p in _PURPOSES)),
    )

    # Início da chamada (simulação do TTL do cache). Nas linhas antigas, gravadas depois da
    # resposta, fica o created_at: até ~80 s depois do início real.
    op.add_column("llm_calls", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE llm_calls SET started_at = created_at")
    op.alter_column("llm_calls", "started_at", nullable=False, server_default=sa.text("now()"))
    op.create_index("ix_llm_calls_started_at", "llm_calls", ["started_at"])

    op.add_column("llm_calls", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("llm_calls", sa.Column("batch_id", sa.String(length=100), nullable=True))
    op.add_column("llm_calls", sa.Column("effort", sa.String(length=10), nullable=True))
    op.add_column("llm_calls", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_calls", sa.Column("stop_reason", sa.String(length=30), nullable=True))
    op.add_column("llm_calls", sa.Column("request_id", sa.String(length=100), nullable=True))
    op.add_column("llm_calls", sa.Column("cache_marker", sa.String(length=2), nullable=True))
    op.add_column("llm_calls", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))
    # Desde a fase 1 a chamada usa effort medium, max_tokens 16000 e cache de 5 min. O custo
    # das linhas antigas é calculado na leitura, a partir do usage (quotas.row_cost).
    op.execute("UPDATE llm_calls SET effort = 'medium', max_tokens = 16000, cache_marker = '5m'")

    # Import que já foi adiado por falta de orçamento: a chamada dele é `deferred`. Nos adiados
    # agora, o updated_at (a última mudança foi o adiamento); os que já voltaram à fila não têm
    # como ser identificados.
    op.add_column("imports", sa.Column("deferred_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE imports SET deferred_at = updated_at WHERE status = 'deferred'")


def downgrade() -> None:
    op.drop_column("imports", "deferred_at")
    # Reservas que nunca terminaram não têm usage: sem a coluna de custo, deixariam de contar.
    # Sem `purpose`, as chamadas do eval passariam a contar no orçamento de produção e no limite
    # de tentativas do vídeo (uma recusa do Haiku no eval bloquearia o vídeo em produção).
    op.execute("DELETE FROM llm_calls WHERE error_code = 'llm_in_progress' OR purpose = 'eval'")
    op.drop_index("ix_llm_calls_started_at", table_name="llm_calls")
    op.drop_constraint(op.f("ck_llm_calls_llm_purpose"), "llm_calls", type_="check")
    for column in (
        "cost_usd",
        "cache_marker",
        "request_id",
        "stop_reason",
        "max_tokens",
        "effort",
        "batch_id",
        "latency_ms",
        "started_at",
        "purpose",
    ):
        op.drop_column("llm_calls", column)
