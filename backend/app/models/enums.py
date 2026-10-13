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


ACTIVE_IMPORT_STATUSES = frozenset(
    {
        ImportStatus.PENDING,
        ImportStatus.FETCHING,
        ImportStatus.TRANSCRIBING,
        ImportStatus.GENERATING,
    }
)
