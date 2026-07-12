# Golden Fixtures Validation

**Date**: 2026-07-12
**Spec**: `.specs/features/golden-fixtures/spec.md`
**Diff range**: `e8e28a2..HEAD` on `feat/golden-fixtures` (6 commits)
**Verifier**: independent sub-agent (author ≠ verifier, evidence-or-zero)

---

## Verdict: ✅ PASS

All 10 EVAL criteria are covered with located `file:line` evidence whose asserted
values match the spec-defined outcome. Full backend gate green (453 passed, 0
failed, 0 skipped with the test DB). 3/3 targeted regression mutants killed by
the golden checks; the 4th (grounding filter) is a characterized survivor of the
golden suite that is killed by pre-existing QA unit tests — not a feature gap
(see Sensor + Spec-precision notes).

---

## Task Completion

| Phase | Status | Notes |
| --- | --- | --- |
| A — ingestion golden (EVAL-01..04) | ✅ Done | `test_golden_ingestion.py` (pure), `test_golden_fixtures.py` self-consistency |
| B — retrieval golden (EVAL-05/06) | ✅ Done | `test_golden_retrieval.py` (`requires_db`) |
| C — citation golden (EVAL-07/08) | ✅ Done | `test_golden_citations.py` (`requires_db`) |
| Deviation — env.py fileConfig drop | ✅ Done | sound (see Deviations) |
| Deviation — test_migrations restore-to-head | ✅ Done | DB left at head after full suite |

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| EVAL-01 corpus metadata matches golden | title=`Field Notes on Change`, authors=`("Marie Curie",)`, language=`en`; null-safe (title/lang None, authors ()) for no_toc | `test_golden_ingestion.py:22-24` — `assert built.title == fixture.expected.title` (+authors,+language) | ✅ PASS |
| EVAL-02 ordered section structure | ordered `(section_path, anchor, depth)` per chapter, e.g. `(("The Rhythm of Tides",), "ch1.xhtml", 0)` | `test_golden_ingestion.py:40` — `assert actual == expected` (list of `(section_path, anchor, depth)`) | ✅ PASS |
| EVAL-03 derived chunks by stable identity | one chunk/section, text `# {title}\n\n{prose}`, `section_path`/`anchor` match, `page_span is None`; keyed by anchor not UUID | `test_golden_ingestion.py:51-55` — `assert tuple(c.text ...) == section.chunk_texts` + `chunk.section_path/anchor` + `assert chunk.page_span is None` | ✅ PASS |
| EVAL-04 block/chunk totals | `block_count == 6` (2×3 chapters), `chunk_count == 3`; no_toc `3/2` | `test_golden_ingestion.py:62-63` — `assert built.block_count == fixture.expected.block_count` (+chunk_count) | ✅ PASS |
| EVAL-05 target is rank-1 fused hit | target chapter anchor is `results[0].anchor` (rank-1, tightened from top-k in context.md) | `test_golden_retrieval.py:41` — `assert results[0].anchor == case.expected_anchor` | ✅ PASS |
| EVAL-06 source-scoping, no leakage | no source-B chunk id returned; every `Evidence.source_id == A` | `test_golden_retrieval.py:59-60` — `assert {e.chunk_id ...}.isdisjoint(b_ids)` + `assert all(e.source_id == source_a.id ...)` | ✅ PASS |
| EVAL-07 answered: target cited + bounded | `status=="answered"`, citations non-empty, target anchor cited, all cited anchors ⊆ golden anchors | `test_golden_citations.py:44-48` — `assert result.status == "answered"` + `assert result.citations` + `assert case.expected_anchor in cited_anchors` + `assert cited_anchors <= GOLDEN_SECTION_ANCHORS` | ✅ PASS ⚠️ (bound is structurally trivial — see spec-precision) |
| EVAL-08 empty-evidence → not-found | un-embedded corpus + unmatched question → `status=="not_found_in_source"`, `citations == ()` | `test_golden_citations.py:60-61` — `assert result.status == "not_found_in_source"` + `assert result.citations == ()` | ✅ PASS |
| EVAL-09 versioned golden; drift fails readably | hand-authored constants in `golden_corpus.py`/`golden_expected.py`; self-consistency guards | `test_golden_fixtures.py:33,36,44,49` — unique anchors, `chunk_count == Σ len(chunk_texts)`, case anchors ∈ `GOLDEN_SECTION_ANCHORS`; drift diff demonstrated by sensor | ✅ PASS |
| EVAL-10 deterministic/offline; skip w/o DB | integration modules `requires_db`, skip cleanly when `LEARNY_TEST_DATABASE_URL` unset; deterministic adapters | `test_golden_retrieval.py:22` / `test_golden_citations.py:26` — `pytestmark = requires_db`; verified 8 skipped without the var | ✅ PASS |

