# Golden Fixtures — Decision Context (Cycle 8)

Auto-decided per learny-ship-cycle Stage 1 (options + recommendation recorded;
no user prompt). Mirrored as AD-036..AD-039 in `.specs/project/STATE.md`.

## D-1 — Evaluation realized as a versioned test harness, not persisted tables (AD-036)

- **Chosen:** implement Phase 9 as a deterministic golden-fixture **test harness** under `backend/tests/` — versioned fixtures + expected values + fixture-driven checks. No `evaluation_fixtures/evaluation_runs/evaluation_results` SQL tables, no evaluation service, no Celery task, no endpoint this cycle.
- **Why:** ADR-016 scopes MVP evaluation to golden fixtures *before* a dashboard or metric scoring; TDD Phase 9's success criterion is "regression tests protect the source-grounding path" — the protection is the checks, not a run store. The project has repeatedly declined to add tables without a consumer (AD-025 shipped Q&A stateless); nothing reads persisted eval runs yet. Smallest reviewable surface; runs in CI with no new infrastructure.
- **Why not persisted schema + service + task:** big surface (migration + repos + task + wiring) for zero user-facing or test value this cycle — the tables would be write-only. The TDD data-model names them as *conceptual* tables whose exact columns "may change during implementation"; the Evaluation context's ownership (fixtures, expected values, run outcomes) is honoured as versioned artifacts + check results. Persistence becomes a follow-up when a real consumer (history UI, trend tracking, Ragas dashboard) exists — exactly the sequencing ADR-016 prescribes.

## D-2 — Fixture EPUBs are authored synthetic, no third-party binaries (AD-037)

- **Chosen:** the golden fixtures are authored synthetic EPUBs built as reviewable code — reuse the existing `tests/fixtures_epub.py` builders (`valid_book`, `nested_fragment_book`, `ncx_book`, `no_toc_book`) for ingestion structure coverage, plus one new topically-rich `golden_corpus.py` book whose sections carry distinct prose so retrieval queries have unambiguous targets. No real/third-party EPUB binary is committed.
- **Why:** resolves TDD open question #9 (first fixture EPUBs + licensing) by *avoiding* third-party text entirely — no license, trademark, or binary-blob concern. Synthetic EPUBs are byte-deterministic, fully reviewable in the diff, and already the basis of the parser tests, so the harness reuses a proven fixture idiom.
- **Why not a Project Gutenberg / real EPUB:** committing a binary book opens exactly the licensing/storage question OQ#9 flags for the owner, adds a non-reviewable blob to git, and buys a marginally more realistic retrieval signal that the topically-distinct synthetic book already provides for a deterministic recall check. A real-book fixture can be added later behind the same harness without changing it.
- **Why the new richer book (not just `valid_book`):** existing fixtures have very thin section prose (a few words each), a weak signal for retrieval recall. The new book gives each section enough distinct, disjoint prose that a query maps to one target section deterministically under the bag-of-tokens embedding adapter.

## D-3 — Stable-identity expectations; pure ingestion, integration retrieval/citation (AD-038)

- **Chosen:** golden expectations are expressed via **stable identity** — `anchor`, `section_path`, and snippet text — never generated chunk UUIDs. Ingestion golden runs **pure** (real parser + markup + `BuildCorpus` over an in-memory `FakeCorpusRepository`, no DB); retrieval + citation golden run **integration** against the pgvector test DB (build the corpus with the real `SqlAlchemyCorpusRepository`, embed with the deterministic adapter, retrieve with the real hybrid query), guarded by `requires_db` so they skip when `LEARNY_TEST_DATABASE_URL` is unset.
- **Why:** chunk ids are per-run UUIDs; `anchor`/`section_path` are the stable citation identity guaranteed across reads (AD-018), so expectations keyed on them are reproducible and readable. Ingestion output (metadata, structure, chunks, counts) is fully observable from `BuildCorpus`'s inputs to `CorpusRepository.replace` without a DB — keeping that suite fast and DB-free. Retrieval's whole point is the real hybrid SQL over pgvector, so its golden must exercise the real repository (mirrors `test_retrieval.py`). This split matches the repo's marker-based unit/integration convention exactly.
- **Why not assert on chunk UUIDs:** they change every run; a golden keyed on them is either flaky or requires pinning the id generator, which couples the golden to an implementation detail.
- **Why not run ingestion golden through the DB too:** no added signal (the corpus rows are a faithful projection of the records `BuildCorpus` passes to `replace`) at the cost of a DB dependency on a suite that does not need one.

