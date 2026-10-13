"""Acesso ao YouTube via yt-dlp: URL → id, metadados, legendas e áudio temporário.

A API do yt-dlp é bloqueante, então toda chamada de rede roda em `asyncio.to_thread`.
"""

import asyncio
import html
import json
import re
import shutil
import tempfile
import threading
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Literal, NoReturn
from urllib.parse import parse_qs, urlsplit

import yt_dlp
from yt_dlp.networking import Request
from yt_dlp.utils import DownloadCancelled, DownloadError

from app.config import get_settings
from app.errors import (
    InvalidUrlError,
    LiveVideoError,
    NotEmbeddableError,
    VideoTooLongError,
    VideoUnavailableError,
    YoutubeBlockedError,
)
from app.schemas.transcript import Segment
from app.services.threads import run_cancellable

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)
_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_ID_PATH_PREFIXES = frozenset({"shorts", "embed", "v", "e", "live"})
# Tem 11 caracteres como um id, mas é o embed de playlist (embed/videoseries?list=...).
_NOT_VIDEO_IDS = frozenset({"videoseries"})

_YDL_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "noplaylist": True,
    "skip_download": True,
    "socket_timeout": 30,
}


@contextmanager
def _youtube_dl(extra: dict[str, Any] | None = None) -> Iterator[yt_dlp.YoutubeDL]:
    """`YoutubeDL` com as opções base e, com `YTDLP_COOKIES_FILE`, os cookies de uma conta.

    O yt-dlp regrava o arquivo de cookies ao fechar: cada uso recebe uma cópia temporária,
    apagada no fim, para o original poder ficar montado só para leitura e jobs simultâneos não
    escreverem no mesmo arquivo.
    """
    opts = {**_YDL_BASE_OPTS, **(extra or {})}
    cookies_file = get_settings().ytdlp_cookies_file
    with ExitStack() as stack:
        if cookies_file:
            directory = stack.enter_context(tempfile.TemporaryDirectory(prefix="receita-ck-"))
            copy = Path(directory) / "cookies.txt"
            shutil.copyfile(cookies_file, copy)
            opts["cookiefile"] = str(copy)
        yield stack.enter_context(yt_dlp.YoutubeDL(opts))


def extract_youtube_id(url: str) -> str:
    """Extrai o id de 11 caracteres de qualquer forma de link de vídeo do YouTube.

    Aceita watch?v=, youtu.be/, shorts/, embed/, live/, m./music./nocookie, com ou sem
    esquema e com parâmetros extras. Rejeita playlists sem vídeo, canais e domínios falsos.
    """
    raw = url.strip()
    if not raw or any(ch.isspace() for ch in raw):
        raise InvalidUrlError(detail=f"url vazia ou com espaços: {url!r}")
    if "://" not in raw:
        raw = f"https://{raw}"

    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise InvalidUrlError(detail=str(exc)) from exc

    if parts.scheme not in ("http", "https") or parts.username or parts.password:
        raise InvalidUrlError(detail=f"esquema ou credenciais inválidos: {url!r}")

    segments = [s for s in parts.path.split("/") if s]
    candidate: str | None = None
    if host in _SHORT_HOSTS:
        candidate = segments[0] if len(segments) == 1 else None
    elif host in _YOUTUBE_HOSTS:
        if segments == ["watch"]:
            values = parse_qs(parts.query).get("v", [])
            candidate = values[0] if len(values) == 1 else None
        elif len(segments) == 2 and segments[0] in _ID_PATH_PREFIXES:
            candidate = segments[1]

    if candidate is None or candidate in _NOT_VIDEO_IDS or not _VIDEO_ID_RE.fullmatch(candidate):
        raise InvalidUrlError(detail=f"não é link de vídeo do YouTube: {url!r}")
    return candidate


def watch_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"


