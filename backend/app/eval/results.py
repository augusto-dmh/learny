"""Read-only reader over the accumulating eval result JSONL (RFC-005 Cycle D).

The judge appends one JSONL line per evaluated case to
``evals/results/<date>-<git-sha>.jsonl`` and nothing has ever rendered them: the
nightly workflow's own comment called git history the dashboard. This module is
the render path's data half — discovery, tolerant parsing, and per-run
aggregation — kept free of web, database, and provider imports so the fitness
check's ``app/eval/`` rules hold and the whole thing is a file read.

Three properties of the real data drive the design, and each is a trap rather
than a preference:

* **Two record families share every file.** The generation judge writes
  ``case_id`` lines and the answerability judge writes ``item_id`` lines, into
  the same file, in the same run. :func:`app.eval.ab.aggregate` reads
  ``line["faithfulness"]`` unguarded, so handing it an answerability line raises
  ``KeyError``. Families are partitioned before anything aggregates (AD-242).
* **The nightly re-publishes every file it finds.** Each run copies all of
  ``evals/results/*.jsonl`` into ``results/<date>-<run_id>/`` on the
  ``eval-results`` branch, so the committed seed files reappear in every
  snapshot directory. Runs are keyed by file basename and de-duplicated, or the
  history reads as mostly repeated seed data (AD-240).
* **No verdict is recorded.** The gate asserts thresholds at run time and writes
  nothing about the outcome, so a rendered pass/fail has to be re-derived. It is
  derived by mirroring :func:`app.eval.judge._assert_aggregates` and importing
  its constants, so a recalibration cannot leave the dashboard showing a stale
  line (AD-241).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.eval.ab import ModelAggregate, aggregate
from app.eval.judge import FAITHFULNESS_MIN, RELEVANCY_MIN

#: Identity key the generation judge writes (``judge.py`` builds these lines).
GENERATION_KEY = "case_id"
#: Identity key the answerability judge writes.
ANSWERABILITY_KEY = "item_id"

#: Verdicts. ``NOT_EVALUATED`` is distinct from ``PASS``: a run that gated
#: nothing has not passed anything, and collapsing the two would let an
#: answerability-only run render as a green generation run.
PASS = "pass"
FAIL = "fail"
NOT_EVALUATED = "not-evaluated"

#: Failure reasons, carried alongside a ``fail`` so the page can say which
#: condition broke instead of only that the run is red.
CITATION_FAILURE = "citation"
FAITHFULNESS_FAILURE = "faithfulness"
RELEVANCY_FAILURE = "relevancy"


@dataclass(frozen=True)
class CaseRecord:
    """One rendered case. ``None`` scores mean *declined*, never zero.

    A decline (``found`` false) carries null scores by ADR-0028 — it is its own
    outcome class, not a bad answer — so the distinction has to survive all the
    way to the page or the drill-down would libel every decline as a zero.
    """

    case_id: str
    found: bool
    faithfulness: float | None
    relevancy: float | None
    citation_valid: bool
    tier: str | None
    status: str | None
    expected_not_found: bool
    run_index: int | None


@dataclass(frozen=True)
class RunSummary:
    """One eval run: its provenance, its aggregates, and its derived verdict."""

    run_id: str
    path: str
    latest_ts: str | None
    git_sha: str | None
    generation_model: str | None
    judge_model: str | None
    prompt_hash: str | None
    line_count: int
    unparsable: int
    generation: ModelAggregate | None
    answerability_count: int
    answerability_mean_score: float | None
    verdict: str
    failures: tuple[str, ...]
    cases: tuple[CaseRecord, ...]


def discover_result_files(root: Path) -> dict[str, Path]:
    """Map each result-file basename to the one path that represents it.

    The walk is recursive so a checkout of the ``eval-results`` branch — whose
    files sit under ``results/<date>-<run_id>/`` — reads the same as the flat
    local ``evals/results/``. Because the nightly copies every file it finds into
    each snapshot directory, one basename routinely exists under many
    directories; the greatest path wins, which is the newest snapshot, and the
    judge only ever appends, so that copy is a superset of the older ones
    (AD-240). A missing directory is not an error: nothing has run yet.
    """
    if not root.is_dir():
        return {}
    winners: dict[str, Path] = {}
    for path in root.rglob("*.jsonl"):
        if not path.is_file():
            continue
        current = winners.get(path.name)
        if current is None or str(path) > str(current):
            winners[path.name] = path
    return winners


def parse_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Return a file's records and the count of lines that would not parse.

    A truncated final line is the expected failure — the judge appends while a
    run is in flight, and a snapshot can catch it mid-write. One bad line must
    cost that line only, never the run, so parsing is per-line and the casualty
    is counted rather than raised. Non-object JSON (a bare list or scalar) is
    counted the same way: it cannot be a record.
    """
    records: list[dict[str, Any]] = []
    unparsable = 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [], 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            unparsable += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
        else:
            unparsable += 1
    return records, unparsable


