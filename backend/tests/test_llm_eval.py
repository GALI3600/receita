"""Eval da geração (`llm_eval` e `python -m app.cli llm-eval`), sempre com a API falsa."""

import asyncio
import csv
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cli
from app.config import Settings
from app.errors import ErrorCode
from app.models import LLMCall, LLMPurpose, Video
from app.models.llm_call import LLM_CALL_TIMEOUT
from app.schemas.transcript import Segment, TranscriptSource
from app.services import llm_eval, recipe_llm
from app.services.llm_eval import (
    EvalEntry,
    EvalInputError,
    is_foreign_text,
    parse_ids,
    run_checks,
    run_eval,
)
from app.services.recipe_llm import LLMConfig
from tests.factories import GENERATED, SPEECH, make_video, youtube_id
from tests.test_recipe_llm import RECIPE, USAGE, FakeAPI, _message, _ok

REFUSAL = _message(
    content=[],
    stop_reason="refusal",
    stop_details={"type": "refusal", "category": "bio", "explanation": None},
)


class _Engine:
    async def dispose(self) -> None:
        pass


def _entries(*ids: str) -> list[EvalEntry]:
    return [EvalEntry(youtube_id, True) for youtube_id in ids]


async def _eval_calls(session: AsyncSession) -> list[LLMCall]:
    calls = list(await session.scalars(select(LLMCall).order_by(LLMCall.started_at)))
    await session.commit()
    return calls


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


def _summary(out_dir: Path) -> list[dict[str, str]]:
    with (out_dir / "summary.csv").open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


# --- Arquivo de ids ---------------------------------------------------------------------------


