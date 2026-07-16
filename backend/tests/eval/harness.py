"""Loader + snapshot schema for the generation replay harness (design §8).

Pure, DB-free, provider-free helpers so the deterministic invariant suite and
the record path share one definition of a case and a snapshot. A snapshot is the
port-boundary record of one generation — the retrieved evidence in order and the
Learny-owned :class:`~app.domain.entities.GeneratedAnswer` it produced — with
**sorted keys and no timestamps or request ids**, so a re-record produces a clean
reviewable diff rather than volatile churn (risks table, design §8).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domain.entities import Evidence, GeneratedAnswer

_HERE = Path(__file__).resolve().parent
CASES_PATH = _HERE / "cases.yaml"
SNAPSHOTS_DIR = _HERE / "snapshots"


@dataclass(frozen=True)
class EvalCase:
    """One hand-authored golden-book case (``cases.yaml``).

    ``expected_status`` (``answered`` | ``not_found_in_source``) is a hint for the
    live/snapshot path; the deterministic invariants do not assert it.
    """

    case_id: str
    question: str
    expected_status: str


@dataclass(frozen=True)
class SnapshotEvidence:
    """One retrieved chunk as recorded in a snapshot (stable identity + text)."""

    chunk_id: str
    snippet: str
    anchor: str


@dataclass(frozen=True)
class SnapshotAnswer:
    """The recorded generation outcome (parsed ``GeneratedAnswer`` fields)."""

    text: str
    cited_chunk_ids: tuple[str, ...]
    found: bool


@dataclass(frozen=True)
class Snapshot:
    """A committed replay record for one case: evidence in order + the answer."""

    case_id: str
    model: str
    question: str
    evidence: tuple[SnapshotEvidence, ...]
    answer: SnapshotAnswer

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form (no volatile fields; keys sorted at write)."""
        return {
            "case_id": self.case_id,
            "model": self.model,
            "question": self.question,
            "evidence": [
                {"chunk_id": e.chunk_id, "snippet": e.snippet, "anchor": e.anchor}
                for e in self.evidence
            ],
            "answer": {
                "text": self.answer.text,
                "cited_chunk_ids": list(self.answer.cited_chunk_ids),
                "found": self.answer.found,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        """Rebuild a snapshot from its committed JSON (inverse of :meth:`to_dict`)."""
        answer = data["answer"]
        return cls(
            case_id=data["case_id"],
            model=data["model"],
            question=data["question"],
            evidence=tuple(
                SnapshotEvidence(
                    chunk_id=e["chunk_id"], snippet=e["snippet"], anchor=e["anchor"]
                )
                for e in data["evidence"]
            ),
            answer=SnapshotAnswer(
                text=answer["text"],
                cited_chunk_ids=tuple(answer["cited_chunk_ids"]),
                found=answer["found"],
            ),
        )


def load_cases() -> tuple[EvalCase, ...]:
    """Load the hand-authored cases from ``cases.yaml`` in file order."""
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return tuple(
        EvalCase(
            case_id=case["case_id"],
            question=case["question"],
            expected_status=case["expected_status"],
        )
        for case in data["cases"]
    )


def load_snapshots(snapshots_dir: Path = SNAPSHOTS_DIR) -> tuple[Snapshot, ...]:
    """Load committed snapshots (``*.json``) sorted by filename; empty when absent.

    Returns ``()`` when the directory is missing or holds no snapshots — the
    caller skips the snapshot-driven checks with an explicit reason (no snapshots
    are committed this cycle).
    """
    if not snapshots_dir.is_dir():
        return ()
    return tuple(
        Snapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(snapshots_dir.glob("*.json"))
    )


def build_snapshot(
    case: EvalCase, evidence: Sequence[Evidence], generated: GeneratedAnswer
) -> Snapshot:
    """Assemble a :class:`Snapshot` from a case, its evidence, and the generation.

    Records the retrieved evidence in order and the parsed answer fields only —
    no timestamps, request ids, or scores — so re-recording is a stable diff.
    """
    return Snapshot(
        case_id=case.case_id,
        model=generated.model,
        question=case.question,
        evidence=tuple(
            SnapshotEvidence(
                chunk_id=str(item.chunk_id), snippet=item.snippet, anchor=item.anchor
            )
            for item in evidence
        ),
        answer=SnapshotAnswer(
            text=generated.text,
            cited_chunk_ids=tuple(str(cid) for cid in generated.cited_chunk_ids),
            found=generated.found,
        ),
    )


def write_snapshot(snapshot: Snapshot, snapshots_dir: Path = SNAPSHOTS_DIR) -> Path:
    """Write ``snapshot`` as ``<case_id>.json`` with sorted keys; return its path."""
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / f"{snapshot.case_id}.json"
    path.write_text(
        json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def record_snapshots(
    cases: Sequence[EvalCase],
    *,
    evidence_for: Callable[[EvalCase], Sequence[Evidence]],
    generate: Callable[[str, Sequence[Evidence]], GeneratedAnswer],
    snapshots_dir: Path = SNAPSHOTS_DIR,
) -> list[Path]:
    """Record a snapshot per case by running ``generate`` over its retrieved evidence.

    Provider- and DB-agnostic: ``evidence_for`` supplies each case's retrieved
    evidence and ``generate(question, evidence)`` is the adapter call, so the same
    routine drives the live ``--record-generation`` run and a fake-client unit
    test. Returns the written paths in case order.
    """
    written: list[Path] = []
    for case in cases:
        evidence = evidence_for(case)
        generated = generate(case.question, evidence)
        snapshot = build_snapshot(case, evidence, generated)
        written.append(write_snapshot(snapshot, snapshots_dir))
    return written
