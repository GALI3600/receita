"""Eval da geração da receita: roda uma configuração do Claude sobre um conjunto fixo de vídeos.

A entrada são os `Video` já transcritos no banco (sem yt-dlp nem whisper: idêntica byte a byte
entre configurações). O eval nunca escreve em `Video`; cada chamada vai para `llm_calls` com
`purpose` eval, sob o teto próprio `EVAL_DAILY_LLM_BUDGET_USD`, fora do orçamento de produção e
do limite de tentativas do vídeo. Roda em ordem estável (a do arquivo de ids, com os trials de
um vídeo em seguida) e sequencial. Grava `DIR/<id>.json` a cada resultado e `DIR/summary.csv` no
fim, com as checagens automáticas (de graça) de cada receita contra a referência gravada.
`from_db` avalia as receitas já gravadas, sem chamar o Claude.
"""

import csv
import json
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import ErrorCode, LLMBudgetExceededError, NoTranscriptError, PipelineError
from app.models import LLMPurpose, Video
from app.schemas.transcript import Segment
from app.services import llm_calls, pipeline, quotas, recipe_llm
from app.services.llm_reports import nearest_rank, thinking_tokens
from app.services.recipe_llm import LLMConfig

_YOUTUBE_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
_COST_STEP = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class EvalEntry:
    youtube_id: str
    expected_is_recipe: bool | None


def parse_ids(text: str) -> list[EvalEntry]:
    """Lê o arquivo de ids: um `youtube_id` por linha, opcionalmente seguido de true/false (o
    `is_recipe` esperado). Linhas vazias e com # são ignoradas."""
    entries: list[EvalEntry] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) > 2 or not _YOUTUBE_ID_RE.fullmatch(fields[0]):
            raise ValueError(f"linha {lineno}: esperado '<youtube_id> [true|false]': {line!r}")
        youtube_id = fields[0]
        expected: bool | None = None
        if len(fields) == 2:
            flag = fields[1].lower()
            if flag not in ("true", "false"):
                raise ValueError(f"linha {lineno}: is_recipe esperado deve ser true ou false")
            expected = flag == "true"
        if youtube_id in seen:
            raise ValueError(f"linha {lineno}: {youtube_id} repetido")
        seen.add(youtube_id)
        entries.append(EvalEntry(youtube_id, expected))
    return entries


class EvalInputError(Exception):
    """Vídeo do conjunto ausente do banco ou sem transcrição."""


async def load_videos(session: AsyncSession, entries: list[EvalEntry]) -> list[Video]:
    """Os vídeos do conjunto, na ordem do arquivo; `EvalInputError` lista todos os que faltam."""
    ids = [entry.youtube_id for entry in entries]
    found = {
        video.youtube_id: video
        for video in await session.scalars(select(Video).where(Video.youtube_id.in_(ids)))
    }
    await session.commit()
    missing = [youtube_id for youtube_id in ids if youtube_id not in found]
    untranscribed = [
        youtube_id
        for youtube_id in ids
        if youtube_id in found and found[youtube_id].transcript is None
    ]
    problems = []
    if missing:
        problems.append(f"fora do banco: {', '.join(missing)}")
    if untranscribed:
        problems.append(f"sem transcrição: {', '.join(untranscribed)}")
    if problems:
        raise EvalInputError("; ".join(problems))
    return [found[youtube_id] for youtube_id in ids]


@dataclass(frozen=True, slots=True)
class CostEstimate:
    calls: int
    # Saída = output_tokens da receita gravada quando há (até max_tokens), senão
    # min(LLM_RESERVED_OUTPUT_TOKENS, max_tokens); o prefixo é escrito no cache só na 1ª
    # chamada e lido nas outras (rodam em sequência, bem dentro do TTL).
    typical_usd: Decimal
    # Saída = max_tokens e prefixo escrito em toda chamada: o que as chamadas podem custar de
    # fato. Não inclui as tentativas extras do fallback do servidor.
    ceiling_usd: Decimal