**Status**: ✅ All 10 ACs covered. One spec-precision observation on EVAL-07 (non-blocking).

**Golden values are hand-authored (not derived — no tautology):** `golden_expected.py`
and `golden_corpus.py` write every expected string by hand (`_NO_TOC_EXPECTED`
literals `# Introduction\n\nOpening remarks.`; `_chunk_text = f"# {title}\n\n{prose}"`).
`block_count`/`chunk_count` are computed from the fixture *input* definition
(`2 * len(_CHAPTERS)`), not read back from `BuildCorpus` output. No value is
derived by running the pipeline, so the checks are genuine oracles.

---

## Discrimination Sensor

Scratch state = direct edit + `git checkout --` revert (tracked files); tree
verified clean after each. Ran the covering golden test per mutation.

| # | File:line | Mutation | Covering test | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `app/application/chunking.py:49` | block join `\n\n` → `\n` | `test_golden_ingestion::test_derived_chunks_match_golden` | ✅ Killed (2 failed: `# Introduction\nOpening remarks.` ≠ `# Introduction\n\nOpening remarks.`) |
| 2 | `app/infrastructure/ingestion/markup.py:44` | heading level `#`×n → ×(n-1) (drops the `#`) | `test_golden_ingestion::test_derived_chunks_match_golden` | ✅ Killed (2 failed: `Introduction...` ≠ `# Introduction...`) |
| 3 | `app/infrastructure/db/retrieval.py:95` | fused `ORDER BY f.rrf_score DESC` → `ASC` | `test_golden_retrieval::test_recall_target_is_top_ranked` | ✅ Killed (3 failed: rank-1 anchor flips) |
| 4 | `app/application/grounding.py:30` | `grounded = [e ... if e.chunk_id in cited]` → `list(evidence)` (stop filtering to cited evidence) | `test_golden_citations` (all 4) | ❌ **Survived** (golden suite) — **Killed** by pre-existing `test_application_qa.py:136,268` |

**Sensor depth**: lightweight (4 behavior-level mutations on the highest-risk new
code, per spec Testing Strategy).
**Result**: 3/3 in-scope targeted mutants killed by the golden checks. Mutant 4
is an honest characterization, not a feature defect (see below).

### Mutant 4 — grounding filter, honest reasoning

The golden citation bound `cited_anchors <= GOLDEN_SECTION_ANCHORS` **cannot**
catch a "stop filtering to cited evidence" regression, and **cannot** catch a
fabricated out-of-source citation, in this fixture setup — because:

1. The `DeterministicAnswerAdapter` is extractive: it cites *exactly* the
   retrieved top-`_MAX_SNIPPETS` evidence it was handed. It can never emit an
   anchor that was not retrieved.
2. Retrieval is source-scoped (`WHERE cd.source_id = :source_id`), so every
   retrieved anchor is already ∈ the golden book's anchors.

