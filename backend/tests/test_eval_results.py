"""Reader over the eval result JSONL (RFC-005 Cycle D).

The cases here are drawn from the shapes the real files actually contain: two
record families sharing one file, four different record schemas across five
committed files, and the nightly's habit of re-publishing every file it finds
into each snapshot directory.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.eval import results as reader
from app.eval.judge import FAITHFULNESS_MIN, RELEVANCY_MIN, _assert_aggregates
from app.infrastructure.web import evals as web_evals

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_RESULTS = REPO_ROOT / "evals" / "results"


def generation_line(
    case_id: str,
    *,
    faithfulness: float | None = 1.0,
    relevancy: int | None = 5,
    citation_valid: bool = True,
    found: bool = True,
    ts: str = "2026-07-31T10:00:00+00:00",
    **extra: Any,
) -> dict[str, Any]:
    """A generation-judge line, shaped as ``judge.run_eval`` writes it."""
    return {
        "case_id": case_id,
        "ts": ts,
        "git_sha": "abc1234",
        "generation_model": "claude-sonnet-5",
        "judge_model": "claude-opus-4-8",
        "prompt_hash": "hash",
        "faithfulness": faithfulness,
        "relevancy": relevancy,
        "citation_valid": citation_valid,
        "found": found,
        **extra,
    }


def answerability_line(item_id: str, *, score: int = 5, ts: str = "2026-07-31T10:00:00+00:00"):
    """An answerability-judge line — no ``faithfulness``, no ``citation_valid``."""
    return {
        "item_id": item_id,
        "ts": ts,
        "git_sha": "abc1234",
        "judge_model": "claude-haiku-4-5",
        "prompt_hash": "hash",
        "answerable": True,
        "score": score,
        "reason": "recoverable from the excerpt",
    }


def write_run(directory: Path, name: str, lines: list[dict[str, Any]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines), encoding="utf-8"
    )
    return path


# --- discovery + parsing (T1) ---------------------------------------------------


def test_missing_directory_yields_no_runs(tmp_path: Path) -> None:
    assert reader.load_runs(tmp_path / "never-created") == []


def test_empty_directory_yields_no_runs(tmp_path: Path) -> None:
    assert reader.load_runs(tmp_path) == []


def test_discovery_walks_nested_snapshot_directories(tmp_path: Path) -> None:
    """The eval-results branch nests runs under results/<date>-<run_id>/."""
    write_run(tmp_path / "results" / "2026-07-26-1", "2026-07-26-aaa.jsonl", [generation_line("a")])
    assert set(reader.discover_result_files(tmp_path)) == {"2026-07-26-aaa.jsonl"}


def test_same_basename_across_snapshots_counts_once(tmp_path: Path) -> None:
    """The nightly copies every file into each snapshot dir; a seed file is one run."""
    for snapshot in ("2026-07-24-1", "2026-07-25-2", "2026-07-26-3"):
        write_run(tmp_path / "results" / snapshot, "2026-07-18-seed.jsonl", [generation_line("a")])
    runs = reader.load_runs(tmp_path)
    assert [run.run_id for run in runs] == ["2026-07-18-seed"]


def test_duplicate_basename_resolves_to_the_newest_snapshot(tmp_path: Path) -> None:
    """The judge only appends, so the newest copy is a superset of the older ones."""
    write_run(tmp_path / "results" / "2026-07-24-1", "run.jsonl", [generation_line("a")])
    write_run(
        tmp_path / "results" / "2026-07-26-3",
        "run.jsonl",
        [generation_line("a"), generation_line("b")],
    )
    (run,) = reader.load_runs(tmp_path)
    assert run.line_count == 2


def test_malformed_line_is_counted_and_the_run_survives(tmp_path: Path) -> None:
    path = write_run(tmp_path, "run.jsonl", [generation_line("a"), generation_line("b")])
    path.write_text(path.read_text(encoding="utf-8") + '{"case_id": "trunc', encoding="utf-8")
    (run,) = reader.load_runs(tmp_path)
    assert (run.unparsable, run.line_count) == (1, 2)


def test_non_object_json_line_counts_as_unparsable(tmp_path: Path) -> None:
    path = write_run(tmp_path, "run.jsonl", [generation_line("a")])
    path.write_text(path.read_text(encoding="utf-8") + "[1, 2, 3]\n", encoding="utf-8")
    (run,) = reader.load_runs(tmp_path)
    assert (run.unparsable, run.line_count) == (1, 1)


# --- families + aggregation (T2) ------------------------------------------------


def test_mixed_family_file_aggregates_without_raising(tmp_path: Path) -> None:
    """Every real nightly file mixes both families; ab.aggregate raises on a mixed list."""
    write_run(
        tmp_path,
        "run.jsonl",
        [answerability_line("free_recall-0"), generation_line("a"), answerability_line("cloze-1")],
    )
    (run,) = reader.load_runs(tmp_path)
    assert run.answerability_count == 2
    assert run.generation is not None
    assert run.generation.line_count == 1


def test_answerability_lines_are_summarized_separately(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run.jsonl",
        [answerability_line("i-0", score=4), answerability_line("i-1", score=2)],
    )
    (run,) = reader.load_runs(tmp_path)
    assert run.answerability_mean_score == pytest.approx(3.0)
    assert run.generation is None
    assert run.verdict == reader.NOT_EVALUATED


def test_declines_stay_out_of_the_quality_means(tmp_path: Path) -> None:
    """ADR-0028: a decline is its own outcome class, never a zero-scoring answer."""
    write_run(
        tmp_path,
        "run.jsonl",
        [
            generation_line("answered", faithfulness=1.0, relevancy=4),
            generation_line("declined", faithfulness=None, relevancy=None, found=False),
        ],
    )
    (run,) = reader.load_runs(tmp_path)
    assert run.generation is not None
    assert run.generation.golden.answered == 1
    assert run.generation.golden.mean_faithfulness == pytest.approx(1.0)
    assert run.generation.golden.mean_relevancy == pytest.approx(4.0)


def test_declined_case_renders_with_absent_scores_not_zeros(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run.jsonl",
        [generation_line("declined", faithfulness=None, relevancy=None, found=False)],
    )
    (run,) = reader.load_runs(tmp_path)
    (case,) = run.cases
    assert (case.found, case.faithfulness, case.relevancy) == (False, None, None)


def test_runs_are_ordered_newest_first(tmp_path: Path) -> None:
    write_run(tmp_path, "old.jsonl", [generation_line("a", ts="2026-07-01T00:00:00+00:00")])
    write_run(tmp_path, "new.jsonl", [generation_line("b", ts="2026-07-30T00:00:00+00:00")])
    assert [run.run_id for run in reader.load_runs(tmp_path)] == ["new", "old"]


def test_undated_runs_sort_after_dated_ones(tmp_path: Path) -> None:
    dated = generation_line("a", ts="2026-07-01T00:00:00+00:00")
    undated = generation_line("b")
    del undated["ts"]
    write_run(tmp_path, "dated.jsonl", [dated])
    write_run(tmp_path, "undated.jsonl", [undated])
    assert [run.run_id for run in reader.load_runs(tmp_path)] == ["dated", "undated"]


def test_optional_provenance_fields_may_all_be_absent(tmp_path: Path) -> None:
    """The A/B study lines carry no git_sha; the de-noise lines carry no judge_model."""
    line = generation_line("a")
    for absent in ("git_sha", "judge_model", "prompt_hash", "generation_model"):
        del line[absent]
    write_run(tmp_path, "run.jsonl", [line])
    (run,) = reader.load_runs(tmp_path)
    assert (run.git_sha, run.judge_model, run.prompt_hash, run.generation_model) == (
        None,
        None,
        None,
        None,
    )
    assert run.verdict == reader.PASS


def test_silver_tier_lines_aggregate_into_the_silver_tier(tmp_path: Path) -> None:
    write_run(tmp_path, "run.jsonl", [generation_line("a", tier="silver", relevancy=4)])
    (run,) = reader.load_runs(tmp_path)
    assert run.generation is not None
    assert (run.generation.silver.scored, run.generation.golden.scored) == (1, 0)


def test_the_committed_result_files_all_parse(tmp_path: Path) -> None:
    """The four real record shapes are the regression surface for this reader."""
    runs = reader.load_runs(COMMITTED_RESULTS)
    assert len(runs) == 5
    assert all(run.unparsable == 0 for run in runs)
    assert any(run.generation is not None for run in runs)
    assert any(run.answerability_count > 0 for run in runs)


# --- verdict (T3) ---------------------------------------------------------------


def test_no_generation_lines_is_not_evaluated() -> None:
    assert reader.gate_outcome([]) == (reader.NOT_EVALUATED, ())


def test_citation_violation_fails_even_on_a_decline() -> None:
    """The citation invariant covers every line, declines included."""
    verdict, failures = reader.gate_outcome(
        [generation_line("d", faithfulness=None, relevancy=None, found=False, citation_valid=False)]
    )
    assert (verdict, failures) == (reader.FAIL, (reader.CITATION_FAILURE,))


def test_all_declined_run_passes_on_the_citation_invariant_alone() -> None:
    """The gate returns before its threshold asserts when nothing was answered."""
    lines = [
        generation_line(f"d{i}", faithfulness=None, relevancy=None, found=False) for i in range(3)
    ]
    assert reader.gate_outcome(lines) == (reader.PASS, ())


def test_all_declined_run_reports_absent_means_not_zeros(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run.jsonl",
        [generation_line("d", faithfulness=None, relevancy=None, found=False)],
    )
    (run,) = reader.load_runs(tmp_path)
    assert run.generation is not None
    assert run.generation.golden.mean_faithfulness is None
    assert run.generation.golden.mean_relevancy is None
    assert run.verdict == reader.PASS


def test_a_mean_below_its_threshold_names_that_metric() -> None:
    below = RELEVANCY_MIN - 1
    verdict, failures = reader.gate_outcome([generation_line("a", relevancy=int(below))])
    assert (verdict, failures) == (reader.FAIL, (reader.RELEVANCY_FAILURE,))


#: Every module on the dashboard's path that decides or publishes a threshold.
#: Value-equality assertions cannot catch a literal re-typed at today's value —
#: it only diverges at the next recalibration, which is precisely when nobody is
#: looking at this test — so the ban is enforced structurally, per module.
THRESHOLD_FREE_MODULES = (reader, web_evals)


@pytest.mark.parametrize("module", THRESHOLD_FREE_MODULES, ids=lambda m: m.__name__)
def test_thresholds_are_imported_rather_than_retyped(module: ModuleType) -> None:
    """A threshold literal in these modules would outlive the next recalibration.

    Cycle B moved relevancy 3.0 → 3.1; a dashboard drawing its reference line
    from its own copy would have kept drawing the old one. Checks the parsed
    code rather than the text, so prose naming a threshold is not a violation.
    """
    tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
    numbers = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float)
    ]
    assert FAITHFULNESS_MIN not in numbers
    assert RELEVANCY_MIN not in numbers


# --- the sensor that keeps the dashboard honest ---------------------------------


def gate_says_pass(lines: list[dict[str, Any]]) -> bool:
    """Run the real gate and report whether it accepted the lines."""
    try:
        _assert_aggregates(lines)
    except AssertionError:
        return False
    return True


EQUIVALENCE_CASES: list[tuple[str, list[dict[str, Any]]]] = [
    ("clean pass", [generation_line("a"), generation_line("b")]),
    (
        "faithfulness below threshold",
        [generation_line("a", faithfulness=0.5), generation_line("b", faithfulness=0.5)],
    ),
    ("relevancy below threshold", [generation_line("a", relevancy=1)]),
    ("citation violated", [generation_line("a", citation_valid=False)]),
    (
        "citation violated on a decline",
        [
            generation_line("a"),
            generation_line(
                "d", faithfulness=None, relevancy=None, found=False, citation_valid=False
            ),
        ],
    ),
    (
        "all declined",
        [generation_line("d", faithfulness=None, relevancy=None, found=False)],
    ),
    (
        "declines drag no mean down",
        [
            generation_line("a", faithfulness=1.0, relevancy=5),
            generation_line("d", faithfulness=None, relevancy=None, found=False),
        ],
    ),
    (
        "exactly at both thresholds",
        [generation_line("a", faithfulness=FAITHFULNESS_MIN, relevancy=4)],
    ),
    ("empty", []),
]


@pytest.mark.parametrize("label,lines", EQUIVALENCE_CASES, ids=[c[0] for c in EQUIVALENCE_CASES])
def test_derived_verdict_agrees_with_the_nightly_gate(
    label: str, lines: list[dict[str, Any]]
) -> None:
    """The dashboard's verdict is the gate's verdict, or the dashboard is a lie.

    ``not-evaluated`` is the one deliberate refinement: the gate returns early on
    an empty run, which is indistinguishable from acceptance, and the reader
    keeps them apart rather than painting nothing-ran green.
    """
    verdict, _ = reader.gate_outcome(lines)
    if verdict == reader.NOT_EVALUATED:
        assert not lines
        return
    assert (verdict == reader.PASS) is gate_says_pass(lines), label