def estimate(videos: list[Video], config: LLMConfig, repeat: int) -> CostEstimate:
    """Custo esperado do eval. Vídeos que não chegariam ao Claude (sem fala útil e com
    descrição curta) não entram."""
    reserved = min(get_settings().llm_reserved_output_tokens, config.max_tokens)
    calls = 0
    typical = ceiling = Decimal(0)
    for video in videos:
        try:
            prompt = recipe_llm.estimate_prompt(pipeline.llm_context(video))
        except NoTranscriptError:
            continue
        reference_output = (video.llm_usage or {}).get("output_tokens")
        output = (
            min(reference_output, config.max_tokens)
            if isinstance(reference_output, int)
            else reserved
        )
        for _ in range(repeat):
            calls += 1
            typical += _call_cost(config, prompt, output, cache_hit=calls > 1)
            ceiling += _call_cost(config, prompt, config.max_tokens, cache_hit=False)
    return CostEstimate(calls, typical, ceiling)


def _call_cost(
    config: LLMConfig, prompt: recipe_llm.PromptEstimate, output_tokens: int, *, cache_hit: bool
) -> Decimal:
    return quotas.estimate_cost_usd(
        config.model,
        prefix_tokens=prompt.prefix_tokens,
        input_tokens=prompt.input_tokens,
        output_tokens=output_tokens,
        cache_ttl=config.cache_ttl,
        cache_hit=cache_hit,
    )


# --- Checagens (puras) ------------------------------------------------------------------------

# Dica que fala das fontes (regra 8 do SYSTEM_PROMPT: "o vídeo não informa", "a descrição diz",
# "na fala"). Nos JSONs do eval: 33 dicas na v1, 0 na v2 e na v3.
SOURCE_MENTION_RE = re.compile(
    r"\b(v[íi]deos?|descri[çc](?:ão|ao|ões|oes)|transcri[çc](?:ão|ao|ões|oes)|legendas?|canal|"
    r"coment[áa]rios?|narra[çc](?:ão|ao)|(?:na|da|pela) fala|(?:o|a) apresentador(?:a)?|"
    r"youtube|fontes?)\b",
    re.IGNORECASE,
)

_WORD_RE = re.compile(r"[a-záàéèíóúâêôãõçñü]+")
_EN_WORDS = frozenset(
    "the and with until into then add of is it your to in on or stir bake mix for at "
    "minutes".split()
)
# Imperativo de usted e de tú (vídeos latino-americanos).
_ES_WORDS = frozenset(
    "el la los las y con hasta agregar añadir una del luego agregue añada mezcle hornee agrega "
    "añade mezcla hornea cocina calienta".split()
)
_PT_WORDS = frozenset("o os as e com até de do da dos das em no na um uma por para ao à".split())

# Unidade imperial que devia ter sido convertida (regra 1 do SYSTEM_PROMPT). Num passo, só conta
# sem uma medida métrica junto: "70 a 85 g (2½ a 3 oz)" está certo, "asse a 350 °F" não.
IMPERIAL_UNIT_RE = re.compile(
    r"\b(?:oz|fl\.?\s?oz|onças?|lbs?|libras?|pounds?|ounces?|cups?|tbsp|tsp|tablespoons?|"
    r"teaspoons?|inch(?:es)?|polegadas?)\b|[°º]\s?F\b",
    re.IGNORECASE,
)
# "º" (indicador ordinal) é como muita gente escreve o grau em português.
METRIC_RE = re.compile(r"\b(?:g|kg|ml|l|litros?|gramas?|cm)\b|[°º]\s?C\b", re.IGNORECASE)


def is_foreign_text(text: str) -> bool:
    """Passo em outro idioma: ≥ 2 palavras típicas de inglês ou de espanhol e mais delas que de
    português."""
    words = _WORD_RE.findall(text.lower())
    portuguese = sum(word in _PT_WORDS for word in words)
    return any(
        count >= 2 and count > portuguese
        for count in (
            sum(word in _EN_WORDS for word in words),
            sum(word in _ES_WORDS for word in words),
        )
    )


