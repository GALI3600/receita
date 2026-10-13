from pathlib import Path
from typing import Any

import pytest

from app.services import youtube
from app.services.youtube import (
    SubtitleTrack,
    clean_text,
    metadata_from_info,
    parse_json3,
    parse_vtt,
    rank_subtitle_tracks,
)

EXPECTED_AUTO_TEXTS = [
    "o preparo do bolo começa",
    "preaqueça o forno a 180 graus",
    "unte a forma com manteiga",
    "até a próxima",
]


def test_parse_json3_auto_drops_annotations_and_trims_overlap(fixtures_dir: Path) -> None:
    segments = parse_json3((fixtures_dir / "auto.pt.json3").read_bytes())

    assert [s["text"] for s in segments] == EXPECTED_AUTO_TEXTS
    # A duração de cada linha automática termina onde a próxima começa.
    assert segments[0] == {"start": 4.56, "end": 6.48, "text": "o preparo do bolo começa"}
    assert segments[1]["end"] == 8.84
    assert segments[-1] == {"start": 93.0, "end": 95.0, "text": "até a próxima"}


def test_parse_json3_manual_joins_lines_unescapes_and_dedups(fixtures_dir: Path) -> None:
    segments = parse_json3((fixtures_dir / "manual.pt-BR.json3").read_text())

    assert [s["text"] for s in segments] == [
        "Hoje vamos fazer um bolo de cenoura.",
        "Bata no liquidificador 3 cenouras e 4 ovos.",
        "Junte 2 xícaras de açúcar & o óleo.",
        "Asse por 40 minutos.",
    ]
    junte = segments[2]
    assert junte["start"] == 5.284
    assert junte["end"] == 11.2  # repetição consecutiva fundida no mesmo segmento


def test_parse_vtt_auto_removes_rolling_duplicates(fixtures_dir: Path) -> None:
    segments = parse_vtt((fixtures_dir / "auto.pt.vtt").read_bytes())

    assert [s["text"] for s in segments] == EXPECTED_AUTO_TEXTS
    assert segments[0]["start"] == 4.56
    assert segments[1]["start"] == 6.48
    assert segments[-1]["start"] == 93.0
    assert all("<" not in s["text"] for s in segments)


def test_parse_vtt_manual(fixtures_dir: Path) -> None:
    segments = parse_vtt((fixtures_dir / "manual.pt-BR.vtt").read_text())

    assert segments == [
        {"start": 0.06, "end": 2.06, "text": "Hoje vamos fazer um bolo de cenoura."},
        {"start": 2.06, "end": 5.284, "text": "Bata no liquidificador 3 cenouras e 4 ovos."},
        {"start": 5.284, "end": 8.062, "text": "Junte 2 xícaras de açúcar & o óleo."},
        {"start": 3611.397, "end": 3613.731, "text": "Asse por 40 minutos."},
    ]


def test_json3_and_vtt_agree(fixtures_dir: Path) -> None:
    from_json3 = parse_json3((fixtures_dir / "auto.pt.json3").read_bytes())
    from_vtt = parse_vtt((fixtures_dir / "auto.pt.vtt").read_bytes())
    assert [s["text"] for s in from_json3] == [s["text"] for s in from_vtt]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<c.colorE5E5E5>olá</c> mundo", "olá mundo"),
        ("[Música] ♪ ♪", ""),
        ("(música de fundo) mexa bem", "mexa bem"),
        ("sal &amp; pimenta", "sal & pimenta"),
        ("  muitos   espaços\n aqui ", "muitos espaços aqui"),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def _track(lang: str, kind: str = "auto", translated: bool = False) -> SubtitleTrack:
    return SubtitleTrack(lang, kind, translated, {"json3": f"https://x/{lang}"})  # type: ignore[arg-type]


def _order(tracks: list[SubtitleTrack], video_language: str | None = None) -> list[str]:
    return [f"{t.kind}:{t.lang}" for t in rank_subtitle_tracks(tracks, video_language)]


def test_rank_prefers_manual_pt_then_manual_en_then_auto() -> None:
    tracks = [
        _track("en-orig"),
        _track("pt", translated=True),
        _track("en", "manual"),
        _track("pt-BR", "manual"),
        _track("fr", "manual"),
    ]
    assert _order(tracks, "en") == [
        "manual:pt-BR",
        "manual:en",
        "auto:en-orig",
        "auto:pt",
    ]


def test_rank_auto_pt_original_before_auto_en() -> None:
    tracks = [_track("en", translated=True), _track("pt"), _track("pt-orig")]
    assert _order(tracks, "pt-BR") == ["auto:pt-orig", "auto:pt", "auto:en"]


def test_rank_region_variants() -> None:
    tracks = [
        _track("pt-PT", "manual"),
        _track("pt-BR", "manual"),
        _track("en-GB", "manual"),
        _track("en-US", "manual"),
        _track("en-ehkg1hFWq8A", "manual"),
    ]
    assert _order(tracks) == [
        "manual:pt-BR",
        "manual:pt-PT",
        "manual:en-US",
        "manual:en-GB",
        "manual:en-ehkg1hFWq8A",
    ]


