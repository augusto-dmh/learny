"""D1 gate — generation replay harness: loader, snapshot schema, record path.

Derived from GEN-18 and the D1 Done-when: the cases load from ``cases.yaml``; a
snapshot round-trips through ``to_dict``/``from_dict`` and is written with sorted
keys and no volatile fields; the ``record_snapshots`` path writes one reviewable
JSON per case from an injected adapter; and the snapshot-driven check skips with
an explicit reason when no snapshots are committed (none are this cycle). A
live ``--record-generation`` test rewrites the real snapshots and stays skipped
offline.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.entities import Evidence, GeneratedAnswer
from tests.eval.harness import (
    EvalCase,
    Snapshot,
    build_snapshot,
    load_cases,
    load_snapshots,
    record_snapshots,
    write_snapshot,
)


def _evidence(snippet: str, anchor: str) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=("Chapter",),
        anchor=anchor,
        page_span=None,
        snippet=snippet,
        score=0.5,
    )


# --- Cases loader (GEN-18) -----------------------------------------------------


def test_cases_load_with_required_fields() -> None:
    cases = load_cases()

    assert len(cases) >= 10, "expected ~10-15 hand-authored cases"
    assert all(isinstance(c, EvalCase) for c in cases)
    assert all(c.case_id and c.question for c in cases)
    assert all(
        c.expected_status in {"answered", "not_found_in_source"} for c in cases
    )
    # Case ids are unique (they name the snapshot files).
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))
    # Both outcomes are represented, including not-found cases (F5 coverage).
    statuses = {c.expected_status for c in cases}
    assert statuses == {"answered", "not_found_in_source"}


# --- Snapshot schema round-trip (GEN-18) ---------------------------------------


def test_snapshot_build_and_roundtrip() -> None:
    case = EvalCase(case_id="c1", question="What is X?", expected_status="answered")
    evidence = [_evidence("alpha", "ch1.xhtml"), _evidence("beta", "ch2.xhtml")]
    generated = GeneratedAnswer(
        text="An answer.",
        cited_chunk_ids=(evidence[1].chunk_id,),
        model="claude-sonnet-4-6",
        found=True,
    )

    snapshot = build_snapshot(case, evidence, generated)

    assert snapshot.case_id == "c1"
    assert snapshot.model == "claude-sonnet-4-6"
    assert snapshot.question == "What is X?"
    # Evidence recorded in order, stable identity only.
    assert [e.chunk_id for e in snapshot.evidence] == [
        str(evidence[0].chunk_id),
        str(evidence[1].chunk_id),
    ]
    assert [e.snippet for e in snapshot.evidence] == ["alpha", "beta"]
    assert snapshot.answer.text == "An answer."
    assert snapshot.answer.cited_chunk_ids == (str(evidence[1].chunk_id),)
    assert snapshot.answer.found is True
    # to_dict → from_dict is lossless.
    assert Snapshot.from_dict(snapshot.to_dict()) == snapshot


def test_written_snapshot_has_sorted_keys_and_no_volatile_fields(tmp_path: Path) -> None:
    case = EvalCase(case_id="tides", question="Q?", expected_status="answered")
    evidence = [_evidence("gamma", "ch3.xhtml")]
    generated = GeneratedAnswer(
        text="", cited_chunk_ids=(), model="m", found=False
    )

    path = write_snapshot(build_snapshot(case, evidence, generated), tmp_path)

    assert path.name == "tides.json"
    raw = path.read_text(encoding="utf-8")
    loaded = json.loads(raw)
    # Sorted keys at every object level → stable, reviewable diffs on re-record.
    assert list(loaded.keys()) == sorted(loaded.keys())
    assert list(loaded["answer"].keys()) == sorted(loaded["answer"].keys())
    # No timestamps / request ids anywhere in the serialized form (design §8).
    for banned in ("timestamp", "ts", "request_id", "created_at", "score"):
        assert banned not in raw
    # The written file re-parses to the original snapshot.
    assert Snapshot.from_dict(loaded) == build_snapshot(case, evidence, generated)


# --- Record path with an injected adapter (GEN-18) -----------------------------


def test_record_snapshots_writes_one_reviewable_json_per_case(tmp_path: Path) -> None:
    cases = [
        EvalCase(case_id="a", question="Qa", expected_status="answered"),
        EvalCase(case_id="b", question="Qb", expected_status="not_found_in_source"),
    ]
    evidence_by_case = {
        "a": [_evidence("a-snip", "a.xhtml")],
        "b": [_evidence("b-snip", "b.xhtml")],
    }

    def generate(question: str, evidence: Sequence[Evidence]) -> GeneratedAnswer:
        # Fake adapter: cite the first chunk for the answerable case, decline the other.
        if question == "Qa":
            return GeneratedAnswer(
                text="Answer a.",
                cited_chunk_ids=(evidence[0].chunk_id,),
                model="fake-model",
                found=True,
            )
        return GeneratedAnswer(text="", cited_chunk_ids=(), model="fake-model", found=False)

    written = record_snapshots(
        cases,
        evidence_for=lambda case: evidence_by_case[case.case_id],
        generate=generate,
        snapshots_dir=tmp_path,
    )

    assert [p.name for p in written] == ["a.json", "b.json"]
    reloaded = {s.case_id: s for s in load_snapshots(tmp_path)}
    assert reloaded["a"].answer.found is True
    assert reloaded["a"].answer.text == "Answer a."
    assert reloaded["a"].answer.cited_chunk_ids == (
        str(evidence_by_case["a"][0].chunk_id),
    )
    assert reloaded["a"].model == "fake-model"
    assert reloaded["b"].answer.found is False
    assert reloaded["b"].answer.cited_chunk_ids == ()


# --- Snapshot-absent skip (GEN-18) ---------------------------------------------


def test_committed_snapshots_roundtrip_or_skip() -> None:
    snapshots = load_snapshots()
    if not snapshots:
        pytest.skip(
            "no committed generation snapshots — record them with "
            "`pytest --record-generation` and a provider key"
        )
    for snapshot in snapshots:
        assert Snapshot.from_dict(snapshot.to_dict()) == snapshot
        assert snapshot.case_id
        assert all(e.chunk_id and e.anchor for e in snapshot.evidence)
        # Not-found answers cite nothing — the recorded artifact must honor the
        # same contract the live path enforces, so a corrupted snapshot cannot
        # smuggle citations into a not-found case.
        if not snapshot.answer.found:
            assert snapshot.answer.cited_chunk_ids == ()


# --- Live recording (GEN-18) — skipped offline / without the flag --------------


@pytest.fixture
def _recording_enabled(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--record-generation"):
        pytest.skip("pass --record-generation to rewrite the committed snapshots")
    if not os.getenv("LEARNY_ANTHROPIC_API_KEY"):
        pytest.skip("LEARNY_ANTHROPIC_API_KEY required to record from the live provider")


@pytest.mark.live
def test_record_generation_rewrites_snapshots(
    _recording_enabled: None, db_conn  # noqa: ANN001 — sqlalchemy Connection fixture
) -> None:
    # Live path: build + embed the golden book, retrieve per case, run the real
    # Anthropic answer adapter, and rewrite the committed snapshots (reviewed in
    # the diff). Skipped unless --record-generation and a key are both present.
    from app.core.config import get_settings
    from app.infrastructure.answering.anthropic import AnthropicAnswerAdapter
    from tests.eval.harness import SNAPSHOTS_DIR
    from tests.eval_runner import (
        build_corpus_in_db,
        embed_source,
        retrieve,
        seed_source,
    )
    from tests.golden_corpus import golden_book

    settings = get_settings()
    _, source = seed_source(db_conn, email=f"record-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())
    embed_source(db_conn, source.id)
    adapter = AnthropicAnswerAdapter(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"],
        model=settings.generation_model,
        max_tokens=settings.generation_max_tokens,
    )

    written = record_snapshots(
        load_cases(),
        evidence_for=lambda case: retrieve(
            db_conn, source.id, case.question, top_k=settings.qa_evidence_top_k
        ),
        generate=lambda question, evidence: adapter.generate(
            question=question, evidence=evidence
        ),
        snapshots_dir=SNAPSHOTS_DIR,
    )

    assert len(written) == len(load_cases())