def _imperial_outside_note(recipe: dict[str, Any]) -> int:
    count = 0
    for ingredient in recipe.get("ingredients") or []:
        measure = f"{ingredient.get('quantity') or ''} {ingredient.get('unit') or ''}"
        count += bool(IMPERIAL_UNIT_RE.search(measure))
    for step in recipe.get("steps") or []:
        text = step.get("text") or ""
        count += bool(IMPERIAL_UNIT_RE.search(text) and not METRIC_RE.search(text))
    return count


def _group_count(recipe: dict[str, Any]) -> int:
    # "marmita 1 – tutu" e "marmita 1 – acompanhamentos" são partes do mesmo preparo: conta o
    # que vem antes do travessão (OWLnnv4tsFQ: 3 marmitas).
    groups = {
        str(ingredient["group"]).split("–")[0].strip().casefold()
        for ingredient in recipe.get("ingredients") or []
        if ingredient.get("group")
    }
    return len(groups)


@dataclass(frozen=True, slots=True)
class TimestampCheck:
    # Passos pareados por ordem com timestamp no novo e na referência.
    pairs: int
    # Média com sinal (novo − referência).
    mean_delta_s: float | None
    mean_abs_delta_s: float | None
    # Fração com o trecho da transcrição a no máximo 1 do trecho da referência.
    same_segment_share: float | None
    # Passos do novo com timestamp menor que o do anterior não nulo.
    out_of_order: int


def segment_index(starts: list[int], ts: int) -> int:
    """Trecho da transcrição que contém `ts`; `starts` são os inícios em segundos inteiros, como
    no marcador [Ns]."""
    return max(0, bisect_right(starts, ts) - 1)


def _timestamps(recipe: dict[str, Any] | None) -> list[int | None]:
    steps = sorted((recipe or {}).get("steps") or [], key=lambda step: step.get("order") or 0)
    return [step.get("video_timestamp_s") for step in steps]


def check_timestamps(
    recipe: dict[str, Any] | None, reference: dict[str, Any] | None, transcript: list[Segment]
) -> TimestampCheck:
    new = _timestamps(recipe)
    out_of_order = 0
    previous: int | None = None
    for ts in new:
        if ts is None:
            continue
        if previous is not None and ts < previous:
            out_of_order += 1
        previous = ts
    if reference is None:
        return TimestampCheck(0, None, None, None, out_of_order)

    pairs = [
        (ts, ref)
        for ts, ref in zip(new, _timestamps(reference), strict=False)
        if ts is not None and ref is not None
    ]
    if not pairs:
        return TimestampCheck(0, None, None, None, out_of_order)
    starts = [int(seg["start"]) for seg in transcript]
    deltas = [ts - ref for ts, ref in pairs]
    same = sum(
        abs(segment_index(starts, ts) - segment_index(starts, ref)) <= 1 for ts, ref in pairs
    )
    return TimestampCheck(
        pairs=len(pairs),
        mean_delta_s=sum(deltas) / len(deltas),
        mean_abs_delta_s=sum(abs(delta) for delta in deltas) / len(deltas),
        same_segment_share=same / len(pairs),
        out_of_order=out_of_order,
    )


@dataclass(frozen=True, slots=True)
class Checks:
    is_recipe: bool | None
    # None sem o esperado.
    is_recipe_ok: bool | None
    # stop_reason "max_tokens" ou error_code llm_output_too_long.
    cut_by_max_tokens: bool
    source_tips: int
    foreign_steps: int
    imperial_outside_note: int
    ingredients: int
    steps: int
    # Preparos distintos nos grupos de ingredientes (OWLnnv4tsFQ: 3 marmitas).
    groups: int
    ref_ingredients: int | None
    ref_steps: int | None
    ref_groups: int | None
    timestamps: TimestampCheck


