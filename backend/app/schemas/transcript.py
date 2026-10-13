from enum import StrEnum
from typing import TypedDict


class TranscriptSource(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"
    WHISPER = "whisper"


class Segment(TypedDict):
    start: float
    end: float
    text: str