def partition_families(
    lines: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into ``(generation, answerability)`` by their identity key.

    This is the guard that keeps :func:`app.eval.ab.aggregate` from ever seeing a
    mixed list. An answerability line has no ``faithfulness`` key and no
    ``found`` key — and ``found`` defaults to *answered* — so it would be pulled
    into the answered set and dereference a key it does not have (AD-242). A
    record carrying neither identity key belongs to neither family and is
    dropped; it is not a case.
    """
    generation: list[dict[str, Any]] = []
    answerability: list[dict[str, Any]] = []
    for line in lines:
        if GENERATION_KEY in line:
            generation.append(line)
        elif ANSWERABILITY_KEY in line:
            answerability.append(line)
    return generation, answerability


def gate_outcome(generation_lines: list[dict[str, Any]]) -> tuple[str, tuple[str, ...]]:
    """Re-derive the nightly gate's verdict for one run's generation lines.

    Mirrors :func:`app.eval.judge._assert_aggregates` condition for condition,
    because the JSONL records no verdict and a dashboard that disagrees with the
    gate it claims to show is worse than none. The order matters and is the
    gate's own:

    1. No generation line at all — nothing was gated (``not-evaluated``).
    2. ``citation_valid`` must hold on **every** line, declines included.
    3. With no answered line there is no mean to take, and the gate returns
       before its threshold asserts — so this is a pass on the citation
       invariant alone, not a failure, and the means stay absent.
    4. Otherwise both means, over answered lines only (ADR-0028).

    Thresholds come from :mod:`app.eval.judge`; a literal here would silently
    outlive the next recalibration (relevancy moved 3.0 → 3.1 in Cycle B).

    Two deliberate divergences, both unreachable on judge-written data, because a
    renderer may not crash on a file the gate would merely have died on:
    a generation line missing ``citation_valid`` counts as violating the
    invariant (the gate subscripts the key and would raise), and an *answered*
    line carrying a null score is left out of that mean rather than poisoning it
    (the gate would raise on the ``None``). Neither shape is producible by the
    writer — a decline is exactly the null-score line, and declines are not
    answered — so the equivalence with the gate holds for everything the judge
    actually emits.
    """
    if not generation_lines:
        return NOT_EVALUATED, ()
    failures: list[str] = []
    if not all(line.get("citation_valid", False) for line in generation_lines):
        failures.append(CITATION_FAILURE)
    answered = [line for line in generation_lines if line.get("found", True)]
    if answered:
        faithfulness = [
            float(line["faithfulness"]) for line in answered if line.get("faithfulness") is not None
        ]
        relevancy = [
            float(line["relevancy"]) for line in answered if line.get("relevancy") is not None
        ]
        if faithfulness and sum(faithfulness) / len(faithfulness) < FAITHFULNESS_MIN:
            failures.append(FAITHFULNESS_FAILURE)
        if relevancy and sum(relevancy) / len(relevancy) < RELEVANCY_MIN:
            failures.append(RELEVANCY_FAILURE)
    return (FAIL if failures else PASS), tuple(failures)


def _first_present(lines: list[dict[str, Any]], key: str) -> Any | None:
    """The first non-null value for ``key``, or ``None`` when no record carries it.

    Provenance fields are absent from whole families of the real files — the
    A/B study lines carry no ``git_sha``, the de-noise lines carry no
    ``judge_model`` — so every one of them is optional by construction.
    """
    for line in lines:
        value = line.get(key)
        if value is not None:
            return value
    return None


def _mean_score(lines: list[dict[str, Any]]) -> float | None:
    """Mean answerability score, or ``None`` when no line carries one."""
    scores = [float(line["score"]) for line in lines if isinstance(line.get("score"), int | float)]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _case_record(line: dict[str, Any]) -> CaseRecord:
    return CaseRecord(
        case_id=str(line.get(GENERATION_KEY, "")),
        found=bool(line.get("found", True)),
        faithfulness=(
            float(line["faithfulness"]) if line.get("faithfulness") is not None else None
        ),
        relevancy=(float(line["relevancy"]) if line.get("relevancy") is not None else None),
        citation_valid=bool(line.get("citation_valid", False)),
        tier=line.get("tier"),
        status=line.get("status"),
        expected_not_found=bool(line.get("expected_not_found", False)),
        run_index=line.get("run_index") if isinstance(line.get("run_index"), int) else None,
    )


def summarize_run(run_id: str, path: Path, root: Path) -> RunSummary:
    """Build one run's summary from its file."""
    records, unparsable = parse_lines(path)
    generation, answerability = partition_families(records)
    timestamps = [str(line["ts"]) for line in records if line.get("ts") is not None]
    verdict, failures = gate_outcome(generation)
    try:
        display_path = str(path.relative_to(root))
    except ValueError:
        display_path = str(path)
    return RunSummary(
        run_id=run_id,
        path=display_path,
        latest_ts=max(timestamps) if timestamps else None,
        git_sha=_first_present(records, "git_sha"),
        generation_model=_first_present(generation, "generation_model"),
        judge_model=_first_present(records, "judge_model"),
        prompt_hash=_first_present(records, "prompt_hash"),
        line_count=len(records),
        unparsable=unparsable,
        # Aggregation sees generation lines only — never the mixed list (AD-242).
        generation=aggregate(generation) if generation else None,
        answerability_count=len(answerability),
        answerability_mean_score=_mean_score(answerability),
        verdict=verdict,
        failures=failures,
        cases=tuple(_case_record(line) for line in generation),
    )


def load_runs(root: Path) -> list[RunSummary]:
    """Every discovered run, newest first.

    Ordering is by latest record timestamp; a run whose records carry no
    timestamp still has to land somewhere deterministic, so the run id breaks
    the tie and undated runs sort last rather than at an arbitrary position.
    """
    runs = [
        summarize_run(name.removesuffix(".jsonl"), path, root)
        for name, path in discover_result_files(root).items()
    ]
    runs.sort(
        key=lambda run: (run.latest_ts is not None, run.latest_ts or "", run.run_id), reverse=True
    )
    return runs