# --- Metadados ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    lang: str
    kind: Literal["manual", "auto"]
    translated: bool
    formats: dict[str, str] = field(repr=False)
    """Extensão (json3, vtt) → URL. Só formatos baixáveis com um GET simples."""

    @property
    def base_lang(self) -> str:
        return self.lang.split("-")[0].lower()

    @property
    def is_original(self) -> bool:
        return self.lang.endswith("-orig")


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    youtube_id: str
    title: str
    channel: str | None
    duration_s: int
    thumbnail_url: str | None
    description: str
    embeddable: bool
    availability: str | None
    live_status: str | None
    age_limit: int
    language: str | None
    subtitles: list[SubtitleTrack]


_SUPPORTED_SUB_EXTS = ("json3", "vtt")


def _parse_tracks(
    raw: dict[str, list[dict[str, Any]]] | None, kind: Literal["manual", "auto"]
) -> list[SubtitleTrack]:
    tracks: list[SubtitleTrack] = []
    for lang, entries in (raw or {}).items():
        if lang == "live_chat":
            continue
        formats: dict[str, str] = {}
        translated = False
        for entry in entries:
            ext, url = entry.get("ext"), entry.get("url")
            protocol = entry.get("protocol") or ""
            if ext not in _SUPPORTED_SUB_EXTS or not url or protocol.startswith("m3u8"):
                continue
            formats.setdefault(ext, url)
            translated = translated or "tlang" in parse_qs(urlsplit(url).query)
        if formats:
            tracks.append(SubtitleTrack(lang, kind, translated, formats))
    return tracks


def metadata_from_info(info: dict[str, Any]) -> VideoMetadata:
    return VideoMetadata(
        youtube_id=info["id"],
        title=info.get("title") or "",
        channel=info.get("channel") or info.get("uploader"),
        duration_s=int(info.get("duration") or 0),
        thumbnail_url=info.get("thumbnail"),
        description=info.get("description") or "",
        embeddable=bool(info.get("playable_in_embed", True)),
        availability=info.get("availability"),
        live_status=info.get("live_status"),
        age_limit=int(info.get("age_limit") or 0),
        language=info.get("language"),
        subtitles=_parse_tracks(info.get("subtitles"), "manual")
        + _parse_tracks(info.get("automatic_captions"), "auto"),
    )


_AGE_RESTRICTED_MESSAGE = "Esse vídeo tem restrição de idade e não pode ser exibido no livro."


def _raise_for_download_error(exc: DownloadError) -> NoReturn:
    message = str(exc)
    lowered = message.lower()
    if "not a bot" in lowered or "http error 429" in lowered:
        raise YoutubeBlockedError(detail=message) from exc
    if "confirm your age" in lowered or "age-restricted" in lowered:
        raise NotEmbeddableError(_AGE_RESTRICTED_MESSAGE, detail=message) from exc
    if "live event will begin" in lowered or "premieres in" in lowered:
        raise LiveVideoError(detail=message) from exc
    raise VideoUnavailableError(detail=message) from exc


def _extract_info(youtube_id: str) -> dict[str, Any]:
    with _youtube_dl() as ydl:
        try:
            info = ydl.extract_info(watch_url(youtube_id), download=False)
        except DownloadError as exc:
            _raise_for_download_error(exc)
        if not info:
            raise VideoUnavailableError(detail="yt-dlp não retornou metadados")
        return ydl.sanitize_info(info)


async def fetch_metadata(youtube_id: str) -> VideoMetadata:
    info = await asyncio.to_thread(_extract_info, youtube_id)
    return metadata_from_info(info)