def run_checks(
    *,
    recipe: dict[str, Any] | None,
    stop_reason: str | None,
    error_code: str | None,
    expected_is_recipe: bool | None,
    reference: dict[str, Any] | None,
    transcript: list[Segment],
) -> Checks:
    """Checagens automáticas de uma receita (ou de uma falha, com `recipe` None)."""
    data = recipe or {}
    is_recipe = data.get("is_recipe") if recipe is not None else None
    steps = data.get("steps") or []
    return Checks(
        is_recipe=is_recipe,
        is_recipe_ok=(
            None
            if is_recipe is None or expected_is_recipe is None
            else is_recipe == expected_is_recipe
        ),
        cut_by_max_tokens=(
            stop_reason == "max_tokens" or error_code == ErrorCode.LLM_OUTPUT_TOO_LONG
        ),
        source_tips=sum(bool(SOURCE_MENTION_RE.search(tip)) for tip in data.get("tips") or []),
        foreign_steps=sum(is_foreign_text(step.get("text") or "") for step in steps),
        imperial_outside_note=_imperial_outside_note(data),
        ingredients=len(data.get("ingredients") or []),
        steps=len(steps),
        groups=_group_count(data),
        ref_ingredients=len(reference.get("ingredients") or []) if reference else None,
        ref_steps=len(reference.get("steps") or []) if reference else None,
        ref_groups=_group_count(reference) if reference else None,
        timestamps=check_timestamps(recipe, reference, transcript),
    )


# --- Execução ---------------------------------------------------------------------------------

NO_TRANSCRIPT = str(ErrorCode.NO_TRANSCRIPT)


@dataclass(frozen=True, slots=True)
class EvalResult:
    youtube_id: str
    trial: int
    # "ok" ou o código do erro ("no_transcript" quando o vídeo nem chega ao Claude).
    status: str
    error_detail: str | None
    recipe: dict[str, Any] | None
    model: str | None
    usage: dict[str, Any]
    cost_usd: Decimal
    stop_reason: str | None
    request_id: str | None
    latency_ms: int | None
    checks: Checks
    expected_is_recipe: bool | None = None
    # Prompt da geração avaliada e o da receita gravada usada como referência (None sem
    # referência: ela só vale com o prompt atual).
    prompt_version: str | None = None
    reference_prompt_version: str | None = None


class EvalBudgetExceeded(Exception):
    """O orçamento de eval acabou no meio; os resultados até ali foram gravados."""

    def __init__(self, detail: str, results: list[EvalResult]) -> None:
        super().__init__(detail)
        self.results = results


@dataclass(frozen=True, slots=True)
class _VideoInput:
    """O que o eval lê do `Video`, guardado antes de chamar: um rollback (`mark_interrupted`)
    expira o objeto, e o lazy load na sessão async falharia."""

    video: Video
    youtube_id: str
    expected_is_recipe: bool | None
    transcript: list[Segment]
    context: recipe_llm.VideoContext | None
    reference: dict[str, Any] | None
    reference_prompt_version: str | None
    stored_recipe: dict[str, Any] | None
    stored_model: str | None
    stored_usage: dict[str, Any]
    stored_prompt_version: str | None


def _read_video(video: Video, entry: EvalEntry) -> _VideoInput:
    try:
        context: recipe_llm.VideoContext | None = pipeline.llm_context(video)
    except NoTranscriptError:
        context = None
    current = video.prompt_version == recipe_llm.PROMPT_VERSION
    return _VideoInput(
        video=video,
        youtube_id=video.youtube_id,
        expected_is_recipe=entry.expected_is_recipe,
        transcript=list(video.transcript or []),
        context=context,
        reference=video.generated_recipe if current else None,
        reference_prompt_version=video.prompt_version if current else None,
        stored_recipe=video.generated_recipe,
        stored_model=video.llm_model,
        stored_usage=dict(video.llm_usage or {}),
        stored_prompt_version=video.prompt_version,
    )


