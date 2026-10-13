"""Transcrição do vídeo: legenda manual → legenda automática → faster-whisper local."""

import logging
import threading
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from yt_dlp.utils import YoutubeDLError

from app.config import get_settings
from app.errors import TranscriptionFailedError
from app.schemas.transcript import Segment, TranscriptSource
from app.services import youtube
from app.services.threads import run_cancellable
from app.services.youtube import SubtitleTrack, VideoMetadata

if TYPE_CHECKING:
    import numpy as np
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

MIN_USEFUL_WORDS = 20
MIN_USEFUL_WORDS_SHORT_VIDEO = 5
MAX_SUBTITLE_ATTEMPTS = 4

# Segmentos do whisper com alta chance de não serem fala (música, ruído) costumam ser
# alucinações ("Obrigado por assistir", "Legendas pela comunidade...").
_NO_SPEECH_PROB = 0.6
_LOW_AVG_LOGPROB = -1.0

# O faster-whisper calcula as features (mel) do áudio inteiro de uma vez: a memória cresce com a
# duração (~50 MB por minuto; 60 min passavam de 3 GB). Em blocos de até 10 min o pico fica
# limitado (~1,5 GB com o "small") seja qual for a duração do vídeo. O corte é no trecho mais
# silencioso dos últimos 30 s do bloco, para não partir uma palavra ao meio.
SAMPLE_RATE = 16_000
WHISPER_CHUNK_S = 600
_CHUNK_SEARCH_S = 30
_CHUNK_MIN_TAIL_S = 60
_QUIET_FRAME_S = 0.1


@dataclass(frozen=True, slots=True)
class Transcript:
    segments: list[Segment]
    source: TranscriptSource

    @property
    def word_count(self) -> int:
        return word_count(self.segments)


def word_count(segments: list[Segment] | None) -> int:
    return sum(len(seg["text"].split()) for seg in segments or [])


def min_useful_words(duration_s: int) -> int:
    """Palavras mínimas para considerar que há fala; Shorts de receita falam pouco."""
    return max(MIN_USEFUL_WORDS_SHORT_VIDEO, min(MIN_USEFUL_WORDS, duration_s // 6))


def is_useful_transcript(segments: list[Segment] | None, duration_s: int) -> bool:
    """False quando não há fala suficiente; o pipeline então se apoia na descrição."""
    return word_count(segments) >= min_useful_words(duration_s)


async def transcribe(meta: VideoMetadata) -> Transcript:
    """Retorna a melhor transcrição disponível; pode vir vazia (ver `is_useful_transcript`)."""
    transcript = await transcribe_from_subtitles(meta.subtitles, meta.language, meta.duration_s)
    if transcript is not None:
        return transcript

    logger.info("vídeo %s sem legenda com texto; transcrevendo com whisper", meta.youtube_id)
    return await transcribe_with_whisper(meta.youtube_id, meta.language)


async def transcribe_with_whisper(youtube_id: str, language: str | None) -> Transcript:
    """Baixa o áudio para um diretório temporário, transcreve localmente e apaga o áudio."""
    async with youtube.downloaded_audio(youtube_id) as audio_path:
        try:
            segments = await run_cancellable(partial(whisper_transcribe, audio_path, language))
        except Exception as exc:
            raise TranscriptionFailedError(detail=f"whisper: {type(exc).__name__}: {exc}") from exc
    return Transcript(segments, TranscriptSource.WHISPER)


async def transcribe_from_subtitles(
    tracks: list[SubtitleTrack], video_language: str | None, duration_s: int
) -> Transcript | None:
    """Primeira legenda (na ordem de preferência) com fala suficiente.

    Se nenhuma tiver, fica com a de mais palavras: legenda curta num vídeo curto é a fala real,
    e o whisper não faria melhor. Só devolve None (→ whisper) quando nenhuma faixa tem texto.
    """
    fallback: Transcript | None = None
    candidates = youtube.rank_subtitle_tracks(tracks, video_language)
    for track in candidates[:MAX_SUBTITLE_ATTEMPTS]:
        try:
            segments = await youtube.download_subtitle(track)
        except (YoutubeDLError, ValueError) as exc:
            # Faixas traduzidas costumam receber 429; tenta a próxima da lista.
            logger.warning("falha ao baixar legenda %s (%s): %s", track.lang, track.kind, exc)
            continue
        source = TranscriptSource.MANUAL if track.kind == "manual" else TranscriptSource.AUTO
        if is_useful_transcript(segments, duration_s):
            logger.info("legenda %s %s: %d segmentos", track.kind, track.lang, len(segments))
            return Transcript(segments, source)
        logger.info("legenda %s %s com pouca fala", track.kind, track.lang)
        if segments and (fallback is None or word_count(segments) > fallback.word_count):
            fallback = Transcript(segments, source)
    return fallback


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
                    # Um worker interno por job simultâneo: sem isso as chamadas se enfileiram.
                    num_workers=settings.whisper_max_jobs,
                )
    return _whisper_model


def load_audio(audio_path: Path) -> "np.ndarray":
    """Áudio mono em float32 a 16 kHz (~230 MB para 60 min)."""
    from faster_whisper import decode_audio

    return decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)


