"""Linha de comando para testar o pipeline.

uv run python -m app.cli import <url> [--skip-llm] [--json]
uv run python -m app.cli seed-demo --email <email>   # só em ENVIRONMENT=development
uv run python -m app.cli llm-spend [--days 7] [--by day|version]   # gasto com o Claude x orçamento
uv run python -m app.cli llm-cache-sim [--days 14]   # acerto e custo do cache, TTL de 5 min x 1 h
uv run python -m app.cli llm-eval --ids evals/ids.txt --model M --effort E --out DIR [--yes]
    [--max-tokens N] [--no-fallbacks] [--repeat K] | --from-db   # eval da geração (purpose eval)
"""

import argparse
import asyncio
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal, engine
from app.errors import PipelineError
from app.models import ImportStatus, LLMPurpose, Video
from app.services import llm_eval, llm_reports, quotas, recipe_llm, youtube
from app.services.demo import DEMO_VIDEOS, DemoSeedError, seed_demo
from app.services.pipeline import find_video, process_video
from app.services.quotas import llm_spend_by_day
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
        "description": video.description,
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


async def _failure_as_dict(session: AsyncSession, url: str, exc: PipelineError) -> dict[str, Any]:
    failure: dict[str, Any] = {"error_code": exc.code, "error_detail": exc.detail}
    try:
        video = await find_video(session, youtube.extract_youtube_id(url))
    except PipelineError:
        video = None
    return {**failure, **(_video_as_dict(video) if video is not None else {})}


async def _import(url: str, *, skip_llm: bool, as_json: bool) -> int:
    async def on_stage(status: ImportStatus) -> None:
        _print_stage(status)

    try:
        async with SessionLocal() as session:
            try:
                video = await process_video(
                    url, session, skip_llm=skip_llm, on_stage=on_stage, purpose=LLMPurpose.CLI
                )
            except PipelineError as exc:
                print(f"erro [{exc.code}]: {exc.message}", file=sys.stderr)
                if exc.detail:
                    print(f"  detalhe: {exc.detail}", file=sys.stderr)
                if as_json:
                    # O vídeo pode ter ficado salvo (ex.: receita que não é receita, em cache).
                    print(
                        json.dumps(
                            await _failure_as_dict(session, url, exc), ensure_ascii=False, indent=2
                        )
                    )
                return 1
    finally:
        await engine.dispose()

    if as_json:
        print(json.dumps(_video_as_dict(video), ensure_ascii=False, indent=2))
    else:
        _print_summary(video)
    return 0


async def _seed_demo(email: str) -> int:
    try:
        async with SessionLocal() as session:
            try:
                recipe_ids = await seed_demo(session, email)
            except DemoSeedError as exc:
                print(f"erro: {exc}", file=sys.stderr)
                return 1
    finally:
        await engine.dispose()

    for demo, recipe_id in zip(DEMO_VIDEOS, recipe_ids, strict=True):
        print(f"{recipe_id}  {demo.recipe['title']}  [{demo.youtube_id}]")
    return 0


async def _llm_spend(days: int) -> int:
    try:
        async with SessionLocal() as session:
            report = await llm_spend_by_day(session, days)
    finally:
        await engine.dispose()

    settings = get_settings()
    budget = settings.daily_llm_budget_usd
    print(f"orçamento diário (DAILY_LLM_BUDGET_USD): US$ {budget:.2f}")
    eval_budget = settings.eval_daily_llm_budget_usd
    print(f"orçamento do eval (EVAL_DAILY_LLM_BUDGET_USD): US$ {eval_budget:.2f}")
    print("dia (UTC)    chamadas  falhas  sem resposta  produção (US$)  eval (US$)  % do orçamento")
    for spend in report:
        share = f"{spend.cost_usd / Decimal(str(budget)):>7.0%}" if budget else "      -"
        print(
            f"{spend.day.isoformat()}  {spend.calls:>8}  {spend.failed_calls:>6}  "
            f"{spend.unfinished_calls:>12}  {spend.cost_usd:>14.4f}  {spend.eval_cost_usd:>10.4f}"
            f"  {share}"
        )
    total = sum((spend.cost_usd for spend in report), Decimal(0))
    eval_total = sum((spend.eval_cost_usd for spend in report), Decimal(0))
    print(f"total em {days} dia(s): produção US$ {total:.4f}, eval US$ {eval_total:.4f}")
    return 0


