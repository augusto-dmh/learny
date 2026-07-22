"""Silver eval tier: case format, loader, DB resolution, per-case execution.

The silver tier is a small set of question -> expected-passage cases authored over
the maintainer's *real* ingested books (git-ignored ``evals/silver/cases.yaml``),
so eval verdicts reflect real usage rather than the synthetic golden book both
candidate models ace. Only this loader/runner code is committed; the cases,
snippets, and result lines live on the maintainer's machine (AD-163, DEEP-05).

A case is keyed by **source checksum + expected anchor(s)** (AD-162), never a
source UUID, so it survives re-ingestion and DB rebuilds. Resolution against a
live DB classifies each case as ``runnable`` (:class:`ResolvedCase`),
``skipped`` (book absent, :class:`SkippedCase`) or ``broken`` (anchor no longer
resolves, :class:`BrokenCase`) — three distinct outcomes the runner records
distinctly (DEEP-02/18). This module holds no provider SDK import: the loader and
resolver are pure/DB-only, and the runner takes its retrieve/generate/judge
callables injected, so the committed skip path never touches a provider (DEEP-03).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import yaml
from sqlalchemy import Connection, select

from app.eval.judge import git_sha_of_head
from app.infrastructure.db.metadata import (
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    sources,
)

_HERE = Path(__file__).resolve().parent
# silver.py -> tests/eval -> tests -> backend -> repo root; the ignored data tree
# lives at the repo root beside the tracked golden results (evals/results/).
_REPO_ROOT = _HERE.parents[2]
SILVER_DIR = _REPO_ROOT / "evals" / "silver"
SILVER_CASES_PATH = SILVER_DIR / "cases.yaml"
SILVER_RESULTS_DIR = SILVER_DIR / "results"

# Advisory case-count bounds (DEEP-04): the loader does not enforce them — a
# curation aid, not a schema rule — so a work-in-progress set still loads.
SILVER_MIN_CASES = 10
SILVER_MAX_CASES = 20

# Corpus languages the silver set spans (DEEP-04); the search_config values the
# real books carry are portuguese/english (simple is the untyped fallback).
SILVER_LANGUAGES = ("portuguese", "english")

_CHECKSUM_RE = re.compile(r"[0-9a-f]{64}")


class SilverCaseError(ValueError):
    """A ``cases.yaml`` entry failed schema validation, naming the case and field.

    Raised on load so a malformed local file aborts *before* any provider work,
    with the offending case id and field named for a one-line fix (DEEP-01/17).
    """

    def __init__(self, case_id: str, field: str, detail: str) -> None:
        self.case_id = case_id
        self.field = field
        super().__init__(f"silver case {case_id!r}: {field}: {detail}")


@dataclass(frozen=True)
class SilverCase:
    """One curated silver case: a question written against a specific read passage.

    Keyed by ``source_checksum`` + ``expected_anchors`` (AD-162). ``expected_snippet``
    is a short (<=25-word) attributed excerpt of the target passage, kept local for
    the maintainer's eyeball check — it is never written to a tracked file.
    """

    case_id: str
    question: str
    source_checksum: str
    expected_anchors: tuple[str, ...]
    expected_snippet: str
    language: str


def load_silver_cases(path: Path = SILVER_CASES_PATH) -> list[SilverCase]:
    """Load and schema-validate ``cases.yaml`` into :class:`SilverCase` objects.

    Raises :class:`SilverCaseError` (naming the case id + field) on the first
    malformed entry, so the run aborts before any resolution or provider call.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        raise SilverCaseError("<file>", "cases", "top-level 'cases:' list is required")
    entries = raw["cases"]
    if not isinstance(entries, list) or not entries:
        raise SilverCaseError("<file>", "cases", "must be a non-empty list")

    cases: list[SilverCase] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        case = _parse_case(entry, index)
        if case.case_id in seen:
            raise SilverCaseError(case.case_id, "case_id", "duplicate case id")
        seen.add(case.case_id)
        cases.append(case)
    return cases


def advisory_case_count(cases: list[SilverCase]) -> str | None:
    """Return an advisory message when the set is outside 10-20 cases, else ``None``.

    Advisory only (DEEP-04): the loader never rejects an out-of-range set — this
    is a curation aid the author consults, not a gate.
    """
    count = len(cases)
    if count < SILVER_MIN_CASES:
        return f"{count} cases: below the advisory minimum of {SILVER_MIN_CASES}"
    if count > SILVER_MAX_CASES:
        return f"{count} cases: above the advisory maximum of {SILVER_MAX_CASES}"
    return None


