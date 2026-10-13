import asyncio
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from yt_dlp.utils import DownloadError

from app.errors import TranscriptionFailedError
from app.schemas.transcript import Segment, TranscriptSource
from app.services import transcription, youtube
from app.services.threads import run_cancellable
from app.services.transcription import is_useful_transcript
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
    assert is_useful_transcript(transcript.segments, META.duration_s)


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

    def fake_whisper(path: Path, language: str | None, cancel: threading.Event) -> list[Segment]:
        events.append(f"whisper:{path.name}:{language}")
        return USEFUL

    monkeypatch.setattr(youtube, "downloaded_audio", fake_audio)
    monkeypatch.setattr(transcription, "whisper_transcribe", fake_whisper)

    transcript = await transcription.transcribe(replace(META, subtitles=[]))

    assert events == ["download:abcdefghijk", "whisper:audio.m4a:pt", "cleanup"]
    assert transcript.source == TranscriptSource.WHISPER
    assert is_useful_transcript(transcript.segments, META.duration_s)


async def test_whisper_without_speech_is_not_useful(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_audio(youtube_id: str) -> AsyncIterator[Path]:
        yield Path("/tmp/inexistente.m4a")

    monkeypatch.setattr(youtube, "downloaded_audio", fake_audio)
    monkeypatch.setattr(transcription, "whisper_transcribe", lambda path, language, cancel: [])

    transcript = await transcription.transcribe(replace(META, subtitles=[]))

    assert transcript.segments == []
    assert not is_useful_transcript(transcript.segments, META.duration_s)


async def test_downloaded_audio_removes_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Path] = []

    def fake_download(youtube_id: str, directory: Path, cancel: threading.Event) -> Path:
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

    def fake_download(youtube_id: str, directory: Path, cancel: threading.Event) -> Path:
        path = directory / "a.m4a"
        path.write_bytes(b"audio")
        created.append(path)
        return path

    monkeypatch.setattr(youtube, "_download_audio", fake_download)

    with pytest.raises(RuntimeError):
        async with youtube.downloaded_audio("abcdefghijk"):
            raise RuntimeError("falhou no meio")

    assert not created[0].parent.exists()


SHORT_SPEECH = [
    Segment(
        start=0.0,
        end=20.0,
        text="misture farinha ovos e leite asse por vinte minutos a cento e oitenta graus e sirva",
    )
]


async def test_short_subtitle_is_kept_instead_of_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    results: dict[str, list[Segment] | Exception] = {"pt-BR": SHORT_SPEECH, "en": [], "pt-orig": []}
    monkeypatch.setattr(youtube, "download_subtitle", _fake_download(results, calls))
    _forbid_whisper(monkeypatch)

    transcript = await transcription.transcribe(replace(META, duration_s=40))

    assert calls == ["manual:pt-BR"]  # num vídeo de 40 s, 17 palavras já são fala útil
    assert transcript.segments == SHORT_SPEECH
    assert transcript.source == TranscriptSource.MANUAL


async def test_subtitle_with_little_text_beats_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    results: dict[str, list[Segment] | Exception] = {
        "pt-BR": USELESS,
        "en": [],
        "pt-orig": SHORT_SPEECH,
    }
    monkeypatch.setattr(youtube, "download_subtitle", _fake_download(results, calls))
    _forbid_whisper(monkeypatch)

    transcript = await transcription.transcribe(replace(META, duration_s=600))

    assert calls == ["manual:pt-BR", "manual:en", "auto:pt-orig"]
    assert transcript.segments == SHORT_SPEECH  # a faixa com mais palavras
    assert transcript.source == TranscriptSource.AUTO
    assert not is_useful_transcript(transcript.segments, 600)


@pytest.mark.parametrize(
    ("duration_s", "words", "useful"),
    [(40, 6, True), (40, 4, False), (90, 15, True), (600, 19, False), (600, 20, True)],
)
def test_useful_transcript_threshold_scales_with_duration(
    duration_s: int, words: int, useful: bool
) -> None:
    segments = [Segment(start=0.0, end=1.0, text=" ".join(["ovo"] * words))]
    assert is_useful_transcript(segments, duration_s) is useful


