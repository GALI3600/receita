"""Transcrição do vídeo: legenda manual → legenda automática → faster-whisper local."""

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yt_dlp.utils import YoutubeDLError

from app.config import get_settings
from app.schemas.transcript import Segment, TranscriptSource
from app.services import youtube
from app.services.youtube import SubtitleTrack, VideoMetadata

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

MIN_USEFUL_WORDS = 20
MAX_SUBTITLE_ATTEMPTS = 4

# Segmentos do whisper com alta chance de não serem fala (música, ruído) costumam ser
# alucinações ("Obrigado por assistir", "Legendas pela comunidade...").
_NO_SPEECH_PROB = 0.6
_LOW_AVG_LOGPROB = -1.0


@dataclass(frozen=True, slots=True)
class Transcript:
    segments: list[Segment]
    source: TranscriptSource

    @property
    def word_count(self) -> int:
        return word_count(self.segments)

    @property
    def is_useful(self) -> bool:
        """False quando não há fala suficiente; o pipeline então se apoia na descrição."""
        return is_useful_transcript(self.segments)


def word_count(segments: list[Segment] | None) -> int:
    return sum(len(seg["text"].split()) for seg in segments or [])


def is_useful_transcript(segments: list[Segment] | None) -> bool:
    return word_count(segments) >= MIN_USEFUL_WORDS


async def transcribe(meta: VideoMetadata) -> Transcript:
    """Retorna a melhor transcrição disponível; pode vir vazia (ver `Transcript.is_useful`)."""
    transcript = await transcribe_from_subtitles(meta.subtitles, meta.language)
    if transcript is not None:
        return transcript

    logger.info("vídeo %s sem legenda utilizável; transcrevendo com whisper", meta.youtube_id)
    async with youtube.downloaded_audio(meta.youtube_id) as audio_path:
        segments = await asyncio.to_thread(whisper_transcribe, audio_path, meta.language)
    return Transcript(segments, TranscriptSource.WHISPER)


async def transcribe_from_subtitles(
    tracks: list[SubtitleTrack], video_language: str | None
) -> Transcript | None:
    candidates = youtube.rank_subtitle_tracks(tracks, video_language)
    for track in candidates[:MAX_SUBTITLE_ATTEMPTS]:
        try:
            segments = await youtube.download_subtitle(track)
        except (YoutubeDLError, ValueError) as exc:
            # Faixas traduzidas costumam receber 429; tenta a próxima da lista.
            logger.warning("falha ao baixar legenda %s (%s): %s", track.lang, track.kind, exc)
            continue
        if is_useful_transcript(segments):
            source = TranscriptSource.MANUAL if track.kind == "manual" else TranscriptSource.AUTO
            logger.info("legenda %s %s: %d segmentos", track.kind, track.lang, len(segments))
            return Transcript(segments, source)
        logger.info("legenda %s %s sem conteúdo útil", track.kind, track.lang)
    return None


# --- Whisper --------------------------------------------------------------------------------

_whisper_model: "WhisperModel | None" = None
_whisper_lock = threading.Lock()


def get_whisper_model() -> "WhisperModel":
    """Carrega o modelo uma única vez por processo (é pesado: centenas de MB)."""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                settings = get_settings()
                logger.info(
                    "carregando whisper %s (%s, %s)",
                    settings.whisper_model,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                )
                _whisper_model = WhisperModel(
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
    return _whisper_model


def whisper_transcribe(audio_path: Path, language: str | None = None) -> list[Segment]:
    model = get_whisper_model()
    language_hint = language.split("-")[0].lower() if language else None
    raw_segments, info = model.transcribe(
        str(audio_path),
        language=language_hint,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    logger.info(
        "whisper: idioma %s (%.0f%%), %.0fs de fala",
        info.language,
        info.language_probability * 100,
        info.duration_after_vad or 0,
    )
    segments = [
        Segment(start=seg.start, end=seg.end, text=seg.text)
        for seg in raw_segments
        if not (seg.no_speech_prob > _NO_SPEECH_PROB and seg.avg_logprob < _LOW_AVG_LOGPROB)
    ]
    return youtube.finalize_segments(segments)