def chunk_bounds(audio: "np.ndarray", sample_rate: int = SAMPLE_RATE) -> list[tuple[int, int]]:
    """Intervalos [início, fim) em amostras, de até WHISPER_CHUNK_S cada, cortados no silêncio.

    O último bloco absorve uma sobra curta (< _CHUNK_MIN_TAIL_S) em vez de virar um bloco à parte.
    """
    import numpy as np

    total = len(audio)
    chunk = WHISPER_CHUNK_S * sample_rate
    search = _CHUNK_SEARCH_S * sample_rate
    frame = max(1, int(_QUIET_FRAME_S * sample_rate))
    bounds: list[tuple[int, int]] = []
    start = 0
    while start < total:
        nominal_end = start + chunk
        if total - nominal_end < _CHUNK_MIN_TAIL_S * sample_rate:
            bounds.append((start, total))
            break
        window = audio[nominal_end - search : nominal_end]
        frames = len(window) // frame
        energy = np.square(window[: frames * frame].reshape(frames, frame)).mean(axis=1)
        end = nominal_end - search + int(np.argmin(energy)) * frame + frame // 2
        bounds.append((start, end))
        start = end
    return bounds


def whisper_transcribe(
    audio_path: Path, language: str | None = None, cancel: threading.Event | None = None
) -> list[Segment]:
    """Transcreve o áudio em blocos; para entre um segmento e outro se `cancel` for marcado."""
    model = get_whisper_model()
    audio = load_audio(audio_path)
    language_hint = language.split("-")[0].lower() if language else None
    segments: list[Segment] = []
    speech_s = 0.0
    for start, end in chunk_bounds(audio):
        if cancel is not None and cancel.is_set():
            break
        offset = start / SAMPLE_RATE
        raw_segments, info = model.transcribe(
            audio[start:end],
            language=language_hint,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        if language_hint is None:
            # O idioma detectado no primeiro bloco vale para os outros (um bloco só de música
            # no meio do vídeo não troca o idioma da transcrição).
            language_hint = info.language
            logger.info(
                "whisper: idioma %s (%.0f%%)", info.language, info.language_probability * 100
            )
        speech_s += info.duration_after_vad or 0
        # Os segmentos são gerados sob demanda: é aqui que o trabalho pesado acontece.
        for seg in raw_segments:
            if cancel is not None and cancel.is_set():
                break
            if not (seg.no_speech_prob > _NO_SPEECH_PROB and seg.avg_logprob < _LOW_AVG_LOGPROB):
                segments.append(
                    Segment(start=seg.start + offset, end=seg.end + offset, text=seg.text)
                )
    logger.info(
        "whisper: %.0fs de áudio, %.0fs de fala, %d segmentos",
        len(audio) / SAMPLE_RATE,
        speech_s,
        len(segments),
    )
    return youtube.finalize_segments(segments)
