from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError

from app.schemas.transcript import Segment, TranscriptSource
from app.services import transcription, youtube
from app.services.youtube import SubtitleTrack, VideoMetadata

USEFUL = [Segment(start=float(i), end=i + 1.0, text="bata os ovos com açúcar") for i in range(6)]
USELESS = [Segment(start=0.0, end=3.0, text="obrigado")]

META = VideoMetadata(
    youtube_id="abcdefghijk",
    title="Bolo",
    channel=None,
    duration_s=120,
    thumbnail_url=None,
    description="",
    embeddable=True,
    availability="public",
    live_status="not_live",
    age_limit=0,
    language="pt",
    subtitles=[
        SubtitleTrack("pt-orig", "auto", False, {"json3": "https://x/auto-pt"}),
        SubtitleTrack("en", "manual", False, {"json3": "https://x/manual-en"}),
        SubtitleTrack("pt-BR", "manual", False, {"vtt": "https://x/manual-pt"}),
    ],
)


def _fake_download(results: dict[str, list[Segment] | Exception], calls: list[str]):
    async def download(track: SubtitleTrack) -> list[Segment]:
        calls.append(f"{track.kind}:{track.lang}")
        result = results[track.lang]
        if isinstance(result, Exception):
            raise result
        return result

    return download


def _forbid_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> list[Segment]:
        raise AssertionError("whisper não deveria rodar")

    monkeypatch.setattr(transcription, "whisper_transcribe", fail)


async def test_uses_best_subtitle(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(youtube, "download_subtitle", _fake_download({"pt-BR": USEFUL}, calls))
    _forbid_whisper(monkeypatch)

    transcript = await transcription.transcribe(META)

    assert calls == ["manual:pt-BR"]
    assert transcript.source == TranscriptSource.MANUAL
    assert transcript.segments == USEFUL
    assert transcript.is_useful


async def test_skips_failed_and_useless_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    results: dict[str, list[Segment] | Exception] = {
        "pt-BR": DownloadError("HTTP Error 429: Too Many Requests"),
        "en": USELESS,
        "pt-orig": USEFUL,
    }
    monkeypatch.setattr(youtube, "download_subtitle", _fake_download(results, calls))
    _forbid_whisper(monkeypatch)

    transcript = await transcription.transcribe(META)

    assert calls == ["manual:pt-BR", "manual:en", "auto:pt-orig"]
    assert transcript.source == TranscriptSource.AUTO


async def test_falls_back_to_whisper_and_cleans_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    audio = tmp_path / "audio.m4a"
    events: list[str] = []

    @asynccontextmanager
    async def fake_audio(youtube_id: str) -> AsyncIterator[Path]:
        events.append(f"download:{youtube_id}")
        yield audio
        events.append("cleanup")

    def fake_whisper(path: Path, language: str | None) -> list[Segment]:
        events.append(f"whisper:{path.name}:{language}")
        return USEFUL

    monkeypatch.setattr(youtube, "downloaded_audio", fake_audio)
    monkeypatch.setattr(transcription, "whisper_transcribe", fake_whisper)

    transcript = await transcription.transcribe(replace(META, subtitles=[]))

    assert events == ["download:abcdefghijk", "whisper:audio.m4a:pt", "cleanup"]
    assert transcript.source == TranscriptSource.WHISPER
    assert transcript.is_useful


async def test_whisper_without_speech_is_not_useful(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_audio(youtube_id: str) -> AsyncIterator[Path]:
        yield Path("/tmp/inexistente.m4a")

    monkeypatch.setattr(youtube, "downloaded_audio", fake_audio)
    monkeypatch.setattr(transcription, "whisper_transcribe", lambda path, language: [])

    transcript = await transcription.transcribe(replace(META, subtitles=[]))

    assert transcript.segments == []
    assert not transcript.is_useful


async def test_downloaded_audio_removes_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Path] = []

    def fake_download(youtube_id: str, directory: Path) -> Path:
        path = directory / f"{youtube_id}.m4a"
        path.write_bytes(b"audio")
        created.append(path)
        return path

    monkeypatch.setattr(youtube, "_download_audio", fake_download)

    async with youtube.downloaded_audio("abcdefghijk") as path:
        assert path.read_bytes() == b"audio"

    assert not created[0].exists()
    assert not created[0].parent.exists()


async def test_downloaded_audio_removes_directory_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Path] = []

    def fake_download(youtube_id: str, directory: Path) -> Path:
        path = directory / "a.m4a"
        path.write_bytes(b"audio")
        created.append(path)
        return path

    monkeypatch.setattr(youtube, "_download_audio", fake_download)

    with pytest.raises(RuntimeError):
        async with youtube.downloaded_audio("abcdefghijk"):
            raise RuntimeError("falhou no meio")

    assert not created[0].parent.exists()
