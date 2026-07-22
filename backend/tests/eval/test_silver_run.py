"""Deterministic silver per-case execution + runner skip path (DEEP-01/03/17/19/20).

All fakes, no DB, no provider: exercises ``run_silver_case`` across every status
(ok / error), the retrieved-empty flag, citation validity, the skip/broken line
builders, the fresh-file-per-run writer, and — critically — proves the committed
runner self-skips with **zero** provider SDK imports when data/keys are absent.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.eval.silver import (
    BrokenCase,
    ResolvedCase,
    SilverCase,
    SilverJudgement,
    SkippedCase,
    broken_result,
    run_silver_case,
    silver_run_skip_reason,
    skipped_result,
    write_silver_results,
)

_FIXED = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


@dataclass
class FakeEvidence:
    chunk_id: str
    snippet: str = "SECRET_BOOK_PASSAGE"
    anchor: str = "ch1.xhtml"


@dataclass
class FakeAnswer:
    text: str = "An answer."
    cited_chunk_ids: tuple[str, ...] = ()
    model: str = "claude-sonnet-5"
    found: bool = True


@dataclass
class RaisingJudge:
    """Stands in for a judge whose provider 5xx'd or returned unschema'd output."""

    message: str = "judge returned malformed output"
    calls: list = field(default_factory=list)

    def __call__(self, question, evidence, answer):  # noqa: ANN001
        raise RuntimeError(self.message)


def _case(language: str = "english") -> SilverCase:
    return SilverCase(
        case_id="c1",
        question="What is trust?",
        source_checksum="a" * 64,
        expected_anchors=("ch1.xhtml",),
        expected_snippet="short attributed snippet",
        language=language,
    )


def _resolved(expected: tuple[str, ...] = ("c1",)) -> ResolvedCase:
    return ResolvedCase(case=_case(), source_id="src-1", expected_chunk_ids=expected)


def _ok_judge(question, evidence, answer) -> SilverJudgement:  # noqa: ANN001
    return SilverJudgement(
        faithfulness=1.0, relevancy=4, model="claude-haiku-4-5", prompt_hash="ph"
    )


# --- ok line -------------------------------------------------------------------


def test_ok_line_carries_the_full_schema_and_no_book_text() -> None:
    line = run_silver_case(
        _resolved(expected=("c1",)),
        retrieve=lambda r: [FakeEvidence("c1"), FakeEvidence("c2")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",), found=True),
        judge=_ok_judge,
        now=_FIXED,
    )

    assert line["status"] == "ok"
    assert line["case_id"] == "c1"
    assert line["tier"] == "silver"
    assert line["source_checksum"] == "a" * 64
    assert line["source_id"] == "src-1"
    assert line["language"] == "english"
    assert line["ts"] == _FIXED.isoformat()
    assert line["generation_model"] == "claude-sonnet-5"
    assert line["judge_model"] == "claude-haiku-4-5"
    assert line["prompt_hash"] == "ph"
    assert line["faithfulness"] == 1.0
    assert line["relevancy"] == 4
    assert line["citation_valid"] is True
    assert line["retrieved_empty"] is False
    assert line["expected_chunk_hit"] is True
    # The result line records ids/scores only — never the retrieved passage text.
    assert "SECRET_BOOK_PASSAGE" not in json.dumps(line)


def test_expected_chunk_miss_is_recorded() -> None:
    line = run_silver_case(
        _resolved(expected=("c9",)),  # expected chunk not among retrieved
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",)),
        judge=_ok_judge,
        now=_FIXED,
    )

    assert line["status"] == "ok"
    assert line["expected_chunk_hit"] is False


# --- retrieved-empty is ok, not error (DEEP-19) --------------------------------


def test_empty_retrieval_is_ok_with_flag_not_error() -> None:
    line = run_silver_case(
        _resolved(),
        retrieve=lambda r: [],
        generate=lambda q, ev: FakeAnswer(text="", cited_chunk_ids=(), found=False),
        judge=_ok_judge,
        now=_FIXED,
    )

    assert line["status"] == "ok"
    assert line["retrieved_empty"] is True
    assert line["expected_chunk_hit"] is False


# --- error lines (DEEP-17 malformed judge, DEEP-20 provider failure) -----------


def test_malformed_judge_output_becomes_a_visible_error_line() -> None:
    line = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",)),
        judge=RaisingJudge("no text block in judge response"),
        now=_FIXED,
    )

    assert line["status"] == "error"
    assert "RuntimeError" in line["error"]
    assert "no text block" in line["error"]
    # An error line keeps the case identity but carries no scores (never silently 0).
    assert line["case_id"] == "c1"
    assert line["tier"] == "silver"
    assert "faithfulness" not in line
    assert "relevancy" not in line


def test_judgement_missing_a_field_is_an_error_not_a_zero() -> None:
    class Partial:
        faithfulness = 1.0  # missing .relevancy / .model / .prompt_hash

    line = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",)),
        judge=lambda q, ev, a: Partial(),
        now=_FIXED,
    )

    assert line["status"] == "error"


def test_provider_failure_mid_run_becomes_an_error_line() -> None:
    def boom(question, evidence):  # noqa: ANN001 — generate adapter that 5xx'd
        raise RuntimeError("anthropic 529 overloaded")

    line = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=boom,
        judge=_ok_judge,
        now=_FIXED,
    )

    assert line["status"] == "error"
    assert "529" in line["error"]


# --- citation validity ---------------------------------------------------------


@pytest.mark.parametrize(
    ("found", "cited", "expected"),
    [
        (True, ("c1",), True),  # found + cites a retrieved chunk
        (True, ("c9",), False),  # found + cites a non-retrieved chunk
        (True, (), False),  # found but cites nothing
        (False, (), True),  # a decline cites nothing
        (False, ("c1",), False),  # a decline must not cite
    ],
)
def test_citation_validity_rules(found: bool, cited: tuple[str, ...], expected: bool) -> None:
    line = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1"), FakeEvidence("c2")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=cited, found=found),
        judge=_ok_judge,
        now=_FIXED,
    )

    assert line["citation_valid"] is expected


# --- the four statuses are distinct (DEEP-02/17/18/19) -------------------------


def test_skip_broken_error_ok_are_four_distinct_statuses() -> None:
    ok = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",)),
        judge=_ok_judge,
        now=_FIXED,
    )
    error = run_silver_case(
        _resolved(),
        retrieve=lambda r: [FakeEvidence("c1")],
        generate=lambda q, ev: FakeAnswer(cited_chunk_ids=("c1",)),
        judge=RaisingJudge(),
        now=_FIXED,
    )
    skipped = skipped_result(SkippedCase(case=_case(), reason="book absent"), now=_FIXED)
    broken = broken_result(
        BrokenCase(case=_case(), anchor="ch9.xhtml", source_id="src-1"), now=_FIXED
    )

    assert {ok["status"], error["status"], skipped["status"], broken["status"]} == {
        "ok",
        "error",
        "skipped",
        "broken",
    }
    # Each non-ok line stays diagnosable.
    assert skipped["reason"] == "book absent"
    assert broken["anchor"] == "ch9.xhtml"
    assert broken["source_id"] == "src-1"
    for line in (skipped, broken):
        assert line["tier"] == "silver"
        assert line["case_id"] == "c1"


# --- fresh-file-per-run writer (DEEP-20) ---------------------------------------


def test_writer_never_mutates_a_prior_results_file(tmp_path: Path) -> None:
    first = write_silver_results(
        [{"b": 1, "a": 2}], results_dir=tmp_path, git_sha="deadbee", now=_FIXED
    )
    first_bytes = first.read_bytes()

    second = write_silver_results(
        [{"a": 9}], results_dir=tmp_path, git_sha="deadbee", now=_FIXED
    )

    # Same date + sha, yet a distinct file — a rerun never appends to a prior one.
    assert first != second
    assert first.read_bytes() == first_bytes
    assert first.parent == tmp_path
    # JSONL with sorted keys.
    assert first.read_text(encoding="utf-8").splitlines() == ['{"a": 2, "b": 1}']
    assert json.loads(second.read_text(encoding="utf-8")) == {"a": 9}


# --- runner skip decision (DEEP-03) --------------------------------------------


def test_skip_reason_when_cases_file_absent(tmp_path: Path) -> None:
    reason = silver_run_skip_reason(cases_path=tmp_path / "cases.yaml")
    assert reason is not None
    assert "not present" in reason


def test_skip_reason_when_a_key_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []", encoding="utf-8")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "x")
    monkeypatch.setenv("LEARNY_DATABASE_URL", "x")
    monkeypatch.delenv("LEARNY_ANTHROPIC_API_KEY", raising=False)

    reason = silver_run_skip_reason(cases_path=cases)
    assert reason is not None
    assert "ANTHROPIC" in reason


def test_skip_reason_when_openai_key_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []", encoding="utf-8")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LEARNY_DATABASE_URL", "x")
    monkeypatch.delenv("LEARNY_OPENAI_API_KEY", raising=False)

    reason = silver_run_skip_reason(cases_path=cases)
    assert reason is not None
    assert "OPENAI" in reason


def test_skip_reason_when_database_url_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []", encoding="utf-8")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "x")
    monkeypatch.delenv("LEARNY_DATABASE_URL", raising=False)

    reason = silver_run_skip_reason(cases_path=cases)
    assert reason is not None
    assert "DATABASE_URL" in reason


def test_skip_reason_none_when_data_keys_and_db_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []", encoding="utf-8")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "x")
    monkeypatch.setenv("LEARNY_DATABASE_URL", "x")

    assert silver_run_skip_reason(cases_path=cases) is None


def test_runner_self_skips_and_imports_no_provider_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the skip regardless of whether local cases.yaml exists (Phase D may
    # create it) by clearing a required key, then prove importing the runner skips
    # at module level without pulling in a provider SDK.
    monkeypatch.delenv("LEARNY_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LEARNY_OPENAI_API_KEY", raising=False)
    for module in ("anthropic", "openai", "tests.eval.test_silver"):
        monkeypatch.delitem(sys.modules, module, raising=False)

    with pytest.raises(pytest.skip.Exception):
        importlib.import_module("tests.eval.test_silver")

    assert "anthropic" not in sys.modules
    assert "openai" not in sys.modules