def _parse_case(entry: object, index: int) -> SilverCase:
    """Validate one raw YAML entry into a :class:`SilverCase` (all fields required)."""
    if not isinstance(entry, dict):
        raise SilverCaseError(f"#{index}", "case", "each case must be a mapping")

    # case_id first — it names every other field's error.
    case_id = entry.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise SilverCaseError(f"#{index}", "case_id", "non-empty string required")

    question = entry.get("question")
    if not isinstance(question, str) or not question.strip():
        raise SilverCaseError(case_id, "question", "non-empty string required")

    checksum = entry.get("source_checksum")
    if not isinstance(checksum, str) or not _CHECKSUM_RE.fullmatch(checksum):
        raise SilverCaseError(
            case_id, "source_checksum", "64-char lowercase sha256 hex required"
        )

    anchors = entry.get("expected_anchors")
    if not isinstance(anchors, list) or not anchors:
        raise SilverCaseError(
            case_id, "expected_anchors", "at least one anchor required"
        )
    if not all(isinstance(a, str) and a.strip() for a in anchors):
        raise SilverCaseError(
            case_id, "expected_anchors", "every anchor must be a non-empty string"
        )

    snippet = entry.get("expected_snippet")
    if not isinstance(snippet, str) or not snippet.strip():
        raise SilverCaseError(case_id, "expected_snippet", "non-empty string required")

    language = entry.get("language")
    if language not in SILVER_LANGUAGES:
        raise SilverCaseError(
            case_id, "language", f"must be one of {SILVER_LANGUAGES}"
        )

    return SilverCase(
        case_id=case_id,
        question=question,
        source_checksum=checksum,
        expected_anchors=tuple(anchors),
        expected_snippet=snippet,
        language=language,
    )


# --- DB resolution (checksum -> source, anchor -> chunks) -----------------------


@dataclass(frozen=True)
class ResolvedCase:
    """A runnable case: its book is present and every expected anchor resolves.

    ``source_id`` is the chosen source (latest ``created_at`` when the checksum is
    duplicated) as a string; ``expected_chunk_ids`` are the corpus chunks the
    expected anchors point at, in anchor order, deduplicated.
    """

    case: SilverCase
    source_id: str
    expected_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class SkippedCase:
    """The referenced book is not present in this DB (checksum miss) — skip, not fail."""

    case: SilverCase
    reason: str


@dataclass(frozen=True)
class BrokenCase:
    """The book is present but ``anchor`` no longer resolves — the case needs re-authoring.

    Distinct from :class:`SkippedCase` (DEEP-18): the source exists, so the case is
    stale (book re-ingested with different structure), not merely absent.
    """

    case: SilverCase
    anchor: str
    source_id: str


def resolve_case(
    conn: Connection, case: SilverCase
) -> ResolvedCase | SkippedCase | BrokenCase:
    """Resolve ``case`` against ``conn`` by source checksum then expected anchor(s).

    Checksum miss -> :class:`SkippedCase` (book absent). Checksum hit but an
    expected anchor matches no chunk (via the section's ``anchor`` or its
    ``anchor_aliases``) -> :class:`BrokenCase` naming that anchor. All anchors
    resolve -> :class:`ResolvedCase`. Duplicate checksums resolve deterministically
    to the latest ``created_at`` (id as tie-break); the chosen source id is
    surfaced so a result line records which book was scored. SELECT-only.
    """
    source_id = conn.execute(
        select(sources.c.id)
        .where(sources.c.checksum == case.source_checksum)
        .order_by(sources.c.created_at.desc(), sources.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if source_id is None:
        return SkippedCase(
            case=case,
            reason=f"no source with checksum {case.source_checksum} in this DB",
        )

    rows = conn.execute(
        select(
            corpus_chunks.c.id,
            corpus_sections.c.anchor,
            corpus_sections.c.anchor_aliases,
        )
        .select_from(
            corpus_documents.join(
                corpus_sections,
                corpus_sections.c.document_id == corpus_documents.c.id,
            ).join(
                corpus_chunks,
                corpus_chunks.c.section_id == corpus_sections.c.id,
            )
        )
        .where(corpus_documents.c.source_id == source_id)
    ).all()

    chunk_ids: list[str] = []
    for anchor in case.expected_anchors:
        matches = [
            str(row.id)
            for row in rows
            if row.anchor == anchor or anchor in (row.anchor_aliases or ())
        ]
        if not matches:
            return BrokenCase(case=case, anchor=anchor, source_id=str(source_id))
        for chunk_id in matches:
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)

    return ResolvedCase(
        case=case, source_id=str(source_id), expected_chunk_ids=tuple(chunk_ids)
    )


# --- Per-case execution + JSONL results ----------------------------------------


class _Evidence(Protocol):
    """The retrieved-chunk slice the runner reads (matches ``domain.Evidence``)."""

    chunk_id: Any
    snippet: str
    anchor: str


class _Answer(Protocol):
    """The generation slice the runner reads (matches ``domain.GeneratedAnswer``)."""

    text: str
    cited_chunk_ids: Sequence[Any]
    model: str
    found: bool


@dataclass(frozen=True)
class SilverJudgement:
    """One case's judge scores — the shape ``run_silver_case`` records on the line.

    The live runner composes the two :class:`~app.eval.judge.Judge` calls
    (faithfulness ratio + relevancy 1-5) into this; fakes build it directly.
    """

    faithfulness: float
    relevancy: int
    model: str
    prompt_hash: str


# Injected callables (the runner wires real adapters; tests wire fakes).
Retrieve = Callable[["ResolvedCase"], Sequence[_Evidence]]
Generate = Callable[[str, Sequence[_Evidence]], _Answer]
JudgeCall = Callable[[str, Sequence[_Evidence], _Answer], SilverJudgement]


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).isoformat()