So dropping the `ground()` filter changes nothing observable here: `grounded ==
evidence`, all anchors are still golden anchors, the target is still cited →
tests pass. The "no citation outside the source" property EVAL-07 asserts is
guaranteed *structurally by source-scoping*, not by the grounding filter, under
the deterministic adapter. The grounding-filter mechanism itself is exercised by
the pre-existing QA service tests (`test_ask_answered_grounds_orders_and_dedupes_citations`,
`test_ask_all_citations_out_of_evidence_is_not_found`), which use a fake generator
that cites an unretrieved id and assert it is excluded — those killed the mutant
(2 failed). This is consistent with the spec (EVAL-07 asserts source-boundedness
+ target-cited, both of which hold) and with the Out-of-Scope note that the shared
grounding guard is "already the citation seam under test." No fix task.

---

## Code Quality

| Principle | Status |
| --- | --- |
| No features beyond what was asked (test-only harness, no schema/endpoint per AD-039) | ✅ |
| No abstractions for single-use code (small dataclasses + thin runner fns) | ✅ |
| Only touched files required (tests/ + 2 justified deviation fixes) | ✅ |
| Matches existing patterns (`fixtures_epub.py`/`fakes.py` flat idiom, `requires_db` marker, `_persisted_source` mirror) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Every test maps to a spec EVAL — no unclaimed tests | ✅ |
| Golden values hand-authored, not pipeline-derived | ✅ |
| Documented guidelines followed: `.claude/skills/tlc-spec-driven/references/validate.md` | ✅ |

---

## Deviations — soundness check

- **`migrations/env.py` dropped `fileConfig(config.config_file_name)`** — SOUND.
  No test depends on alembic's own logging config; the app owns logging via
  `configure_logging`. The full suite (incl. `test_logging_redaction`, which the
  drop is meant to protect) passes, confirming redaction survives in-process
  migrations. Real production risk (redaction stripped if migrations run after
  startup) is correctly removed. Behavior-preserving for schema autogenerate /
  offline `--sql` (URL injection + metadata unchanged).
- **`test_migrations.py` module-scoped `_restore_schema_to_head` autouse fixture**
  — SOUND. After the full suite (which includes `test_migrations` downgrading to
  `base`), `alembic current` reports `0006_teaching_schema (head)`. The fixture
  leaves the shared DB at head regardless of module ordering. Additive; no
  assertion changed.

---

## Gate Check

- **Gate command**: `cd backend && LEARNY_TEST_DATABASE_URL=... uv run pytest -q` + `uv run ruff check .`
- **Result**: **453 passed, 0 failed, 0 skipped** (with test DB); ruff **All checks passed!**
- **Golden tests ran against DB (not skipped)**: verified — 26 golden tests
  PASSED in `-v` run; retrieval/citation integration tests executed (0 skipped
  with the DB url; 8 skip cleanly when the url is unset, confirming EVAL-10).
- **Test count delta**: +40 golden tests (26 golden-module tests: 16 ingestion/
  self-consistency + 4 retrieval + 4 citation + 2 fixture-bytes, parametrized).
  No test deleted; no assertion weakened.
- **Failures**: none.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| EVAL-01..EVAL-10 | Implementing | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 10/10 ACs matched spec outcome (1 non-blocking spec-precision note on EVAL-07).
**Sensor**: 3/3 in-scope regression mutants killed; 1 grounding-filter mutant is a characterized golden-suite survivor covered by pre-existing QA tests.
**Gate**: 453 passed, 0 failed, 0 skipped; ruff clean.

**What works**: EPUB→corpus→embed→retrieve→answer golden path is regression-
protected end to end against hand-authored, versioned expectations; determinism +
clean DB-skip confirmed; the two latent test-isolation deviations are sound and
leave the DB at head.

**Spec-precision observation (non-blocking)**: EVAL-07's "no citation outside the
source" bound is satisfied structurally by source-scoped retrieval + the
deterministic extractive adapter, so the golden citation suite does not itself
discriminate a grounding-filter regression (that seam is covered by the existing
QA unit tests, as the spec's Out-of-Scope note anticipates). If the extractive
adapter is ever replaced by a generative one that can cite freely, EVAL-07's bound
becomes a real (non-trivial) guard — worth a note when that adapter lands.

**Next steps**: none required. Ship.