def validate_metadata(meta: VideoMetadata, *, max_duration_s: int | None = None) -> None:
    if max_duration_s is None:
        max_duration_s = get_settings().max_video_duration_min * 60

    if meta.availability not in (None, "public", "unlisted"):
        raise VideoUnavailableError(detail=f"availability={meta.availability}")
    if meta.live_status in ("is_live", "is_upcoming", "post_live"):
        raise LiveVideoError(detail=f"live_status={meta.live_status}")
    if not meta.embeddable:
        raise NotEmbeddableError()
    if meta.age_limit >= 18:
        raise NotEmbeddableError(_AGE_RESTRICTED_MESSAGE, detail=f"age_limit={meta.age_limit}")
    if meta.duration_s <= 0:
        raise VideoUnavailableError(detail="duração desconhecida")
    if meta.duration_s > max_duration_s:
        raise VideoTooLongError(
            f"Esse vídeo tem mais de {max_duration_s // 60} minutos, que é o limite para importar.",
            detail=f"duration_s={meta.duration_s}",
        )


# --- Legendas -------------------------------------------------------------------------------

_LANG_PRIORITY = {"pt": 0, "en": 1}
_REGION_PRIORITY = {"pt-br": 0, "pt": 1, "en": 0, "en-us": 1, "en-gb": 2}


def rank_subtitle_tracks(
    tracks: Iterable[SubtitleTrack], video_language: str | None = None
) -> list[SubtitleTrack]:
    """Ordena as legendas da melhor para a pior, descartando as que não servem.

    Ordem: manual pt > manual en > auto pt > auto en > manual no idioma do vídeo >
    auto no idioma do vídeo > auto traduzida para pt > auto traduzida para en.
    Dentro de cada grupo: faixa original (-orig) e pt-BR/en primeiro.
    """
    video_base = (video_language or "").split("-")[0].lower() or None
    ranked: list[tuple[tuple[int, int, int, str], SubtitleTrack]] = []

    for track in tracks:
        lang_rank = _LANG_PRIORITY.get(track.base_lang)
        in_video_lang = track.base_lang == video_base
        if track.kind == "manual":
            if lang_rank is not None:
                tier = lang_rank
            elif in_video_lang:
                tier = 4
            else:
                continue
        elif track.translated:
            if lang_rank is None:
                continue
            tier = 6 + lang_rank
        elif lang_rank is not None:
            tier = 2 + lang_rank
        elif in_video_lang:
            tier = 5
        else:
            continue

        lang_key = track.lang.lower().removesuffix("-orig")
        ranked.append(
            (
                (
                    tier,
                    0 if track.is_original else 1,
                    _REGION_PRIORITY.get(lang_key, 9),
                    track.lang,
                ),
                track,
            )
        )

    ranked.sort(key=lambda item: item[0])
    return [track for _, track in ranked]


_TAG_RE = re.compile(r"<[^>]*>")
_ANNOTATION_RE = re.compile(r"\[[^\]]{1,40}\]|\([^)]*(?:música|music|aplausos|risos)[^)]*\)", re.I)
_MUSIC_NOTES_RE = re.compile(r"[♪♫]+")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = html.unescape(_TAG_RE.sub("", text))
    text = _MUSIC_NOTES_RE.sub(" ", _ANNOTATION_RE.sub(" ", text))
    return _WS_RE.sub(" ", text).strip()


def finalize_segments(segments: Iterable[Segment]) -> list[Segment]:
    """Limpa o texto, descarta vazios e funde repetições consecutivas."""
    result: list[Segment] = []
    for seg in segments:
        text = clean_text(seg["text"])
        if not text:
            continue
        start = round(max(seg["start"], 0.0), 3)
        end = round(max(seg["end"], start), 3)
        if result and result[-1]["text"] == text:
            result[-1]["end"] = max(result[-1]["end"], end)
            continue
        result.append(Segment(start=start, end=end, text=text))
    return result


def parse_json3(data: str | bytes) -> list[Segment]:
    events = [
        event
        for event in json.loads(data).get("events", [])
        if event.get("segs") and "".join(s.get("utf8", "") for s in event["segs"]).strip()
    ]
    segments: list[Segment] = []
    for index, event in enumerate(events):
        start_ms = event.get("tStartMs", 0)
        end_ms = start_ms + event.get("dDurationMs", 0)
        if index + 1 < len(events):
            # Nas legendas automáticas a duração de cada linha invade a seguinte.
            end_ms = min(end_ms, events[index + 1].get("tStartMs", end_ms))
        text = "".join(s.get("utf8", "") for s in event["segs"]).replace("\n", " ")
        segments.append(Segment(start=start_ms / 1000, end=end_ms / 1000, text=text))
    return finalize_segments(segments)


