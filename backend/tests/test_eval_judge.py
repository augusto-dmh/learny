"""D3 gate — LLM judge harness (unit, fake client, no network) + live smoke.

Derived from GEN-21 and the D3 Done-when: faithfulness aggregates claim labels to
a supported ratio; relevancy parses the integer score; ``run_eval`` writes one
JSONL line per case with the full schema (case id, timestamps, model ids, prompt
hash, scores, citation flag), caps at ``max_cases``, and is report-only unless the
gate is on; the SDK is imported lazily. A ``live and eval`` smoke runs the real
judge over one inline case and is skipped without a key (the nightly's judge tier).
"""

from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path

import pytest

from app.eval import judge as judge_module
from app.eval.judge import (
    FAITHFULNESS_MIN,
    RELEVANCY_MIN,
    Claim,
    EvalInput,
    FaithfulnessResult,
    Judge,
    prompt_hash,
    run_eval,
)

_JUDGE_MODEL = "claude-haiku-4-5"


# --- Fake Anthropic client: returns a canned JSON payload as one text block ------


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, payload: dict) -> None:
        self.content = [_FakeTextBlock(json.dumps(payload))]


class _FakeMessagesResource:
    """Returns queued payloads in order (faithfulness then relevancy per case)."""

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeMessage:
        self.calls.append(kwargs)
        return _FakeMessage(self._payloads.pop(0))


class _FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.messages = _FakeMessagesResource(payloads)


def _judge(payloads: list[dict]) -> tuple[Judge, _FakeClient]:
    client = _FakeClient(payloads)
    return Judge(api_key="unused-fake", model=_JUDGE_MODEL, client=client), client


def _faithfulness_payload(*supported: bool) -> dict:
    return {
        "claims": [
            {"claim": f"claim {i}", "supported": flag} for i, flag in enumerate(supported)
        ]
    }


# --- Faithfulness ratio math (GEN-21) ------------------------------------------


def test_faithfulness_ratio_counts_supported_claims() -> None:
    judge, client = _judge([_faithfulness_payload(True, False, True)])

    result = judge.faithfulness(question="q", evidence="passages", answer="a")

    assert isinstance(result, FaithfulnessResult)
    assert result.claims == (
        Claim("claim 0", True),
        Claim("claim 1", False),
        Claim("claim 2", True),
    )
    assert result.supported_ratio == pytest.approx(2 / 3)
    # The judge call carried structured-outputs json_schema, no citations documents.
    call = client.messages.calls[0]
    assert call["model"] == _JUDGE_MODEL
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["format"]["schema"]["additionalProperties"] is False


def test_faithfulness_ratio_is_one_when_no_claims() -> None:
    judge, _ = _judge([_faithfulness_payload()])

    result = judge.faithfulness(question="q", evidence="passages", answer="")

    # A not-found decline asserts nothing, so it is vacuously faithful.
    assert result.claims == ()
    assert result.supported_ratio == 1.0


# --- Relevancy parse (GEN-21) --------------------------------------------------


def test_relevancy_parses_integer_score() -> None:
    judge, client = _judge([{"score": 4}])

    score = judge.relevancy(question="q", answer="a")

    assert score == 4
    assert client.messages.calls[0]["output_config"]["format"]["schema"]["properties"][
        "score"
    ]["enum"] == [1, 2, 3, 4, 5]


# --- JSONL result schema (GEN-21) ----------------------------------------------


def _inputs(n: int, *, citation_valid: bool = True) -> list[EvalInput]:
    return [
        EvalInput(
            case_id=f"case-{i}",
            question=f"q{i}",
            evidence_text="passages",
            answer_text=f"a{i}",
            generation_model="claude-sonnet-4-6",
            citation_valid=citation_valid,
        )
        for i in range(n)
    ]


def test_run_eval_writes_jsonl_line_per_case_with_full_schema(tmp_path: Path) -> None:
    # Two cases → four judge calls (faithfulness, relevancy) each.
    judge, _ = _judge(
        [
            _faithfulness_payload(True, True),
            {"score": 5},
            _faithfulness_payload(True, False),
            {"score": 3},
        ]
    )

    lines = run_eval(
        _inputs(2), judge=judge, max_cases=10, results_dir=tmp_path, gate=False
    )

    assert len(lines) == 2
    # Exactly one JSONL file was written, one line per case.
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    written = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(written) == 2
    first = written[0]
    assert set(first) == {
        "case_id",
        "ts",
        "git_sha",
        "generation_model",
        "judge_model",
        "prompt_hash",
        "faithfulness",
        "relevancy",
        "citation_valid",
    }
    assert first["case_id"] == "case-0"
    assert first["generation_model"] == "claude-sonnet-4-6"
    assert first["judge_model"] == _JUDGE_MODEL
    assert first["prompt_hash"] == prompt_hash()
    assert first["faithfulness"] == 1.0
    assert first["relevancy"] == 5
    assert first["citation_valid"] is True
    assert written[1]["faithfulness"] == pytest.approx(0.5)
    assert written[1]["relevancy"] == 3


# --- max_cases cap (GEN-21 / research §8 cost cap) -----------------------------


def test_run_eval_caps_at_max_cases(tmp_path: Path) -> None:
    # Five inputs, cap 2 → only two cases judged (two calls each).
    judge, client = _judge(
        [_faithfulness_payload(True), {"score": 5}, _faithfulness_payload(True), {"score": 5}]
    )

    lines = run_eval(
        _inputs(5), judge=judge, max_cases=2, results_dir=tmp_path, gate=False
    )

    assert len(lines) == 2
    assert len(client.messages.calls) == 4  # never touched the remaining three cases