def _result(
    source: _VideoInput,
    trial: int,
    *,
    status: str,
    error_detail: str | None = None,
    recipe: dict[str, Any] | None = None,
    model: str | None = None,
    usage: dict[str, Any] | None = None,
    cost_usd: Decimal = Decimal(0),
    stop_reason: str | None = None,
    request_id: str | None = None,
    latency_ms: int | None = None,
    prompt_version: str | None = recipe_llm.PROMPT_VERSION,
) -> EvalResult:
    return EvalResult(
        youtube_id=source.youtube_id,
        trial=trial,
        status=status,
        error_detail=error_detail,
        recipe=recipe,
        model=model,
        usage=usage or {},
        cost_usd=cost_usd.quantize(_COST_STEP),
        stop_reason=stop_reason,
        request_id=request_id,
        latency_ms=latency_ms,
        checks=run_checks(
            recipe=recipe,
            stop_reason=stop_reason,
            error_code=None if status == "ok" else status,
            expected_is_recipe=source.expected_is_recipe,
            reference=source.reference,
            transcript=source.transcript,
        ),
        expected_is_recipe=source.expected_is_recipe,
        prompt_version=prompt_version,
        reference_prompt_version=source.reference_prompt_version,
    )


def _from_db(source: _VideoInput, trial: int) -> EvalResult:
    usage = source.stored_usage
    model = source.stored_model
    return _result(
        source,
        trial,
        status="ok" if source.stored_recipe is not None else "no_recipe",
        recipe=source.stored_recipe,
        model=model,
        usage=usage,
        cost_usd=quotas.llm_cost_usd(model, usage) if model and usage else Decimal(0),
        prompt_version=source.stored_prompt_version,
    )


async def _call(
    session: AsyncSession,
    source: _VideoInput,
    trial: int,
    config: LLMConfig,
    client: anthropic.AsyncAnthropic | None,
    results: list[EvalResult],
) -> EvalResult:
    """Uma chamada, com a reserva e o acerto do `pipeline.generate`; o `PipelineError` vira
    resultado. Não toca no `Video` nem no limite de tentativas dele."""
    assert source.context is not None
    try:
        pending = await llm_calls.start(
            session,
            source.video,
            purpose=LLMPurpose.EVAL,
            config=config,
            estimate=recipe_llm.estimate_prompt(source.context),
        )
    except LLMBudgetExceededError as exc:
        raise EvalBudgetExceeded(exc.detail or exc.message, results) from exc
    try:
        generation = await recipe_llm.generate_recipe(source.context, client=client, config=config)
    except PipelineError as exc:
        call = pending.call
        if exc.llm_usage is not None:
            llm_calls.finish(
                pending,
                model=exc.llm_model,
                usage=exc.llm_usage,
                error_code=exc.code,
                stop_reason=exc.llm_stop_reason,
                request_id=exc.llm_request_id,
            )
        elif exc.llm_maybe_billed:
            llm_calls.mark_timeout(pending)
        else:
            await llm_calls.discard(session, pending)
            return _result(source, trial, status=exc.code, error_detail=exc.detail)
        await session.commit()
        return _result(
            source,
            trial,
            status=exc.code,
            error_detail=exc.detail,
            model=call.model,
            usage=exc.llm_usage,
            cost_usd=call.cost_usd or Decimal(0),
            stop_reason=exc.llm_stop_reason,
            request_id=exc.llm_request_id,
            latency_ms=call.latency_ms,
        )
    except BaseException:
        # Cancelamento ou erro inesperado: não se sabe se a API cobrou; fica a estimativa.
        await llm_calls.mark_interrupted(session, pending)
        raise

    llm_calls.finish(
        pending,
        model=generation.model,
        usage=generation.usage,
        error_code=None,
        stop_reason=generation.stop_reason,
        request_id=generation.request_id,
    )
    await session.commit()
    return _result(
        source,
        trial,
        status="ok",
        recipe=generation.recipe.model_dump(mode="json"),
        model=generation.model,
        usage=generation.usage,
        cost_usd=pending.call.cost_usd or Decimal(0),
        stop_reason=generation.stop_reason,
        request_id=generation.request_id,
        latency_ms=pending.call.latency_ms,
        prompt_version=generation.prompt_version,
    )


