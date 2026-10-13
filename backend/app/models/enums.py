from enum import StrEnum


class UserPlan(StrEnum):
    FREE = "free"


class Difficulty(StrEnum):
    EASY = "fácil"
    MEDIUM = "média"
    HARD = "difícil"


class ImportStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    TRANSCRIBING = "transcribing"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"
    # Orçamento diário do Claude esgotado: volta para a fila no dia seguinte (cron do worker).
    DEFERRED = "deferred"


ACTIVE_IMPORT_STATUSES = frozenset(
    {
        ImportStatus.PENDING,
        ImportStatus.FETCHING,
        ImportStatus.TRANSCRIBING,
        ImportStatus.GENERATING,
    }
)

# Ainda sem resultado: em processamento ou adiado. Contam na cota do dia enquanto estão assim.
UNFINISHED_IMPORT_STATUSES = ACTIVE_IMPORT_STATUSES | {ImportStatus.DEFERRED}
