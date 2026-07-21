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

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import Connection, select

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