def _share(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _usd(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:.4f}"


async def _llm_spend_by_version(days: int) -> int:
    try:
        async with SessionLocal() as session:
            report = await llm_reports.spend_by_version(session, days)
            lost = await llm_reports.lost_calls(session, days)
    finally:
        await engine.dispose()

    print(
        f"{'prompt':<14}{'modelo':<20}{'purpose':<10}{'chamadas':>9}{'ok':>6}{'sem resp.':>10}"
        f"{'US$':>10}{'US$/ok':>9}{'saída':>10}{'thinking%':>10}{'cache%':>8}{'p95':>8}"
        f"{'p95/teto':>9}{'cortes':>7}"
    )
    for row in report:
        print(
            f"{row.prompt_version:<14}{row.model:<20}{row.purpose:<10}{row.calls:>9}{row.ok:>6}"
            f"{row.unanswered:>10}{_usd(row.cost_usd):>10}{_usd(row.cost_per_ok_usd):>9}"
            f"{row.output_tokens:>10}{_share(row.thinking_share):>10}{_share(row.hit_rate):>8}"
            f"{row.p95_output if row.p95_output is not None else '-':>8}"
            f"{_share(row.p95_share):>9}{row.cut:>7}"
        )
    total = sum((row.cost_usd for row in report), Decimal(0))
    print(f"total em {days} dia(s): US$ {total:.4f}")
    hours = int(llm_reports.LOST_CALL_AFTER.total_seconds() // 3600)
    print(f"perdidas (llm_in_progress há mais de {hours} h, contam a estimativa): {lost}")
    return 0


async def _llm_cache_sim(days: int, readable_after_s: float) -> int:
    try:
        async with SessionLocal() as session:
            report = await llm_reports.cache_sim(session, days, readable_after_s)
    finally:
        await engine.dispose()

    print(
        f"chamadas de {', '.join(llm_reports.CACHE_SIM_PURPOSES)} nos últimos {days} dia(s); "
        f"escrita legível {readable_after_s:g} s depois do início"
    )
    print(
        f"{'modelo':<20}{'prompt':<14}{'effort':<8}{'chamadas':>9}{'acerto real':>12}"
        f"{'acerto 5m':>10}{'acerto 1h':>10}{'US$ real':>10}{'sem marcador':>13}{'5m':>9}{'1h':>9}"
    )

    def line(label: str, rows: list[llm_reports.CacheSimGroup]) -> str:
        calls = sum(row.calls for row in rows)

        def hits(count: int) -> str:
            return _share(count / calls if calls else None)

        def cost(name: str) -> str:
            return _usd(sum((getattr(row, name) for row in rows), Decimal(0)))

        return (
            f"{label}{calls:>9}{hits(sum(r.real_hits for r in rows)):>12}"
            f"{hits(sum(r.hits_5m for r in rows)):>10}{hits(sum(r.hits_1h for r in rows)):>10}"
            f"{cost('cost_real_usd'):>10}{cost('cost_none_usd'):>13}{cost('cost_5m_usd'):>9}"
            f"{cost('cost_1h_usd'):>9}"
        )

    for row in report:
        print(line(f"{row.model:<20}{row.prompt_version:<14}{row.effort or '-':<8}", [row]))
    print(line(f"{'total':<42}", report))
    print("Custos só das chamadas com usage. 1 h compensa com acerto 1 h ≥ ~51% (CUSTO.md § 5.1).")
    return 0


def _print_eval_summary(summary: llm_eval.EvalSummary) -> None:
    print(
        f"\nchamadas: {summary.calls}  ok: {summary.ok}  recusas: {summary.refused}  "
        f"erros: {summary.errors}"
    )
    print(f"custo: US$ {summary.cost_usd:.4f}  por receita ok: US$ {_usd(summary.cost_per_ok_usd)}")
    print(
        f"p95 da saída: {summary.p95_output if summary.p95_output is not None else '-'}  "
        f"thinking: {_share(summary.thinking_share)}  "
        f"acerto do cache: {_share(summary.cache_hit_share)}"
    )
    failed = ", ".join(f"{name} {count}" for name, count in summary.failed_checks.items() if count)
    print(f"checagens reprovadas: {failed or 'nenhuma'}")


def _eval_config(args: argparse.Namespace) -> recipe_llm.LLMConfig | None:
    if args.from_db:
        return None
    model = args.model
    fallbacks = not args.no_fallbacks and model in recipe_llm.SERVER_FALLBACK_MODELS
    if not args.no_fallbacks and not fallbacks:
        print(f"sem fallback do servidor para {model}")
    if model not in quotas.MODEL_PRICES:
        print(f"aviso: {model} sem preço cadastrado; o custo usa o maior preço publicado")
    return recipe_llm.LLMConfig(
        model=model,
        effort=None if args.effort == "none" else args.effort,
        max_tokens=args.max_tokens,
        fallbacks=fallbacks,
        cache_ttl=get_settings().llm_cache_ttl,
    )


async def _llm_eval(
    entries: list[llm_eval.EvalEntry],
    config: recipe_llm.LLMConfig | None,
    *,
    repeat: int,
    out_dir: Path,
    yes: bool,
) -> int:
    exceeded = False
    try:
        async with SessionLocal() as session:
            try:
                videos = await llm_eval.load_videos(session, entries)
            except llm_eval.EvalInputError as exc:
                print(f"erro: {exc}", file=sys.stderr)
                return 1
            if config is None:
                print(f"{len(videos)} vídeo(s) × {repeat}: receitas gravadas no banco")
            else:
                print(
                    f"config: {config.model}, effort {config.effort or '-'}, max_tokens "
                    f"{config.max_tokens}, fallbacks {'sim' if config.fallbacks else 'não'}, "
                    f"cache {config.cache_ttl}"
                )
                cost = llm_eval.estimate(videos, config, repeat)
                spent = await quotas.llm_spend_today(session, quotas.Budget.EVAL)
                print(
                    f"estimativa: {cost.calls} chamada(s), típica US$ {cost.typical_usd:.4f}, "
                    f"teto US$ {cost.ceiling_usd:.4f}"
                )
                print(
                    f"gasto do eval hoje: US$ {spent:.4f} de US$ "
                    f"{get_settings().eval_daily_llm_budget_usd:.2f} (EVAL_DAILY_LLM_BUDGET_USD)"
                )
                if not yes:
                    print("passe --yes para rodar")
                    return 1
            try:
                results = await llm_eval.run_eval(
                    session,
                    entries,
                    config=config,
                    repeat=repeat,
                    out_dir=out_dir,
                    from_db=config is None,
                    progress=lambda line: print(line, file=sys.stderr, flush=True),
                )
            except llm_eval.EvalBudgetExceeded as exc:
                print(f"orçamento do eval esgotado: {exc}", file=sys.stderr)
                results, exceeded = exc.results, True
    finally:
        await engine.dispose()

    _print_eval_summary(llm_eval.summarize(results))
    print(f"resultados em {out_dir}")
    return 2 if exceeded else 0


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("deve ser ≥ 1")
    return number


def _max_tokens(value: str) -> int:
    number = int(value)
    if not 1 <= number <= recipe_llm.MAX_NONSTREAMING_TOKENS:
        raise argparse.ArgumentTypeError(
            f"deve ficar entre 1 e {recipe_llm.MAX_NONSTREAMING_TOKENS}: acima disso o SDK exige "
            "streaming numa chamada sem stream"
        )
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Ferramentas do Receita")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("import", help="processa um vídeo do YouTube e salva no banco")
    cmd.add_argument("url")
    cmd.add_argument("--skip-llm", action="store_true", help="para depois da transcrição")
    cmd.add_argument("--json", action="store_true", help="imprime o Video completo em JSON")
    cmd.add_argument("-v", "--verbose", action="store_true", help="mostra os logs")
    seed = sub.add_parser(
        "seed-demo",
        help="põe receitas de demonstração no livro de um usuário (só em development)",
    )
    seed.add_argument("--email", required=True, help="e-mail de uma conta já cadastrada")
    spend = sub.add_parser("llm-spend", help="gasto com o Claude (dias UTC) e o orçamento")
    spend.add_argument("--days", type=int, default=7, help="quantos dias mostrar (padrão 7)")
    spend.add_argument(
        "--by",
        choices=("day", "version"),
        default="day",
        help="por dia (padrão) ou por prompt × modelo × purpose",
    )
    cache = sub.add_parser(
        "llm-cache-sim", help="simula o cache com TTL de 5 min e de 1 h sobre as chamadas reais"
    )
    cache.add_argument("--days", type=int, default=14, help="janela em dias UTC (padrão 14)")
    cache.add_argument(
        "--readable-after-s",
        type=float,
        default=5.0,
        help="segundos até a escrita no cache ficar legível (padrão 5)",
    )
    ev = sub.add_parser(
        "llm-eval", help="roda uma configuração do Claude sobre um conjunto fixo de vídeos"
    )
    ev.add_argument("--ids", required=True, help="arquivo de ids (ex.: evals/ids.txt)")
    ev.add_argument("--out", required=True, help="diretório dos resultados (criado)")
    ev.add_argument("--repeat", type=_positive_int, default=1, help="trials por vídeo (padrão 1)")
    ev.add_argument("--yes", action="store_true", help="roda de fato (chamadas pagas)")
    ev.add_argument(
        "--from-db", action="store_true", help="avalia as receitas gravadas, sem chamar o Claude"
    )
    ev.add_argument("--model")
    ev.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max", "none"))
    ev.add_argument(
        "--max-tokens",
        type=_max_tokens,
        help=f"teto da saída (padrão {recipe_llm.MAX_TOKENS})",
    )
    ev.add_argument("--no-fallbacks", action="store_true", help="sem fallback do servidor")
    args = parser.parse_args(argv)

    if args.command == "llm-spend":
        logging.basicConfig(level=logging.WARNING)
        if args.by == "version":
            return asyncio.run(_llm_spend_by_version(max(1, args.days)))
        return asyncio.run(_llm_spend(max(1, args.days)))

    if args.command == "llm-cache-sim":
        logging.basicConfig(level=logging.WARNING)
        return asyncio.run(_llm_cache_sim(max(1, args.days), max(0.0, args.readable_after_s)))

    if args.command == "llm-eval":
        if args.from_db:
            config_flags = [
                flag
                for flag, given in (
                    ("--model", args.model is not None),
                    ("--effort", args.effort is not None),
                    ("--max-tokens", args.max_tokens is not None),
                    ("--no-fallbacks", args.no_fallbacks),
                )
                if given
            ]
            if config_flags:
                ev.error(f"--from-db não aceita {', '.join(config_flags)}")
        elif args.model is None or args.effort is None:
            ev.error("--model e --effort são obrigatórios sem --from-db")
        if args.max_tokens is None:
            args.max_tokens = recipe_llm.MAX_TOKENS
        try:
            entries = llm_eval.parse_ids(Path(args.ids).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"erro em {args.ids}: {exc}", file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        if (out_dir / "summary.csv").exists():
            print(f"erro: {out_dir / 'summary.csv'} já existe; use outro --out", file=sys.stderr)
            return 1
        logging.basicConfig(level=logging.WARNING)
        return asyncio.run(
            _llm_eval(
                entries, _eval_config(args), repeat=args.repeat, out_dir=out_dir, yes=args.yes
            )
        )

    if args.command == "seed-demo":
        logging.basicConfig(level=logging.WARNING)
        return asyncio.run(_seed_demo(args.email))

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_import(args.url, skip_llm=args.skip_llm, as_json=args.json))


if __name__ == "__main__":
    sys.exit(main())