def _config_dict(config: LLMConfig | None) -> dict[str, Any]:
    if config is None:
        return {"source": "db"}
    return {
        "model": config.model,
        "effort": config.effort,
        "max_tokens": config.max_tokens,
        "fallbacks": config.fallbacks,
        "cache_ttl": config.cache_ttl,
    }


def result_path(out_dir: Path, result: EvalResult, repeat: int) -> Path:
    if repeat == 1:
        return out_dir / f"{result.youtube_id}.json"
    return out_dir / f"{result.youtube_id}.trial{result.trial}.json"


def _write_result(out_dir: Path, result: EvalResult, config: LLMConfig | None, repeat: int) -> None:
    data = {
        "youtube_id": result.youtube_id,
        "trial": result.trial,
        "config": _config_dict(config),
        "prompt_version": result.prompt_version,
        "status": result.status,
        "error_detail": result.error_detail,
        "recipe": result.recipe,
        "model": result.model,
        "usage": result.usage,
        "cost_usd": str(result.cost_usd),
        "stop_reason": result.stop_reason,
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "checks": asdict(result.checks),
        "reference_prompt_version": result.reference_prompt_version,
    }
    result_path(out_dir, result, repeat).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


SUMMARY_COLUMNS = (
    "youtube_id",
    "trial",
    "status",
    "model",
    "effort",
    "max_tokens",
    "fallbacks",
    "cost_usd",
    "input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "output_tokens",
    "thinking_tokens",
    "stop_reason",
    "request_id",
    "latency_ms",
    "is_recipe",
    "expected_is_recipe",
    "is_recipe_ok",
    "cut_by_max_tokens",
    "source_tips",
    "foreign_steps",
    "imperial_outside_note",
    "ingredients",
    "ref_ingredients",
    "steps",
    "ref_steps",
    "groups",
    "ref_groups",
    "ts_pairs",
    "ts_mean_delta_s",
    "ts_mean_abs_delta_s",
    "ts_same_segment_share",
    "ts_out_of_order",
)