_VTT_TIMING_RE = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{3})"
)


def _vtt_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def parse_vtt(data: str | bytes) -> list[Segment]:
    """Converte WebVTT em segmentos.

    As legendas automáticas em VTT repetem a linha anterior em cada cue (efeito "rolagem");
    cada linha só entra uma vez, com o tempo do cue em que apareceu pela primeira vez.
    """
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data.removeprefix("\ufeff")
    segments: list[Segment] = []
    recent: list[str] = []

    for block in re.split(r"(?:\r?\n){2,}", text):
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = _VTT_TIMING_RE.search(lines[timing_index])
        if not match:
            continue
        new_lines: list[str] = []
        for line in lines[timing_index + 1 :]:
            cleaned = clean_text(line)
            if cleaned and cleaned not in recent:
                new_lines.append(cleaned)
                recent = [*recent[-2:], cleaned]
        if new_lines:
            segments.append(
                Segment(
                    start=_vtt_seconds(match["start"]),
                    end=_vtt_seconds(match["end"]),
                    text=" ".join(new_lines),
                )
            )

    return finalize_segments(segments)


# Uma legenda json3 de 1 h fica em torno de 1 MB; o resto é abuso ou erro.
MAX_SUBTITLE_BYTES = 8 * 1024 * 1024


def _fetch_url(url: str, max_bytes: int = MAX_SUBTITLE_BYTES) -> bytes:
    with _youtube_dl() as ydl, ydl.urlopen(Request(url)) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"legenda maior que {max_bytes} bytes")
    return data


async def download_subtitle(track: SubtitleTrack) -> list[Segment]:
    """Baixa a faixa (json3, ou vtt como alternativa) e converte em segmentos limpos."""
    if "json3" in track.formats:
        data = await asyncio.to_thread(_fetch_url, track.formats["json3"])
        return parse_json3(data)
    data = await asyncio.to_thread(_fetch_url, track.formats["vtt"])
    return parse_vtt(data)


# --- Áudio ----------------------------------------------------------------------------------


def _download_audio(youtube_id: str, directory: Path, cancel: threading.Event) -> Path:
    def abort_if_cancelled(progress: dict[str, Any]) -> None:
        if cancel.is_set():
            raise DownloadCancelled("tarefa cancelada")

    opts = {
        "skip_download": False,
        # Áudio leve basta para fala; sem pós-processamento, o faster-whisper decodifica via PyAV.
        "format": "bestaudio[abr<=96]/worstaudio/bestaudio",
        "outtmpl": str(directory / "%(id)s.%(ext)s"),
        "max_filesize": 300 * 1024 * 1024,
        "progress_hooks": [abort_if_cancelled],
    }
    with _youtube_dl(opts) as ydl:
        try:
            info = ydl.extract_info(watch_url(youtube_id), download=True)
        except DownloadError as exc:
            _raise_for_download_error(exc)
    downloads = (info or {}).get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.exists():
        raise VideoUnavailableError(detail="áudio não foi baixado")
    return path


@asynccontextmanager
async def downloaded_audio(youtube_id: str) -> AsyncIterator[Path]:
    """Baixa só o áudio para um diretório temporário, apagado ao sair do bloco.

    Se a tarefa for cancelada no meio do download, o yt-dlp é interrompido e o diretório só é
    apagado depois que a thread parou (senão ela recriaria o arquivo depois da limpeza).
    """
    directory = Path(tempfile.mkdtemp(prefix="receita-audio-"))
    try:
        yield await run_cancellable(partial(_download_audio, youtube_id, directory))
    finally:
        await asyncio.to_thread(shutil.rmtree, directory, True)
