from dataclasses import replace

import pytest

from app.errors import (
    LiveVideoError,
    NotEmbeddableError,
    PipelineError,
    VideoTooLongError,
    VideoUnavailableError,
)
from app.services.youtube import VideoMetadata, validate_metadata

META = VideoMetadata(
    youtube_id="abcdefghijk",
    title="Bolo de cenoura",
    channel="Receitas",
    duration_s=600,
    thumbnail_url=None,
    description="",
    embeddable=True,
    availability="public",
    live_status="not_live",
    age_limit=0,
    language="pt",
    subtitles=[],
)


@pytest.mark.parametrize("availability", ["public", "unlisted", None])
def test_valid_video_passes(availability: str | None) -> None:
    validate_metadata(replace(META, availability=availability), max_duration_s=3600)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"availability": "private"}, VideoUnavailableError),
        ({"availability": "subscriber_only"}, VideoUnavailableError),
        ({"availability": "needs_auth"}, VideoUnavailableError),
        ({"embeddable": False}, NotEmbeddableError),
        ({"age_limit": 18}, NotEmbeddableError),
        ({"live_status": "is_live"}, LiveVideoError),
        ({"live_status": "is_upcoming"}, LiveVideoError),
        ({"duration_s": 3601}, VideoTooLongError),
        ({"duration_s": 0}, VideoUnavailableError),
    ],
)
def test_invalid_video_raises(changes: dict[str, object], error: type[PipelineError]) -> None:
    with pytest.raises(error):
        validate_metadata(replace(META, **changes), max_duration_s=3600)  # type: ignore[arg-type]


def test_too_long_message_mentions_limit() -> None:
    with pytest.raises(VideoTooLongError) as exc_info:
        validate_metadata(replace(META, duration_s=5000), max_duration_s=3600)
    assert "60 minutos" in exc_info.value.message


def test_was_live_video_is_accepted() -> None:
    validate_metadata(replace(META, live_status="was_live"), max_duration_s=3600)