def _summary_row(result: EvalResult, config: LLMConfig | None) -> dict[str, Any]:
    usage, checks, ts = result.usage, result.checks, result.checks.timestamps
    return {
        "youtube_id": result.youtube_id,
        "trial": result.trial,
        "status": result.status,
        "model": result.model,
        "effort": config.effort if config else None,
        "max_tokens": config.max_tokens if config else None,
        "fallbacks": config.fallbacks if config else None,
        "cost_usd": result.cost_usd,
        "input_tokens": usage.get("input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "thinking_tokens": thinking_tokens(usage) if usage else None,
        "stop_reason": result.stop_reason,
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "is_recipe": checks.is_recipe,
        "expected_is_recipe": result.expected_is_recipe,
        "is_recipe_ok": checks.is_recipe_ok,
        "cut_by_max_tokens": checks.cut_by_max_tokens,
        "source_tips": checks.source_tips,
        "foreign_steps": checks.foreign_steps,
        "imperial_outside_note": checks.imperial_outside_note,
        "ingredients": checks.ingredients,
        "ref_ingredients": checks.ref_ingredients,
        "steps": checks.steps,
        "ref_steps": checks.ref_steps,
        "groups": checks.groups,
        "ref_groups": checks.ref_groups,
        "ts_pairs": ts.pairs,
        "ts_mean_delta_s": ts.mean_delta_s,
        "ts_mean_abs_delta_s": ts.mean_abs_delta_s,
        "ts_same_segment_share": ts.same_segment_share,
        "ts_out_of_order": ts.out_of_order,
    }


def _make_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_summary(out_dir: Path, results: list[EvalResult], config: LLMConfig | None) -> None:
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(_summary_row(result, config))


async def run_eval(
    session: AsyncSession,
    entries: list[EvalEntry],
    *,
    config: LLMConfig | None,
    repeat: int,
    out_dir: Path,
    client: anthropic.AsyncAnthropic | None = None,
    from_db: bool = False,
    progress: Callable[[str], None] = lambda _: None,
) -> list[EvalResult]:
    """Roda o eval e grava os resultados em `out_dir` (criado se não existe).

    `config` é a configuração avaliada (None com `from_db`). Levanta `EvalInputError` antes de
    qualquer chamada se um vídeo falta ou não tem transcrição, e `EvalBudgetExceeded` quando a
    próxima chamada não cabe no orçamento de eval (o `summary.csv` é gravado do mesmo jeito).
    A sessão precisa ter `expire_on_commit=False` (como `SessionLocal`): cada chamada faz commit
    e os vídeos seguintes são lidos depois.
    """
    if (config is None) != from_db:
        raise ValueError("config é obrigatório, a não ser com from_db")
    videos = await load_videos(session, entries)
    _make_dir(out_dir)
    results: list[EvalResult] = []
    try:
        for entry, video in zip(entries, videos, strict=True):
            source = _read_video(video, entry)
            for trial in range(1, repeat + 1):
                if source.context is None:
                    result = _result(
                        source,
                        trial,
                        status=NO_TRANSCRIPT,
                        error_detail="sem fala útil e descrição curta",
                    )
                elif from_db:
                    result = _from_db(source, trial)
                else:
                    assert config is not None
                    result = await _call(session, source, trial, config, client, results)
                results.append(result)
                _write_result(out_dir, result, config, repeat)
                progress(
                    f"{result.youtube_id} #{trial}: {result.status} (US$ {result.cost_usd:.4f})"
                )
    finally:
        write_summary(out_dir, results, config)
    return results


@dataclass(frozen=True, slots=True)
class EvalSummary:
    # Resultados que chegaram ao Claude (ou à receita gravada, com from_db).
    calls: int
    ok: int
    refused: int
    errors: int
    cost_usd: Decimal
    cost_per_ok_usd: Decimal | None
    p95_output: int | None
    thinking_share: float | None
    cache_hit_share: float | None
    # Resultados reprovados em cada checagem.
    failed_checks: dict[str, int]


def summarize(results: list[EvalResult]) -> EvalSummary:
    called = [result for result in results if result.status != NO_TRANSCRIPT]
    ok = sum(result.status == "ok" for result in called)
    refused = sum(result.status == ErrorCode.LLM_REFUSED for result in called)
    cost = sum((result.cost_usd for result in results), Decimal(0))
    priced = [result.usage for result in called if result.usage]
    outputs = [
        value
        for value in (usage.get("output_tokens") for usage in priced)
        if isinstance(value, int)
    ]
    thinking = sum(thinking_tokens(usage) for usage in priced)
    hits = sum((usage.get("cache_read_input_tokens") or 0) > 0 for usage in priced)
    checks = [result.checks for result in results]
    failed = {
        "is_recipe": sum(check.is_recipe_ok is False for check in checks),
        "cut_by_max_tokens": sum(check.cut_by_max_tokens for check in checks),
        "source_tips": sum(check.source_tips > 0 for check in checks),
        "foreign_steps": sum(check.foreign_steps > 0 for check in checks),
        "imperial_outside_note": sum(check.imperial_outside_note > 0 for check in checks),
        "ts_out_of_order": sum(check.timestamps.out_of_order > 0 for check in checks),
        "ts_off_segment": sum(
            check.timestamps.same_segment_share is not None
            and check.timestamps.same_segment_share < 1
            for check in checks
        ),
    }
    return EvalSummary(
        calls=len(called),
        ok=ok,
        refused=refused,
        errors=len(called) - ok - refused,
        cost_usd=cost,
        cost_per_ok_usd=cost / ok if ok else None,
        p95_output=nearest_rank(outputs, 0.95),
        thinking_share=thinking / sum(outputs) if sum(outputs) else None,
        cache_hit_share=hits / len(priced) if priced else None,
        failed_checks=failed,
    )
