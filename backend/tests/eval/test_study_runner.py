"""Unit tests for the generation A/B study runner (`tests.eval.study`).

All fakes — no network, no DB, no keys. The runner's contract under test:
per-unit checkpoint append (DENOISE-04), resume skip / error re-attempt
(DENOISE-05), prompt-hash & judge-model mismatch refusal (DENOISE-06), decline
and error handling (DENOISE-07), the tracked-golden / ignored-silver artifact
split (DENOISE-08), and the modeled-cost budget stop (DENOISE-14).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.eval.harness import EvalCase, SnapshotEvidence
from tests.eval.study import (
    CostModel,
    StudyMismatchError,
    StudyUnit,
    load_recorded,
    per_run_aggregates,
    plan_units,
    run_study,
    score_golden_unit,
)

_PHASH = "ph-current"
_JUDGE = "claude-opus-4-8"


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "golden.jsonl", tmp_path / "silver.jsonl"


def _cost(gen: float = 0.01, judge: float = 0.01) -> CostModel:
    return CostModel(
        generation_usd_per_unit={"claude-sonnet-5": gen, "claude-opus-4-8": gen},
        judge_usd_per_unit=judge,
    )


def _ok_fields(arm: str = "claude-sonnet-5") -> dict:
    return {
        "status": "ok",
        "generation_model": arm,
        "judge_model": _JUDGE,
        "prompt_hash": _PHASH,
        "faithfulness": 1.0,
        "relevancy": 4,
        "citation_valid": True,
        "found": True,
    }


class RecordingScorer:
    """A fake per-unit scorer that records which units it was asked to score."""

    def __init__(self, fields=None, boom_on=None, interrupt_on=None):
        self.calls: list[StudyUnit] = []
        self._fields = fields or _ok_fields
        self._boom_on = boom_on or set()
        self._interrupt_on = interrupt_on or set()

    def __call__(self, unit: StudyUnit) -> dict:
        if (unit.tier, unit.case_id, unit.arm, unit.run_index) in self._interrupt_on:
            raise KeyboardInterrupt  # a mid-study kill (credit exhaustion, ^C)
        self.calls.append(unit)
        if (unit.tier, unit.case_id, unit.arm, unit.run_index) in self._boom_on:
            raise RuntimeError("provider 5xx")
        fields = self._fields() if callable(self._fields) else dict(self._fields)
        return fields


def _run(units, scorer, tmp_path, *, recorded=None, budget=100.0, cost=None):
    golden_path, silver_path = _paths(tmp_path)
    return run_study(
        units,
        score=scorer,
        recorded=recorded or {},
        cost_model=cost or _cost(),
        budget_usd=budget,
        golden_path=golden_path,
        silver_path=silver_path,
        git_sha="abc1234",
        progress=lambda message: None,
    )


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- plan_units ------------------------------------------------------------------


def test_plan_units_orders_tier_then_run_then_case_then_arm():
    units = plan_units(["g1"], ["s1"], arms=("a", "b"), runs=2)
    assert [(u.tier, u.run_index, u.case_id, u.arm) for u in units] == [
        ("golden", 0, "g1", "a"),
        ("golden", 0, "g1", "b"),
        ("golden", 1, "g1", "a"),
        ("golden", 1, "g1", "b"),
        ("silver", 0, "s1", "a"),
        ("silver", 0, "s1", "b"),
        ("silver", 1, "s1", "a"),
        ("silver", 1, "s1", "b"),
    ]


# --- checkpoint append (DENOISE-04) ---------------------------------------------


def test_each_unit_appends_one_line_with_the_study_schema(tmp_path: Path):
    units = plan_units(["g1"], [], arms=("claude-sonnet-5",), runs=2)
    _run(units, RecordingScorer(), tmp_path)

    lines = _lines(tmp_path / "golden.jsonl")
    assert len(lines) == 2
    line = lines[0]
    # Identity is the runner's (unit-derived), never the scorer's to override.
    assert line["case_id"] == "g1"
    assert line["tier"] == "golden"
    assert line["generation_model"] == "claude-sonnet-5"
    assert line["run_index"] == 0
    assert line["git_sha"] == "abc1234"
    assert "ts" in line
    # Metric fields come from the scorer.
    assert line["faithfulness"] == 1.0
    assert line["relevancy"] == 4
    assert line["citation_valid"] is True
    assert line["found"] is True
    assert line["expected_not_found"] is False  # defaulted for ok lines
    assert lines[1]["run_index"] == 1


def test_lines_are_written_per_unit_not_buffered(tmp_path: Path):
    # A BaseException (mid-study kill) must leave every already-scored unit on
    # disk — the checkpoint is the write, not an end-of-study flush.
    units = plan_units(["g1", "g2", "g3"], [], arms=("claude-sonnet-5",), runs=1)
    scorer = RecordingScorer(interrupt_on={("golden", "g3", "claude-sonnet-5", 0)})
    with pytest.raises(KeyboardInterrupt):
        _run(units, scorer, tmp_path)

    assert [line["case_id"] for line in _lines(tmp_path / "golden.jsonl")] == ["g1", "g2"]


# --- error continuation (DENOISE-07) --------------------------------------------


def test_a_failing_unit_becomes_an_error_line_and_the_study_continues(tmp_path: Path):
    units = plan_units(["g1", "g2"], [], arms=("claude-sonnet-5",), runs=1)
    scorer = RecordingScorer(boom_on={("golden", "g1", "claude-sonnet-5", 0)})
    report = _run(units, scorer, tmp_path)

    lines = _lines(tmp_path / "golden.jsonl")
    assert [line["status"] for line in lines] == ["error", "ok"]
    assert "provider 5xx" in lines[0]["error"]
    assert lines[0]["faithfulness"] is None
    assert lines[0]["relevancy"] is None
    assert report.scored == 2


# --- artifact split (DENOISE-08) ------------------------------------------------


def test_golden_and_silver_lines_land_in_their_own_artifacts(tmp_path: Path):
    units = plan_units(["g1"], ["s1"], arms=("claude-sonnet-5",), runs=1)
    _run(units, RecordingScorer(), tmp_path)

    assert [line["case_id"] for line in _lines(tmp_path / "golden.jsonl")] == ["g1"]
    assert [line["case_id"] for line in _lines(tmp_path / "silver.jsonl")] == ["s1"]


# --- resume (DENOISE-05) --------------------------------------------------------


def test_resume_skips_completed_units_and_reattempts_errors(tmp_path: Path):
    units = plan_units(["g1", "g2", "g3", "g4"], [], arms=("claude-sonnet-5",), runs=1)
    recorded = {
        ("golden", "g1", "claude-sonnet-5", 0): "ok",
        ("golden", "g2", "claude-sonnet-5", 0): "skipped",
        ("golden", "g3", "claude-sonnet-5", 0): "error",
    }
    scorer = RecordingScorer()
    _run(units, scorer, tmp_path, recorded=recorded)

    # ok and skipped are done; error re-attempts; g4 was never recorded.
    assert [u.case_id for u in scorer.calls] == ["g3", "g4"]


def test_resume_of_a_complete_study_makes_zero_scorer_calls(tmp_path: Path):
    units = plan_units(["g1"], [], arms=("claude-sonnet-5",), runs=1)
    recorded = {("golden", "g1", "claude-sonnet-5", 0): "ok"}
    scorer = RecordingScorer()
    report = _run(units, scorer, tmp_path, recorded=recorded)

    assert scorer.calls == []
    assert report.scored == 0
    assert report.skipped == 1
    assert report.budget_stopped is False


# --- load_recorded + mismatch refusal (DENOISE-06) ------------------------------


def _write_lines(path: Path, lines: list[dict]) -> None:
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def test_load_recorded_keys_lines_and_accepts_matching_config(tmp_path: Path):
    golden_path, silver_path = _paths(tmp_path)
    _write_lines(
        golden_path,
        [
            {
                "case_id": "g1",
                "tier": "golden",
                "generation_model": "claude-sonnet-5",
                "run_index": 0,
                "status": "ok",
                "prompt_hash": _PHASH,
                "judge_model": _JUDGE,
            }
        ],
    )
    recorded = load_recorded(golden_path, silver_path, prompt_hash_value=_PHASH, judge_model=_JUDGE)
    assert recorded == {("golden", "g1", "claude-sonnet-5", 0): "ok"}


def test_load_recorded_refuses_a_prompt_hash_drift(tmp_path: Path):
    golden_path, silver_path = _paths(tmp_path)
    _write_lines(
        golden_path,
        [
            {
                "case_id": "g1",
                "tier": "golden",
                "generation_model": "claude-sonnet-5",
                "run_index": 0,
                "status": "ok",
                "prompt_hash": "ph-stale",
                "judge_model": _JUDGE,
            }
        ],
    )
    with pytest.raises(StudyMismatchError):
        load_recorded(golden_path, silver_path, prompt_hash_value=_PHASH, judge_model=_JUDGE)


def test_load_recorded_refuses_a_judge_model_drift(tmp_path: Path):
    golden_path, silver_path = _paths(tmp_path)
    _write_lines(
        silver_path,
        [
            {
                "case_id": "s1",
                "tier": "silver",
                "generation_model": "claude-sonnet-5",
                "run_index": 0,
                "status": "ok",
                "prompt_hash": _PHASH,
                "judge_model": "claude-haiku-4-5",
            }
        ],
    )
    with pytest.raises(StudyMismatchError):
        load_recorded(golden_path, silver_path, prompt_hash_value=_PHASH, judge_model=_JUDGE)


def test_load_recorded_tolerates_lines_without_judge_identity(tmp_path: Path):
    # Declined, skipped, and broken lines carry no judge identity (ADR-028) —
    # they must not trip the mismatch refusal.
    golden_path, silver_path = _paths(tmp_path)
    _write_lines(
        golden_path,
        [
            {
                "case_id": "g1",
                "tier": "golden",
                "generation_model": "claude-sonnet-5",
                "run_index": 0,
                "status": "ok",
                "found": False,
                "faithfulness": None,
                "relevancy": None,
            }
        ],
    )
    recorded = load_recorded(golden_path, silver_path, prompt_hash_value=_PHASH, judge_model=_JUDGE)
    assert recorded == {("golden", "g1", "claude-sonnet-5", 0): "ok"}


def test_load_recorded_of_absent_artifacts_is_a_fresh_study(tmp_path: Path):
    golden_path, silver_path = _paths(tmp_path)
    assert (
        load_recorded(golden_path, silver_path, prompt_hash_value=_PHASH, judge_model=_JUDGE) == {}
    )


# --- budget stop (DENOISE-14) ---------------------------------------------------


def test_budget_stops_before_the_unit_that_would_cross_the_ceiling(tmp_path: Path):
    # 5 units at $0.02 modeled each under a $0.05 ceiling → exactly 2 score.
    units = plan_units(["g1", "g2", "g3", "g4", "g5"], [], arms=("claude-sonnet-5",), runs=1)
    scorer = RecordingScorer()
    report = _run(units, scorer, tmp_path, budget=0.05, cost=_cost(gen=0.01, judge=0.01))

    assert [u.case_id for u in scorer.calls] == ["g1", "g2"]
    assert report.budget_stopped is True
    assert report.modeled_spent_usd == pytest.approx(0.04)
    # The stop is a clean checkpoint: the scored units are on disk.
    assert [line["case_id"] for line in _lines(tmp_path / "golden.jsonl")] == ["g1", "g2"]


def test_recorded_lines_count_toward_the_ceiling_exactly_once(tmp_path: Path):
    # Two recorded ok units at $0.02 modeled each start the meter at $0.04.
    # Under a $0.07 ceiling that leaves room for exactly one more unit — were
    # recorded units double-billed on resume ($0.08), nothing would score.
    units = plan_units(["g1", "g2", "g3", "g4"], [], arms=("claude-sonnet-5",), runs=1)
    recorded = {
        ("golden", "g1", "claude-sonnet-5", 0): "ok",
        ("golden", "g2", "claude-sonnet-5", 0): "ok",
    }
    scorer = RecordingScorer()
    report = _run(
        units, scorer, tmp_path, recorded=recorded, budget=0.07, cost=_cost(gen=0.01, judge=0.01)
    )

    assert [u.case_id for u in scorer.calls] == ["g3"]
    assert report.budget_stopped is True


def test_skipped_and_broken_recorded_lines_bill_nothing(tmp_path: Path):
    # A skipped case made no provider call — it must not consume ceiling.
    units = plan_units(["g1", "g2"], [], arms=("claude-sonnet-5",), runs=1)
    recorded = {("golden", "g1", "claude-sonnet-5", 0): "skipped"}
    scorer = RecordingScorer()
    report = _run(
        units, scorer, tmp_path, recorded=recorded, budget=0.02, cost=_cost(gen=0.01, judge=0.01)
    )

    assert [u.case_id for u in scorer.calls] == ["g2"]
    assert report.budget_stopped is False


# --- score_golden_unit (DENOISE-07: decline handling over frozen evidence) ------


class FakeJudge:
    model = _JUDGE

    def __init__(self):
        self.calls: list[str] = []

    def faithfulness(self, *, question, evidence, answer):
        self.calls.append("faithfulness")
        return SimpleNamespace(supported_ratio=1.0)

    def relevancy(self, *, question, answer):
        self.calls.append("relevancy")
        return 4


_EVIDENCE = [SnapshotEvidence(chunk_id="c1", snippet="a passage", anchor="ch1.xhtml")]


def _answer(text="An answer.", cited=("c1",), found=True):
    return SimpleNamespace(text=text, cited_chunk_ids=cited, model="claude-sonnet-5", found=found)


def _gcase(case_id="g1", expected_status="answered"):
    return EvalCase(case_id=case_id, question="What?", expected_status=expected_status)


def test_answered_golden_unit_is_judged_and_scored():
    judge = FakeJudge()
    fields = score_golden_unit(
        _gcase(),
        _EVIDENCE,
        generate=lambda question, evidence: _answer(),
        judge=judge,
        judge_prompt_hash=_PHASH,
    )

    assert fields["status"] == "ok"
    assert fields["found"] is True
    assert fields["faithfulness"] == 1.0
    assert fields["relevancy"] == 4
    assert fields["citation_valid"] is True
    assert fields["judge_model"] == _JUDGE
    assert fields["prompt_hash"] == _PHASH
    assert fields["expected_not_found"] is False
    assert judge.calls == ["faithfulness", "relevancy"]


def test_declined_golden_unit_skips_the_judge_with_null_scores():
    judge = FakeJudge()
    fields = score_golden_unit(
        _gcase("g-notfound", expected_status="not_found_in_source"),
        _EVIDENCE,
        generate=lambda question, evidence: _answer(text="", cited=(), found=False),
        judge=judge,
        judge_prompt_hash=_PHASH,
    )

    assert fields["status"] == "ok"
    assert fields["found"] is False
    assert fields["faithfulness"] is None
    assert fields["relevancy"] is None
    assert fields["citation_valid"] is True
    assert fields["expected_not_found"] is True
    assert "judge_model" not in fields
    assert judge.calls == []


def test_golden_unit_citing_an_unretrieved_chunk_is_citation_invalid():
    fields = score_golden_unit(
        _gcase(),
        _EVIDENCE,
        generate=lambda question, evidence: _answer(cited=("c9",)),
        judge=FakeJudge(),
        judge_prompt_hash=_PHASH,
    )
    assert fields["citation_valid"] is False


# --- per_run_aggregates (glue to ab.aggregate) ----------------------------------


def test_per_run_aggregates_splits_lines_by_arm_and_run():
    lines = [
        {
            "case_id": "s1",
            "tier": "silver",
            "status": "ok",
            "generation_model": "claude-sonnet-5",
            "run_index": 0,
            "faithfulness": 1.0,
            "relevancy": 4,
            "citation_valid": True,
            "found": True,
        },
        {
            "case_id": "s1",
            "tier": "silver",
            "status": "ok",
            "generation_model": "claude-sonnet-5",
            "run_index": 1,
            "faithfulness": 0.5,
            "relevancy": 2,
            "citation_valid": True,
            "found": True,
        },
        {
            "case_id": "s1",
            "tier": "silver",
            "status": "ok",
            "generation_model": "claude-opus-4-8",
            "run_index": 0,
            "faithfulness": 0.8,
            "relevancy": 3,
            "citation_valid": True,
            "found": True,
        },
    ]
    runs = per_run_aggregates(lines, arm="claude-sonnet-5", runs=2)
    assert len(runs) == 2
    assert runs[0].silver.mean_faithfulness == 1.0
    assert runs[1].silver.mean_faithfulness == 0.5


# --- entrypoint guards (DENOISE-09: opt-in only, never nightly-collected) -------


def test_study_entrypoint_is_not_enrolled_in_the_nightly_selection():
    # The nightly runs `-m "live and eval"`. The study test must carry `live`
    # (it exercises a real provider) but never `eval` — enrolling a two-arm
    # paid study in the nightly would multiply its cost silently.
    from tests.eval.test_generation_study import (
        test_generation_study_runs_both_arms_over_seeded_runs as study_test,
    )

    marker_names = {mark.name for mark in study_test.pytestmark}
    assert "live" in marker_names
    assert "eval" not in marker_names


def test_study_skips_without_the_opt_in_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # A bare run (no --generation-study) must skip, not spend — even with a key.
    from tests.eval.test_generation_study import study_skip_reason

    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "sk-ant-set")
    config = SimpleNamespace(getoption=lambda name: False)
    assert "--generation-study" in study_skip_reason(config)


def test_study_skips_without_a_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.eval.test_generation_study import study_skip_reason

    monkeypatch.delenv("LEARNY_ANTHROPIC_API_KEY", raising=False)
    config = SimpleNamespace(getoption=lambda name: True)
    assert "LEARNY_ANTHROPIC_API_KEY" in study_skip_reason(config)


def test_study_runs_with_flag_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.eval.test_generation_study import study_skip_reason

    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "sk-ant-set")
    config = SimpleNamespace(getoption=lambda name: True)
    assert study_skip_reason(config) is None