async def test_whisper_failure_becomes_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_audio(youtube_id: str) -> AsyncIterator[Path]:
        yield Path("/tmp/inexistente.m4a")

    def broken(path: Path, language: str | None, cancel: threading.Event) -> list[Segment]:
        raise RuntimeError("CUDA failed / modelo não baixou")

    monkeypatch.setattr(youtube, "downloaded_audio", fake_audio)
    monkeypatch.setattr(transcription, "whisper_transcribe", broken)

    with pytest.raises(TranscriptionFailedError) as exc_info:
        await transcription.transcribe(replace(META, subtitles=[]))
    assert exc_info.value.code == "transcription_failed"
    assert "RuntimeError" in (exc_info.value.detail or "")


@dataclass
class _WhisperSegment:
    start: float
    end: float
    text: str
    no_speech_prob: float = 0.01
    avg_logprob: float = -0.2


@dataclass
class _WhisperInfo:
    language: str = "pt"
    language_probability: float = 0.99
    duration_after_vad: float = 10.0


class _FakeWhisperModel:
    def __init__(self, segments: list[_WhisperSegment]) -> None:
        self.segments = segments
        self.kwargs: dict[str, Any] = {}
        self.yielded = 0

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[Any, _WhisperInfo]:
        self.kwargs = kwargs

        def generate() -> Any:
            for seg in self.segments:
                self.yielded += 1
                yield seg

        return generate(), _WhisperInfo()


def test_whisper_transcribe_filters_hallucinations(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _FakeWhisperModel(
        [
            _WhisperSegment(0.0, 2.0, " Bata os ovos."),
            _WhisperSegment(2.0, 4.0, " Obrigado por assistir!", 0.9, -1.5),
            _WhisperSegment(
                4.0, 6.0, " Junte a farinha.", 0.9, -0.3
            ),  # baixa certeza só de um lado
        ]
    )
    monkeypatch.setattr(transcription, "get_whisper_model", lambda: model)

    segments = transcription.whisper_transcribe(Path("/tmp/a.m4a"), "pt-BR")

    assert [s["text"] for s in segments] == ["Bata os ovos.", "Junte a farinha."]
    assert model.kwargs["language"] == "pt"
    assert model.kwargs["vad_filter"] is True


def test_whisper_transcribe_stops_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _FakeWhisperModel([_WhisperSegment(float(i), i + 1.0, "mexa") for i in range(100)])
    monkeypatch.setattr(transcription, "get_whisper_model", lambda: model)
    cancel = threading.Event()
    cancel.set()

    assert transcription.whisper_transcribe(Path("/tmp/a.m4a"), None, cancel) == []
    assert model.yielded == 1


async def test_run_cancellable_waits_for_thread_to_stop() -> None:
    finished = threading.Event()

    def work(cancel: threading.Event) -> str:
        while not cancel.wait(0.01):
            pass
        time.sleep(0.05)  # limpeza da própria thread depois do aviso
        finished.set()
        return "interrompido"

    task = asyncio.create_task(run_cancellable(work))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


async def test_cancelled_download_leaves_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    started, stopped = threading.Event(), threading.Event()
    directories: list[Path] = []

    def slow_download(youtube_id: str, directory: Path, cancel: threading.Event) -> Path:
        directories.append(directory)
        path = directory / f"{youtube_id}.m4a"
        started.set()
        while not cancel.is_set():
            # Como o yt-dlp: grava em pedaços e recria o diretório se ele sumir.
            directory.mkdir(exist_ok=True)
            with path.open("ab") as file:
                file.write(b"x")
            time.sleep(0.01)
        stopped.set()
        return path

    monkeypatch.setattr(youtube, "_download_audio", slow_download)

    async def use_audio() -> None:
        async with youtube.downloaded_audio("abcdefghijk"):
            raise AssertionError("o download não deveria terminar")

    task = asyncio.create_task(use_audio())
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    await asyncio.sleep(0.1)
    assert not directories[0].exists()