def _base_line(case: SilverCase, now: datetime | None) -> dict[str, Any]:
    """The identity fields every silver result line carries (checksum-keyed, AD-162)."""
    return {
        "case_id": case.case_id,
        "ts": _now_iso(now),
        "tier": "silver",
        "source_checksum": case.source_checksum,
        "language": case.language,
    }


def _citation_valid(answer: _Answer, retrieved_ids: set[str]) -> bool:
    """A found answer must cite only retrieved chunks; a decline must cite nothing."""
    cited = {str(c) for c in answer.cited_chunk_ids}
    if not answer.found:
        return not cited
    return bool(cited) and cited <= retrieved_ids


def run_silver_case(
    resolved: ResolvedCase,
    *,
    retrieve: Retrieve,
    generate: Generate,
    judge: JudgeCall,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Retrieve -> generate -> judge one resolved case; return its JSONL result line.

    Status ``ok`` on success, ``error`` when any injected step raises (a provider
    5xx or a malformed judge output surfaces as a visible error line, never a
    silent score — DEEP-17/20). Empty retrieval is *not* an error: the case is
    still generated and judged, with ``retrieved_empty`` flagged (DEEP-19). No book
    text is written — only ids, scores, and flags.
    """
    line = _base_line(resolved.case, now)
    line["source_id"] = resolved.source_id
    try:
        evidence = list(retrieve(resolved))
        answer = generate(resolved.case.question, evidence)
        judgement = judge(resolved.case.question, evidence, answer)
        faithfulness = float(judgement.faithfulness)
        relevancy = int(judgement.relevancy)
        judge_model = str(judgement.model)
        judge_prompt_hash = str(judgement.prompt_hash)
        generation_model = str(answer.model)
    except Exception as exc:  # noqa: BLE001 — any step failing becomes a visible error line
        return {**line, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    retrieved_ids = {str(item.chunk_id) for item in evidence}
    return {
        **line,
        "status": "ok",
        "generation_model": generation_model,
        "judge_model": judge_model,
        "prompt_hash": judge_prompt_hash,
        "faithfulness": faithfulness,
        "relevancy": relevancy,
        "citation_valid": _citation_valid(answer, retrieved_ids),
        "retrieved_empty": not evidence,
        "expected_chunk_hit": bool(retrieved_ids & set(resolved.expected_chunk_ids)),
    }


def skipped_result(skipped: SkippedCase, *, now: datetime | None = None) -> dict[str, Any]:
    """A result line for a case whose book is absent (status ``skipped``, DEEP-02)."""
    return {**_base_line(skipped.case, now), "status": "skipped", "reason": skipped.reason}


def broken_result(broken: BrokenCase, *, now: datetime | None = None) -> dict[str, Any]:
    """A result line for a case whose anchor no longer resolves (status ``broken``, DEEP-18)."""
    return {
        **_base_line(broken.case, now),
        "source_id": broken.source_id,
        "status": "broken",
        "anchor": broken.anchor,
    }


def write_silver_results(
    lines: Sequence[dict[str, Any]],
    *,
    results_dir: Path = SILVER_RESULTS_DIR,
    git_sha: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Write ``lines`` to a **fresh** JSONL file under ``results_dir``; return its path.

    A per-run uuid suffix makes every run its own file, so a rerun never mutates a
    prior results file (DEEP-20) — the file is opened exclusively (``x``) so a name
    collision is a hard error, not a silent append.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H%M%S")
    sha = git_sha if git_sha is not None else git_sha_of_head()
    path = results_dir / f"{stamp}-{sha}-{uuid4().hex[:8]}.jsonl"
    with path.open("x", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, sort_keys=True) + "\n")
    return path


def silver_run_skip_reason(*, cases_path: Path = SILVER_CASES_PATH) -> str | None:
    """Why the committed live runner must self-skip, or ``None`` when it can run.

    The runner checks this at module import so CI and fresh clones skip *before*
    importing any provider SDK (DEEP-03): no local cases file, or a missing key /
    DB url, each yields a reason.
    """
    if not cases_path.exists():
        return f"no silver cases at {cases_path} — local silver tier not present"
    if not os.getenv("LEARNY_ANTHROPIC_API_KEY"):
        return "LEARNY_ANTHROPIC_API_KEY unset — live silver run skipped"
    if not os.getenv("LEARNY_OPENAI_API_KEY"):
        return "LEARNY_OPENAI_API_KEY unset — live silver run skipped"
    if not os.getenv("LEARNY_DATABASE_URL"):
        return "LEARNY_DATABASE_URL unset — no corpus DB to resolve against"
    return None
