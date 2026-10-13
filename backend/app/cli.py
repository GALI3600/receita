"""Linha de comando para testar o pipeline.

uv run python -m app.cli import <url> [--skip-llm] [--json]
"""

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from app.db import SessionLocal, engine
from app.errors import PipelineError
from app.models import ImportStatus, Video
from app.services.pipeline import process_video
from app.services.recipe_llm import format_timestamp
from app.services.transcription import word_count

_STAGE_LABELS = {
    ImportStatus.FETCHING: "Buscando vídeo",
    ImportStatus.TRANSCRIBING: "Transcrevendo",
    ImportStatus.GENERATING: "Escrevendo a receita",
}


def _print_stage(status: ImportStatus) -> None:
    print(f"→ {_STAGE_LABELS.get(status, status)}...", file=sys.stderr, flush=True)


def _video_as_dict(video: Video) -> dict[str, Any]:
    return {
        "id": str(video.id),
        "youtube_id": video.youtube_id,
        "title": video.title,
        "channel": video.channel,
        "duration_s": video.duration_s,
        "embeddable": video.embeddable,
        "transcript_source": video.transcript_source,
        "transcript": video.transcript,
        "generated_recipe": video.generated_recipe,
        "llm_model": video.llm_model,
        "llm_usage": video.llm_usage,
        "prompt_version": video.prompt_version,
    }


def _print_summary(video: Video) -> None:
    segments = video.transcript or []
    words = word_count(segments)
    print(f"\n{video.title}  [{video.youtube_id}]")
    print(f"canal: {video.channel}  duração: {format_timestamp(video.duration_s)}")
    print(f"transcrição: {video.transcript_source} — {len(segments)} trechos, {words} palavras")
    for seg in segments[:8]:
        print(f"  [{format_timestamp(seg['start'])}] {seg['text']}")
    if len(segments) > 8:
        print(f"  ... (+{len(segments) - 8} trechos)")

    if video.generated_recipe is None:
        print("\nreceita: não gerada (--skip-llm)")
        return
    print(f"\nreceita ({video.llm_model}, prompt {video.prompt_version}):")
    print(json.dumps(video.generated_recipe, ensure_ascii=False, indent=2))
    print(f"uso: {json.dumps(video.llm_usage)}")


async def _import(url: str, *, skip_llm: bool, as_json: bool) -> int:
    async def on_stage(status: ImportStatus) -> None:
        _print_stage(status)

    try:
        async with SessionLocal() as session:
            try:
                video = await process_video(url, session, skip_llm=skip_llm, on_stage=on_stage)
            except PipelineError as exc:
                print(f"erro [{exc.code}]: {exc.message}", file=sys.stderr)
                if exc.detail:
                    print(f"  detalhe: {exc.detail}", file=sys.stderr)
                return 1
    finally:
        await engine.dispose()

    if as_json:
        print(json.dumps(_video_as_dict(video), ensure_ascii=False, indent=2))
    else:
        _print_summary(video)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Ferramentas do Receita")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("import", help="processa um vídeo do YouTube e salva no banco")
    cmd.add_argument("url")
    cmd.add_argument("--skip-llm", action="store_true", help="para depois da transcrição")
    cmd.add_argument("--json", action="store_true", help="imprime o Video completo em JSON")
    cmd.add_argument("-v", "--verbose", action="store_true", help="mostra os logs")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_import(args.url, skip_llm=args.skip_llm, as_json=args.json))


if __name__ == "__main__":
    sys.exit(main())