# --- Gate off = report-only; gate on asserts (GEN-21) --------------------------


def test_gate_off_is_report_only_even_below_threshold(tmp_path: Path) -> None:
    # A wholly unfaithful, irrelevant case must not raise when the gate is off.
    judge, _ = _judge([_faithfulness_payload(False), {"score": 1}])

    lines = run_eval(
        _inputs(1), judge=judge, max_cases=10, results_dir=tmp_path, gate=False
    )

    assert lines[0]["faithfulness"] == 0.0
    assert lines[0]["relevancy"] == 1
    assert lines[0]["faithfulness"] < FAITHFULNESS_MIN
    assert lines[0]["relevancy"] < RELEVANCY_MIN


def test_gate_on_asserts_aggregate_thresholds(tmp_path: Path) -> None:
    judge, _ = _judge([_faithfulness_payload(False), {"score": 1}])

    with pytest.raises(AssertionError):
        run_eval(_inputs(1), judge=judge, max_cases=10, results_dir=tmp_path, gate=True)


def test_gate_trips_on_faithfulness_alone(tmp_path: Path) -> None:
    # Relevancy clears its threshold (5 >= RELEVANCY_MIN); only faithfulness is
    # below the bar — the gate must still raise, proving that comparison is
    # individually load-bearing.
    judge, _ = _judge([_faithfulness_payload(False), {"score": 5}])

    with pytest.raises(AssertionError, match="faithfulness"):
        run_eval(_inputs(1), judge=judge, max_cases=10, results_dir=tmp_path, gate=True)


def test_gate_trips_on_relevancy_alone(tmp_path: Path) -> None:
    # Faithfulness clears its threshold (1.0 >= FAITHFULNESS_MIN); only
    # relevancy is below the bar — the gate must still raise.
    judge, _ = _judge([_faithfulness_payload(True), {"score": 1}])

    with pytest.raises(AssertionError, match="relevancy"):
        run_eval(_inputs(1), judge=judge, max_cases=10, results_dir=tmp_path, gate=True)


def test_gate_trips_on_citation_validity_alone(tmp_path: Path) -> None:
    # Faithfulness and relevancy both clear their thresholds; only a citation
    # failure remains — the gate's third branch must be individually
    # load-bearing too.
    judge, _ = _judge([_faithfulness_payload(True), {"score": 5}])

    with pytest.raises(AssertionError, match="citation"):
        run_eval(
            _inputs(1, citation_valid=False),
            judge=judge,
            max_cases=10,
            results_dir=tmp_path,
            gate=True,
        )


def test_gate_passes_on_baseline_aggregates(tmp_path: Path) -> None:
    # All three branches clear: the gate must NOT raise. This is the case that
    # kills an inverted comparison in any branch (an inverted assert fires on
    # good aggregates, where the single-failure cases cannot see it).
    judge, _ = _judge([_faithfulness_payload(True), {"score": 5}])

    lines = run_eval(
        _inputs(1), judge=judge, max_cases=10, results_dir=tmp_path, gate=True
    )

    assert lines[0]["faithfulness"] == 1.0
    assert lines[0]["relevancy"] == 5
    assert lines[0]["citation_valid"] is True


def test_gate_constants_pin_the_calibrated_baselines() -> None:
    # The 2026-07-18 calibration (docs/ops/eval-calibration.md): observed mean
    # minus the safety margin. A drive-by edit to either constant silently
    # re-arms or disarms the nightly gate, so the derived values are pinned
    # here exactly like the model default is pinned in test_config.py.
    assert FAITHFULNESS_MIN == 0.90
    assert RELEVANCY_MIN == 2.5


def test_gate_defaults_to_env_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEARNY_EVAL_GATE", "1")
    judge, _ = _judge([_faithfulness_payload(False), {"score": 1}])

    with pytest.raises(AssertionError):
        # gate=None → read LEARNY_EVAL_GATE, which is "1".
        run_eval(_inputs(1), judge=judge, max_cases=10, results_dir=tmp_path)


# --- Lazy SDK import (GEN-03) --------------------------------------------------


def test_judge_module_imports_no_sdk_at_module_level() -> None:
    tree = ast.parse(inspect.getsource(judge_module))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])

    assert "anthropic" not in top_level


# --- Live judge smoke (nightly judge tier) — skipped without a key -------------


@pytest.mark.live
@pytest.mark.eval
@pytest.mark.skipif(
    not os.getenv("LEARNY_ANTHROPIC_API_KEY"),
    reason="LEARNY_ANTHROPIC_API_KEY unset — live judge smoke skipped (CI stays offline)",
)
def test_live_judge_scores_one_case() -> None:
    # Writes to the real evals/results/ dir (the default) so the nightly run
    # produces the results JSONL the workflow uploads as an artifact (GEN-22).
    # Live-only, so an offline run never touches the repo tree.
    from app.core.config import get_settings

    settings = get_settings()
    judge = Judge(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"], model=settings.judge_model
    )
    evidence = (
        "Ocean tides rise and fall because the moon's gravity pulls seawater "
        "across the planet."
    )
    grounded = EvalInput(
        case_id="live-tides",
        question="Why do ocean tides rise and fall?",
        evidence_text=evidence,
        answer_text="Ocean tides rise and fall because the moon's gravity pulls seawater.",
        generation_model=settings.generation_model,
        citation_valid=True,
    )

    lines = run_eval([grounded], judge=judge, max_cases=settings.eval_max_cases)

    assert len(lines) == 1
    assert 0.0 <= lines[0]["faithfulness"] <= 1.0
    assert lines[0]["relevancy"] in range(1, 6)