def test_parse_ids() -> None:
    text = """
    # comentário
    88syMwVL0dk true

    bXHUoszxL6A FALSE
    -pRC-FQXLEI
    _T6jkRvhlkk True
    """
    assert parse_ids(text) == [
        EvalEntry("88syMwVL0dk", True),
        EvalEntry("bXHUoszxL6A", False),
        EvalEntry("-pRC-FQXLEI", None),
        EvalEntry("_T6jkRvhlkk", True),
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("88syMwVL0dk true\nhttps://youtu.be/x40o71KuLtQ", "linha 2"),
        ("88syMwVL0d", "linha 1"),
        ("88syMwVL0dk sim", "true ou false"),
        ("88syMwVL0dk true extra", "linha 1"),
        ("88syMwVL0dk\n# outro\n88syMwVL0dk false", "linha 3: 88syMwVL0dk repetido"),
    ],
    ids=["url", "id-curto", "esperado-invalido", "campo-a-mais", "repetido"],
)
def test_parse_ids_rejects_bad_lines(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_ids(text)


def test_the_eval_set_is_valid() -> None:
    entries = parse_ids((Path(__file__).parents[1] / "evals" / "ids.txt").read_text())
    assert len(entries) == 17
    assert [e.youtube_id for e in entries if e.expected_is_recipe is False] == ["bXHUoszxL6A"]


# --- Checagens --------------------------------------------------------------------------------


def _checks(recipe: dict[str, Any], **kwargs: Any) -> llm_eval.Checks:
    defaults: dict[str, Any] = {
        "stop_reason": "end_turn",
        "error_code": None,
        "expected_is_recipe": True,
        "reference": None,
        "transcript": [],
    }
    return run_checks(recipe=recipe, **(defaults | kwargs))


def test_source_mentions() -> None:
    tips = [
        "O vídeo não informa a quantidade.",
        "A descrição diz 200 g.",
        "Como dito na fala, mexa sem parar.",
        "Use fermento químico se não tiver o biológico.",
        "Guarde na geladeira por até 3 dias.",
    ]
    assert _checks({**GENERATED, "tips": tips}).source_tips == 3
    assert _checks(GENERATED).source_tips == 0


def test_foreign_steps() -> None:
    assert is_foreign_text("Add the flour and stir until smooth.")
    assert is_foreign_text("Agregue la harina y mezcle hasta que esté suave.")
    assert not is_foreign_text("Bata as cenouras com os ovos até virar um creme.")
    assert not is_foreign_text("Misture o mix de castanhas.")
    # Imperativo de tú e passos curtos em inglês.
    assert is_foreign_text("Agrega la harina y mezcla bien.")
    assert is_foreign_text("Hornea a 180 °C por 30 minutos en el horno.")
    assert is_foreign_text("Bake for 20 minutes.")
    assert not is_foreign_text("Leve à geladeira e depois leve-a ao forno a 180 °C.")
    assert not is_foreign_text("Cubra a massa e deixe-la descansar por 30 minutos na geladeira.")
    assert _checks(RECIPE).foreign_steps == 0
    english = {"order": 3, "text": "Bake it until golden.", "video_timestamp_s": 1}
    steps = [*RECIPE["steps"], english]
    assert _checks({**RECIPE, "steps": steps}).foreign_steps == 1


def test_imperial_units() -> None:
    def ingredient(quantity: str, unit: str | None, note: str | None) -> dict[str, Any]:
        return {"name": "farinha", "quantity": quantity, "unit": unit, "note": note, "group": None}

    def step(text: str) -> dict[str, Any]:
        return {"order": 1, "text": text, "video_timestamp_s": None}

    recipe = {
        **GENERATED,
        "ingredients": [ingredient("7", "oz", None), ingredient("200", "g", "≈ 7 oz")],
        "steps": [
            step("Pese 70 a 85 g (2½ a 3 oz) de massa."),
            step("Asse a 350 °F."),
            # "º" (indicador ordinal) no lugar do grau, comum em português.
            step("Asse a 180 ºC (350 °F) por 40 minutos."),
            step("Asse a 350 ºF."),
        ],
    }
    assert _checks(recipe).imperial_outside_note == 3
    assert _checks(GENERATED).imperial_outside_note == 0


def test_groups_count_each_preparation_once() -> None:
    def ingredient(group: str | None) -> dict[str, Any]:
        return {"name": "x", "quantity": None, "unit": None, "note": None, "group": group}

    recipe = {
        **GENERATED,
        "ingredients": [
            ingredient("marmita 1 – tutu de feijão"),
            ingredient("marmita 1 – acompanhamentos"),
            ingredient("marmita 2 – mexidão"),
            ingredient("Massa"),
            ingredient("massa"),
        ],
    }
    checks = _checks(recipe, reference=GENERATED)
    assert (checks.groups, checks.ref_groups) == (3, 1)
    assert (checks.ingredients, checks.ref_ingredients) == (5, 2)


def test_is_recipe_and_cut_checks() -> None:
    assert _checks(GENERATED, expected_is_recipe=False).is_recipe_ok is False
    assert _checks(GENERATED, expected_is_recipe=None).is_recipe_ok is None
    failure = run_checks(
        recipe=None,
        stop_reason=None,
        error_code=ErrorCode.LLM_OUTPUT_TOO_LONG,
        expected_is_recipe=True,
        reference=GENERATED,
        transcript=[],
    )
    assert (failure.is_recipe, failure.is_recipe_ok, failure.cut_by_max_tokens) == (
        None,
        None,
        True,
    )
    assert (failure.steps, failure.ref_steps) == (0, 2)
    assert _checks(GENERATED, stop_reason="max_tokens").cut_by_max_tokens


def test_timestamp_check() -> None:
    transcript = [Segment(start=s + 0.6, end=s + 9.0, text="x") for s in range(0, 100, 10)]

    def recipe(*timestamps: int | None) -> dict[str, Any]:
        steps = [
            {"order": i, "text": "Mexa.", "video_timestamp_s": ts}
            for i, ts in enumerate(timestamps, start=1)
        ]
        return {**GENERATED, "steps": steps}

    # Trechos começando em 0, 10, ..., 90. Referência nos trechos 1, 3 e 5 (o 4º passo sem
    # timestamp); o novo cai no mesmo trecho, um depois e três depois.
    new = recipe(12, 41, 85, 30)
    reference = recipe(10, 30, 55, None)
    check = llm_eval.check_timestamps(new, reference, transcript)
    assert check.pairs == 3
    assert check.mean_delta_s == pytest.approx((2 + 11 + 30) / 3)
    assert check.mean_abs_delta_s == pytest.approx((2 + 11 + 30) / 3)
    assert check.same_segment_share == pytest.approx(2 / 3)
    assert check.out_of_order == 1  # 30 depois de 85

    early = llm_eval.check_timestamps(recipe(8, None, 20), recipe(12, 25, 22), transcript)
    assert (early.pairs, early.mean_delta_s, early.out_of_order) == (2, -3.0, 0)

    alone = llm_eval.check_timestamps(new, None, transcript)
    assert (alone.pairs, alone.mean_delta_s, alone.mean_abs_delta_s) == (0, None, None)
    assert (alone.same_segment_share, alone.out_of_order) == (None, 1)


# --- Estimativa e CLI sem --yes ---------------------------------------------------------------


def _video(**overrides: Any) -> Video:
    fields: dict[str, Any] = {
        "youtube_id": "abcdefghijk",
        "title": "Bolo",
        "channel": "Receitas",
        "duration_s": 600,
        "description": "",
        "embeddable": True,
        "transcript": SPEECH,
        "transcript_source": TranscriptSource.MANUAL,
    }
    return Video(**(fields | overrides))


def test_eval_estimate(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_reserved_output_tokens", 12_000)
    config = LLMConfig()
    with_reference = _video(llm_usage={"output_tokens": 3000})
    silent = _video(youtube_id="silentvideo", transcript=[], description="curta")

    one = llm_eval.estimate([with_reference], config, repeat=1)
    assert one.calls == 1
    assert one.ceiling_usd > one.typical_usd > 0
    assert llm_eval.estimate([with_reference, silent], config, repeat=1) == one

    # A saída da referência passa de max_tokens: a típica fica no teto, que a API corta.
    capped = LLMConfig(max_tokens=2000)
    long_reference = _video(llm_usage={"output_tokens": 10_000})
    cut = llm_eval.estimate([long_reference], capped, repeat=1)
    assert cut.typical_usd == cut.ceiling_usd

    # Sem referência, a saída típica é a reservada; a 2ª chamada lê o prefixo do cache.
    two = llm_eval.estimate([_video()], config, repeat=2)
    assert two.calls == 2
    assert two.typical_usd < 2 * llm_eval.estimate([_video()], config, repeat=1).typical_usd
    assert two.ceiling_usd == 2 * llm_eval.estimate([_video()], config, repeat=1).ceiling_usd


@pytest.fixture
def cli_db(
    monkeypatch: pytest.MonkeyPatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """O CLI com o banco de teste (rodando em outra thread, com outro event loop)."""
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "engine", _Engine())


def _ids_file(tmp_path: Path, *ids: str) -> str:
    path = tmp_path / "ids.txt"
    path.write_text("".join(f"{youtube_id} true\n" for youtube_id in ids))
    return str(path)


async def test_cli_eval_without_yes_only_estimates(
    session: AsyncSession,
    cli_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await make_video(session, youtube_id(1))
    api = FakeAPI(_ok(_message()))
    monkeypatch.setattr(recipe_llm, "get_client", api.client)
    out_dir = tmp_path / "out"
    argv = ["llm-eval", "--ids", _ids_file(tmp_path, youtube_id(1)), "--out", str(out_dir)]

    code = await asyncio.to_thread(
        cli.main, [*argv, "--model", "claude-opus-5-5", "--effort", "medium"]
    )

    assert code == 1
    out = capsys.readouterr().out
    assert "estimativa: 1 chamada(s)" in out
    assert "EVAL_DAILY_LLM_BUDGET_USD" in out
    assert "passe --yes para rodar" in out
    assert api.requests == []
    assert not out_dir.exists()
    assert await _eval_calls(session) == []


@pytest.mark.parametrize(
    "extra",
    [
        ["--from-db", "--model", "claude-opus-5-5"],
        ["--model", "claude-opus-5-5"],
        ["--model", "claude-opus-5-5", "--effort", "low", "--max-tokens", "21334"],
        ["--model", "claude-opus-5-5", "--effort", "low", "--repeat", "0"],
    ],
    ids=["from-db-com-config", "sem-effort", "max-tokens-com-streaming", "repeat-zero"],
)
def test_cli_eval_rejects_bad_arguments(extra: list[str], tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["llm-eval", "--ids", "ids.txt", "--out", str(tmp_path), *extra])
    assert exc_info.value.code == 2


def test_cli_eval_refuses_existing_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "summary.csv").write_text("")
    argv = ["llm-eval", "--ids", _ids_file(tmp_path, youtube_id(1)), "--out", str(tmp_path)]

    assert cli.main([*argv, "--from-db"]) == 1
    assert "já existe" in capsys.readouterr().err


async def test_cli_eval_without_server_fallback_model(
    session: AsyncSession,
    cli_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await make_video(session, youtube_id(1))
    api = FakeAPI(_ok(_message(model="claude-haiku-5-5")))
    monkeypatch.setattr(recipe_llm, "get_client", api.client)
    argv = ["llm-eval", "--ids", _ids_file(tmp_path, youtube_id(1)), "--out", str(tmp_path / "o")]

    code = await asyncio.to_thread(
        cli.main, [*argv, "--model", "claude-haiku-5-5", "--effort", "none", "--yes"]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "sem fallback do servidor para claude-haiku-5-5" in out
    assert "chamadas: 1  ok: 1" in out
    assert len(api.requests) == 1
    assert "fallbacks" not in api.body
    assert "anthropic-beta" not in api.requests[0].headers
    assert "effort" not in api.body["output_config"]
    [call] = await _eval_calls(session)
    assert (call.purpose, call.model, call.effort) == (LLMPurpose.EVAL, "claude-haiku-5-5", None)


# --- Execução ---------------------------------------------------------------------------------


async def test_eval_run_writes_results_and_never_touches_video(
    session: AsyncSession, tmp_path: Path
) -> None:
    first = await make_video(session, youtube_id(1), llm_usage={"output_tokens": 50})
    second = await make_video(session, youtube_id(2), prompt_version="2026-01-01.1")
    before = [
        (v.generated_recipe, v.llm_model, v.llm_usage, v.prompt_version) for v in (first, second)
    ]
    api = FakeAPI(_ok(_message()), _ok(REFUSAL))
    config = LLMConfig(effort="low", max_tokens=8000)

    results = await run_eval(
        session,
        _entries(youtube_id(1), youtube_id(2)),
        config=config,
        repeat=1,
        out_dir=tmp_path,
        client=api.client(),
    )

    assert [r.status for r in results] == ["ok", "llm_refused"]
    assert [r.trial for r in results] == [1, 1]
    ok, refused = results
    assert ok.recipe is not None and ok.recipe["title"] == "Bolo de cenoura"
    assert (ok.usage, ok.request_id, ok.stop_reason) == (USAGE, "req_test", "end_turn")
    assert ok.cost_usd > 0 and ok.latency_ms is not None
    # Referência só com o prompt atual: o 2º vídeo foi gerado com outro.
    assert ok.checks.ref_steps == 2 and ok.checks.steps == 2
    assert refused.checks.ref_steps is None and refused.recipe is None
    assert refused.cost_usd > 0

    data = json.loads((tmp_path / f"{youtube_id(1)}.json").read_text())
    assert data["config"] == {
        "model": "claude-opus-5-5",
        "effort": "low",
        "max_tokens": 8000,
        "fallbacks": True,
        "cache_ttl": "5m",
    }
    assert data["prompt_version"] == recipe_llm.PROMPT_VERSION
    assert data["reference_prompt_version"] == recipe_llm.PROMPT_VERSION
    assert data["checks"]["timestamps"]["pairs"] == 1
    assert Decimal(data["cost_usd"]) == ok.cost_usd
    failed = json.loads((tmp_path / f"{youtube_id(2)}.json").read_text())
    assert (failed["status"], failed["reference_prompt_version"]) == ("llm_refused", None)

    rows = _summary(tmp_path)
    assert list(rows[0]) == list(llm_eval.SUMMARY_COLUMNS)
    assert [(r["youtube_id"], r["status"], r["effort"], r["max_tokens"]) for r in rows] == [
        (youtube_id(1), "ok", "low", "8000"),
        (youtube_id(2), "llm_refused", "low", "8000"),
    ]
    assert rows[0]["thinking_tokens"] == "0" and rows[0]["cache_read_tokens"] == "1100"

    calls = await _eval_calls(session)
    assert [(c.purpose, c.error_code) for c in calls] == [
        (LLMPurpose.EVAL, None),
        (LLMPurpose.EVAL, "llm_refused"),
    ]
    assert {(c.effort, c.max_tokens, c.cache_marker) for c in calls} == {("low", 8000, "5m")}
    assert calls[0].request_id == "req_test"

    for video in (first, second):
        await session.refresh(video)
    after = [
        (v.generated_recipe, v.llm_model, v.llm_usage, v.prompt_version) for v in (first, second)
    ]
    assert after == before


async def test_eval_repeat_names_trials(session: AsyncSession, tmp_path: Path) -> None:
    await make_video(session, youtube_id(1))
    api = FakeAPI(_ok(_message()))

    results = await run_eval(
        session,
        _entries(youtube_id(1)),
        config=LLMConfig(),
        repeat=2,
        out_dir=tmp_path,
        client=api.client(),
    )

    assert [r.trial for r in results] == [1, 2]
    assert _names(tmp_path) == [
        "summary.csv",
        f"{youtube_id(1)}.trial1.json",
        f"{youtube_id(1)}.trial2.json",
    ]
    assert len(api.requests) == 2
    assert len(_summary(tmp_path)) == 2


async def test_eval_stops_when_eval_budget_runs_out(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "eval_daily_llm_budget_usd", 0.0)
    video = await make_video(session, youtube_id(1))
    api = FakeAPI(_ok(_message()))

    with pytest.raises(llm_eval.EvalBudgetExceeded) as exc_info:
        await run_eval(
            session,
            _entries(youtube_id(1)),
            config=LLMConfig(),
            repeat=1,
            out_dir=tmp_path,
            client=api.client(),
        )

    assert exc_info.value.results == []
    assert api.requests == []
    assert _summary(tmp_path) == []
    assert (tmp_path / "summary.csv").read_text().startswith("youtube_id,trial,status")
    assert await _eval_calls(session) == []
    # A recusa da reserva não expirou o vídeo carregado na sessão.
    assert video.youtube_id == youtube_id(1)


async def test_eval_ignores_production_spend(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "daily_llm_budget_usd", 1.0)
    video = await make_video(session, youtube_id(1))
    session.add(
        LLMCall(
            video_id=video.id,
            model="claude-opus-5-5",
            prompt_version=recipe_llm.PROMPT_VERSION,
            usage={},
            purpose=LLMPurpose.IMPORT,
            cost_usd=Decimal(5),
        )
    )
    await session.commit()
    api = FakeAPI(_ok(_message()))

    results = await run_eval(
        session,
        _entries(youtube_id(1)),
        config=LLMConfig(),
        repeat=1,
        out_dir=tmp_path,
        client=api.client(),
    )

    assert [r.status for r in results] == ["ok"]
    assert len(api.requests) == 1


async def test_eval_refuses_videos_without_transcript(
    session: AsyncSession, tmp_path: Path
) -> None:
    await make_video(session, youtube_id(1))
    await make_video(session, youtube_id(2), transcript=None)
    api = FakeAPI(_ok(_message()))

    with pytest.raises(EvalInputError) as exc_info:
        await run_eval(
            session,
            _entries(youtube_id(1), youtube_id(2), youtube_id(3)),
            config=LLMConfig(),
            repeat=1,
            out_dir=tmp_path,
            client=api.client(),
        )

    assert f"fora do banco: {youtube_id(3)}" in str(exc_info.value)
    assert f"sem transcrição: {youtube_id(2)}" in str(exc_info.value)
    assert api.requests == []
    assert _names(tmp_path) == []


async def test_eval_skips_video_that_would_not_reach_claude(
    session: AsyncSession, tmp_path: Path
) -> None:
    await make_video(session, youtube_id(1), transcript=[])
    api = FakeAPI(_ok(_message()))

    [result] = await run_eval(
        session,
        _entries(youtube_id(1)),
        config=LLMConfig(),
        repeat=1,
        out_dir=tmp_path,
        client=api.client(),
    )

    assert (result.status, result.cost_usd) == ("no_transcript", Decimal(0))
    assert api.requests == []
    assert llm_eval.summarize([result]).calls == 0


async def test_eval_from_db_makes_no_calls(session: AsyncSession, tmp_path: Path) -> None:
    await make_video(session, youtube_id(1), llm_usage=USAGE)
    api = FakeAPI(_ok(_message()))

    [result] = await run_eval(
        session,
        _entries(youtube_id(1)),
        config=None,
        repeat=1,
        out_dir=tmp_path,
        client=api.client(),
        from_db=True,
    )

    assert (result.status, result.recipe, result.usage) == ("ok", GENERATED, USAGE)
    assert result.cost_usd > 0
    assert (result.checks.steps, result.checks.ref_steps, result.checks.is_recipe_ok) == (
        2,
        2,
        True,
    )
    assert result.checks.timestamps.same_segment_share == 1
    data = json.loads((tmp_path / f"{youtube_id(1)}.json").read_text())
    assert data["config"] == {"source": "db"}
    assert api.requests == []
    assert await _eval_calls(session) == []


async def test_eval_billed_timeout_is_a_result(session: AsyncSession, tmp_path: Path) -> None:
    await make_video(session, youtube_id(1))
    await make_video(session, youtube_id(2))
    api = FakeAPI(error=httpx2.ReadTimeout("lento"))

    results = await run_eval(
        session,
        _entries(youtube_id(1), youtube_id(2)),
        config=LLMConfig(),
        repeat=1,
        out_dir=tmp_path,
        client=api.client(),
    )

    assert [r.status for r in results] == ["llm_unavailable"] * 2
    assert all(r.cost_usd > 0 for r in results)
    calls = await _eval_calls(session)
    assert [c.error_code for c in calls] == [LLM_CALL_TIMEOUT] * 2
    assert [r.cost_usd for r in results] == [round(c.cost_usd, 6) for c in calls]


def test_summarize() -> None:
    def result(status: str, usage: dict[str, Any], cost: str, **checks: Any) -> Any:
        base = _checks(GENERATED)
        return llm_eval.EvalResult(
            youtube_id="abcdefghijk",
            trial=1,
            status=status,
            error_detail=None,
            recipe=None,
            model="claude-opus-5-5",
            usage=usage,
            cost_usd=Decimal(cost),
            stop_reason=None,
            request_id=None,
            latency_ms=None,
            checks=replace(base, **checks),
        )

    thinking = {"output_tokens_details": {"thinking_tokens": 100}}
    summary = llm_eval.summarize(
        [
            result("ok", {"output_tokens": 400, "cache_read_input_tokens": 10, **thinking}, "0.3"),
            result("ok", {"output_tokens": 600}, "0.1", source_tips=2),
            result("llm_refused", {"output_tokens": 0}, "0.2"),
            result("llm_unavailable", {}, "0.1"),
            result("no_transcript", {}, "0"),
        ]
    )
    assert (summary.calls, summary.ok, summary.refused, summary.errors) == (4, 2, 1, 1)
    assert summary.cost_usd == Decimal("0.7")
    assert summary.cost_per_ok_usd == Decimal("0.35")
    assert summary.p95_output == 600
    assert summary.thinking_share == pytest.approx(0.1)
    assert summary.cache_hit_share == pytest.approx(1 / 3)
    assert summary.failed_checks["source_tips"] == 1
    assert summary.failed_checks["is_recipe"] == 0