## D-4 — Backend/test-only slice: no frontend, no schema, no endpoint (AD-039)

- **Chosen:** the cycle ships backend test-harness code only. No frontend, no migration, no API surface.
- **Why:** a golden-fixture evaluation harness is a developer/CI regression net with no end-user interaction; there is nothing to render. Adding a UI or endpoint would invent a surface no user story needs.
- **Why flag it:** it is a deliberate departure from AD-010's full-vertical-slice cadence — same category as AD-023 (Cycle 5 shipped backend-only). Surface it at the merge gate so the departure is a recorded choice, not an omission.

## Harness layout (design detail, not a separate decision)

Top-level test modules, matching the repo's flat helper convention
(`fixtures_epub.py`, `fakes.py`):

- `tests/golden_corpus.py` — the new topically-rich fixture book + its golden constants.
- `tests/golden_expected.py` — `ExpectedCorpus`/section/chunk values and `RetrievalCase`/`CitationCase` lists for every registered fixture; a `GOLDEN_FIXTURES` registry.
- `tests/eval_runner.py` — the harness functions: pure ingestion runner (real parser → `BuildCorpus` → `FakeCorpusRepository`) and DB runner (build in DB → embed → retrieve → answer via `AskQuestion`).
- `tests/test_golden_fixtures.py` — self-consistency checks on the golden data (fixtures build; every case's expected anchors are a subset of the fixture's section anchors).
- `tests/test_golden_ingestion.py` (pure), `tests/test_golden_retrieval.py` + `tests/test_golden_citations.py` (`requires_db`).

## Settings introduced

None. The harness reuses existing `LEARNY_` retrieval/QA settings and the
deterministic embedding + answer adapters.

## Execution notes

- 3 phases (A ingestion, B retrieval, C citation) → ≤3 → executed inline (no
  per-phase sub-agent offer). Fresh Verifier runs after the last task.

## Deviations

Two pre-existing latent test-isolation bugs surfaced when `test_golden_retrieval`
became the **first** DB-using test alphabetically (`test_g…`), and had to be fixed
for the full-suite gate to pass. Both are additive/root-cause fixes, not
assertion changes:

- **`migrations/env.py` dropped the alembic `fileConfig` call.** The default
  boilerplate reconfigured the root logger from `alembic.ini` on every in-process
  `command.upgrade`/`downgrade`, replacing handlers and stripping the app's
  sensitive-data redaction filter. Being the first DB test, the golden retrieval
  test triggered the session-scoped `db_engine` upgrade before
  `test_logging_redaction`, exposing it. Also a real production risk (redaction
  stripped if migrations ran after startup). The app owns logging via
  `configure_logging`, so alembic must not. Commit `570e52e`.
- **`tests/test_migrations.py` now restores `head` on module teardown.** Its tests
  `downgrade(..., "base")` and commit the dropped schema; the one-time
  `db_engine` upgrade previously ran *after* this module by ordering accident, so
  nothing broke. With the golden retrieval test upgrading first, the later
  base-downgrade left subsequent DB modules with no schema. Additive autouse
  fixture, no assertion touched. Commit `0fa6cd3`.

- **Spec tightening during Design→Execute:** EVAL-05 asserts the target is the
  **rank-1** hit (not merely "within top-k") — with a 3-section book every anchor
  is always in top-k, so rank-1 is the discriminating check. EVAL-06 is
  source-scoping (a populated semantic index always returns neighbours, so a
  "no-support returns nothing" retrieval negative is not meaningful). EVAL-08 uses
  the empty-evidence short-circuit (an un-embedded corpus + unmatched question) —
  the deterministic extractive adapter grounds whatever it retrieves, so
  grounded not-found is reachable only via empty retrieval.