def test_rank_falls_back_to_video_language_before_translations() -> None:
    tracks = [
        _track("pt", translated=True),
        _track("es-orig"),
        _track("es", "manual"),
        _track("de", translated=True),
    ]
    assert _order(tracks, "es") == ["manual:es", "auto:es-orig", "auto:pt"]


def test_rank_without_candidates() -> None:
    assert rank_subtitle_tracks([_track("ja", "manual"), _track("ko")], "ja-JP") == [
        SubtitleTrack("ja", "manual", False, {"json3": "https://x/ja"})
    ]
    assert rank_subtitle_tracks([], None) == []


def test_metadata_from_info_parses_tracks() -> None:
    timedtext = "https://www.youtube.com/api/timedtext?v=abc&lang=pt"
    info = {
        "id": "abcdefghijk",
        "title": "Bolo de cenoura",
        "channel": "Receitas",
        "duration": 533.4,
        "thumbnail": "https://i.ytimg.com/vi/abcdefghijk/maxresdefault.jpg",
        "description": "Ingredientes: 3 cenouras",
        "playable_in_embed": True,
        "availability": "public",
        "live_status": "not_live",
        "age_limit": 0,
        "language": "pt",
        "subtitles": {
            "live_chat": [{"ext": "json", "url": "https://x"}],
            "pt-BR": [
                {"ext": "srv1", "url": timedtext + "&fmt=srv1"},
                {"ext": "vtt", "url": timedtext + "&fmt=vtt"},
                {"ext": "json3", "url": timedtext + "&fmt=json3"},
            ],
        },
        "automatic_captions": {
            "pt-orig": [{"ext": "json3", "url": timedtext + "&kind=asr&fmt=json3"}],
            "en": [
                {"ext": "json3", "url": timedtext + "&kind=asr&tlang=en&fmt=json3"},
                {
                    "ext": "vtt",
                    "url": "https://manifest.googlevideo.com/x",
                    "protocol": "m3u8_native",
                },
            ],
            "pt-BR": [
                {
                    "ext": "vtt",
                    "url": "https://manifest.googlevideo.com/y",
                    "protocol": "m3u8_native",
                }
            ],
            "fr": [{"ext": "ttml", "url": timedtext + "&tlang=fr&fmt=ttml"}],
        },
    }

    meta = metadata_from_info(info)

    assert meta.duration_s == 533
    assert meta.embeddable is True
    assert [(t.kind, t.lang, t.translated, sorted(t.formats)) for t in meta.subtitles] == [
        ("manual", "pt-BR", False, ["json3", "vtt"]),
        ("auto", "pt-orig", False, ["json3"]),
        ("auto", "en", True, ["json3"]),
    ]


@pytest.mark.parametrize(
    ("formats", "fixture", "fetched"),
    [
        ({"json3": "https://x/j", "vtt": "https://x/v"}, "auto.pt.json3", ["https://x/j"]),
        ({"vtt": "https://x/v"}, "auto.pt.vtt", ["https://x/v"]),
    ],
)
async def test_download_subtitle_prefers_json3_and_falls_back_to_vtt(
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
    formats: dict[str, str],
    fixture: str,
    fetched: list[str],
) -> None:
    urls: list[str] = []

    def fake_fetch(url: str) -> bytes:
        urls.append(url)
        return (fixtures_dir / fixture).read_bytes()

    monkeypatch.setattr(youtube, "_fetch_url", fake_fetch)

    segments = await youtube.download_subtitle(SubtitleTrack("pt", "auto", False, formats))

    assert urls == fetched
    assert [s["text"] for s in segments] == EXPECTED_AUTO_TEXTS


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requested: int | None = None

    def read(self, amt: int | None = None) -> bytes:
        self.requested = amt
        return self.body if amt is None else self.body[:amt]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeYDL:
    response: _FakeResponse

    def __init__(self, opts: dict[str, Any]) -> None:
        pass

    def __enter__(self) -> "_FakeYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def urlopen(self, request: object) -> _FakeResponse:
        return self.response


@pytest.mark.parametrize(("size", "ok"), [(100, True), (101, False)])
def test_fetch_url_limits_subtitle_size(
    monkeypatch: pytest.MonkeyPatch, size: int, ok: bool
) -> None:
    _FakeYDL.response = _FakeResponse(b"x" * size)
    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", _FakeYDL)

    if ok:
        assert youtube._fetch_url("https://x/legenda", max_bytes=100) == b"x" * size
    else:
        with pytest.raises(ValueError, match="maior que"):
            youtube._fetch_url("https://x/legenda", max_bytes=100)
    # Nunca lê a resposta inteira para a memória.
    assert _FakeYDL.response.requested == 101
