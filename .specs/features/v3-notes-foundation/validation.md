# v3-notes-foundation Validation

**Date**: 2026-07-18
**Spec**: `.specs/features/v3-notes-foundation/spec.md`
**Binding ADR**: `docs/adr/0026-notes-and-second-brain-domain-model.md` (decisions 1–2)
**Diff range**: `main...HEAD` (feat/v3-notes-foundation, 10 commits 586c523..ab4a69f)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero
**Verdict**: ✅ PASS (sensor 7/7 after the M7 test-strength fix in ab4a69f)

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 Migration 0010 + metadata + repo schema tests | ✅ Done | `0010_notes_schema.py`; inverse-cascade + content_hash |
| T2 Block hashing + AnchorResolver | ✅ Done | `anchoring.py`; corpus build hashes per block |
| T3 Entities/ports/repositories | ✅ Done | frozen dataclasses, Protocol repos, Connection impls |
| T4 Use cases (CRUD + capture + derive) | ✅ Done | owner scoping, body cap, wikilink/tag derivation |
| T5 ReconcileNoteAnchors + worker wiring | ✅ Done | 4-tier cascade; sibling step after quiz reconcile |
| T6 Web API | ✅ Done | 7 routes; auth/CSRF/rate/error mappings |
| T7 Frontend client | ✅ Done | `lib/notes.ts`, typed NoteError |
| T8 Reader capture | ✅ Done | popover + `deriveCaptureSelection` seam |
| T9 Notes screens + shell | ✅ Done | list/detail, badges, backlinks, jump-back |

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| NF-01 notes/note_anchors/tags/note_tags/note_links schema; source_id NO FK; within-aggregate cascades; note_links SET NULL | 5 tables, bare-UUID source_id, notes→users/anchors→notes CASCADE, target_note_id SET NULL, tags unique per user | `test_migrations.py:911-1006` (`assert "sources" not in anchor_referred`, SET NULL, `["user_id","name"]` unique); `test_repositories_notes.py:160-265` (source delete keeps note+anchor; SET NULL; note cascade) | ✅ PASS |
| NF-02 corpus_blocks.content_hash added; build computes normalize+sha256; existing rows NULL | nullable column; per-block sha256 of normalized markdown | `test_migrations.py:979-982` (nullable content_hash); `test_application_corpus.py:233-254` (`sections[0].block_hashes == (_hash("md:H0"), _hash("md:P0"))`) | ✅ PASS |
| NF-03 resolver locates owning block (hash/ordinal/offsets), falls back to quote-only; per ADR tier semantics | containment→normalized offsets; not-found→None; multi-block→first block; prefix/suffix disambiguate; NULL-hash tolerated | `test_notes_anchoring.py:14-102` (offsets (4,15); None; first-block (6,16); disambiguated start 13; hash None binds) | ✅ PASS |
| NF-04 frozen dataclasses, Protocol repos, Connection impls; body cap via LEARNY_NOTES_MAX_BODY_CHARS default 100000 | body over cap → NoteBodyTooLong, nothing persisted; default 100000; env override | `test_config.py:154-166` (default 100000; override 500); `test_notes_application.py:100-109` (raises + nothing persisted); `test_repositories_notes.py:271-337` (round-trip, set_links/set_tags) | ✅ PASS |
| NF-05 CRUD owner-scoped (== sources); update rewrites links/tags in one txn; wikilinks case-insensitive, unresolved keep target_text NULL | non-owner→NoteNotFound (404, no disclosure); resolved/unresolved links; case-insensitive; self-link ignored; lowercase tags | `test_notes_application.py:112-243` (by_text {"Target":id,"Missing":None}; case-insensitive; self-link []; tags ("notes","python")); `test_notes_application.py:193-231` (non-owner NoteNotFound) | ✅ PASS |
| NF-06 CaptureHighlight validates owned source's corpus, resolves anchor payload, creates note+anchor atomically; empty body allowed | owned source+section; atomic note+anchor; unknown source→SourceNotFound; unknown anchor→CorpusNotFound; stale→StaleCaptureTarget, nothing persisted | `test_notes_application.py:299-381` (anchor fields, empty body; SourceNotFound; CorpusNotFound; StaleCaptureTarget + `list_summaries==[]`); `test_web_notes.py:562-661` (201 jump-back; 404/404/409) | ✅ PASS |
| NF-07 reconcile after quiz reconcile; 4-tier exact cascade; never touches bodies; stale vs orphaned | T1 hash→active; T2 quote-in-section→active rebound; T3 quote-in-doc→active relocated (alias-aware); T4 section-lives→stale / section-gone→orphaned; write only on change | `test_notes_application.py:465-603` (each tier discriminated + alias + write-only-on-change + no-op); `test_worker_tasks.py:759-782` (`order == ["quiz","notes"]`); `test_repositories_notes.py:639-708` (DB active-after-reingest, orphan-after-mutation) | ✅ PASS |
| NF-08 source deleted → anchors orphaned; notes remain readable | orphan flip via reconcile/hook; notes survive | `test_repositories_notes.py:453-466` (`orphan_anchors_for_source` flips active→orphaned, note survives); `test_repositories_notes.py:689-708` (DB source-delete→reconcile→ORPHANED, note exists). SPEC_DEVIATION on record: no product source-delete call site; capability shipped + reconcile tier-4 covers emptied corpus | ✅ PASS (accepted deviation) |
| NF-09 router: 7 routes; auth + rate_limit_notes + origin/CSRF on writes; central error mappings | POST/GET/GET/PATCH/DELETE notes + highlights + backlinks; 401/403/404/409/422/429 | `test_web_notes.py:260-674` (201/422/401/403-csrf/403-origin/429; list; get 404-collapse; patch; delete 204; backlinks; capture); `notes.py:207-361` route deps | ✅ PASS |
| NF-10 views expose anchor status + jump-back (source_id, anchor, quote) | anchor view carries source_id/anchor/quote_exact/status/section_path | `test_web_notes.py:588-597` (source_id, anchor, quote_exact, source_title, status, section_path); `notes.py:103-140` NoteAnchorView; list `anchor_statuses` `test_web_notes.py:360-367` | ✅ PASS |
| NF-11 lib/notes.ts mirrors quiz.ts (CSRF echo, typed errors); vitest coverage | same-origin paths; X-CSRF on writes, none on reads; tag query; typed NoteError 409→stale_capture/422→body_too_long | `notes-client.test.ts:80-395` (each helper path/method/CSRF; tag %20 encode; 409/422/other mappings; readable fallbacks) | ✅ PASS |
| NF-12 reader selection capture: onMouseUp popover, sends quote+context+offsets; success links to note | popover both actions; quote whitespace-normalized + 32-char context from served Markdown; Highlight+note navigates | `section-reader.test.tsx:277-357` (dialog + 2 buttons; payload {anchor,quote_exact,quote_prefix "## Beginnings ",quote_suffix "."}; push /notes/n1; 409 reload prompt) | ✅ PASS |
| NF-13 notes list + detail (textarea+preview, tags, backlinks, anchored passages jump-back); sidebar Notes entry | list title links/tag chips/badges/filter; detail editor+preview, save-when-dirty, jump-back href `read?anchor=` | `notes-screen.test.tsx:78-188` (links, chips, badges, filter, create, empty, signed-out); `note-detail-screen.test.tsx:104-227` (hydrate, jump href, save-dirty, preview, delete-confirm); `app-sidebar.tsx` Notes entry | ✅ PASS |
| NF-14 orphaned anchors render distinct badge + quote snapshot, never hidden | orphaned → `anchor-status-orphaned` badge + quote text shown; orphan offers no jump-back | `notes-screen.test.tsx:95-97`; `note-detail-screen.test.tsx:124-127` (getByText vanished quote + `anchor-status-orphaned` testid); jump-gate direction now pinned by distinct orphan `source_id`/`anchor` (ab4a69f) — see Sensor M7 | ✅ PASS |

**Status**: ✅ 14/14 ACs covered with spec-anchored assertions. No open discrimination gaps (the NF-14/NF-10 orphan jump-back gate direction was strengthened in ab4a69f and re-verified).

### Edge cases

- [x] Multi-block selection binds first block, quote captures full selection — `test_notes_anchoring.py:52-66`.
- [x] Duplicate tag names differing by case normalized to lowercase, unique per user — `test_notes_application.py:155-166`, `test_repositories_notes.py:184-196`.
- [x] Wikilink self-link ignored — `test_notes_application.py:144-152`.
- [x] Note deleted → note_links cascade; inbound links SET NULL keep target_text — `test_repositories_notes.py:199-265`.
- [x] Capture on replaced-mid-flight section → stale input → 409 — `test_notes_application.py:364-381`, `test_web_notes.py:631-646`.

---

## Discrimination Sensor

Scratch-state fault injection (Edit + `git checkout` restore after each); the real working tree was never left mutated. Confirmed pristine after each run.

| # | File:line | Mutation | Test run | Killed? |
| - | --------- | -------- | -------- | ------- |
| 1 | `application/notes.py:96` | Owner check `!= user.id` → `== user.id` | `test_notes_application.py` | ✅ Killed (6 failed) |
| 2 | `application/notes.py:495` | Tier-1 block-hash gate `is not None` → `and False` (always skip) | `test_notes_application.py` | ✅ Killed (2 failed) |
| 3 | `application/notes.py:539` | Tier-4 status `if located is not None` → `if located is None` (stale/orphaned swap) | `test_notes_application.py` | ✅ Killed (2 failed) |
| 4 | `application/notes.py:49` | Wikilink regex `\[\[(...)\]\]` → single-bracket `\[(...)\]` | `test_notes_application.py` | ✅ Killed (6 failed) |
| 5 | `application/anchoring.py:90` | Off-by-one `end_offset = start + len(nq) + 1` | `test_notes_anchoring.py` | ✅ Killed (3 failed) |
| 6 | `notes/capture-popover.tsx:60` | Prefix slice `index - CONTEXT_CHARS` → `index` (empty prefix) | `section-reader.test.tsx` | ✅ Killed (1 failed) |
| 7 (pre-fix, 3d0c594) | `notes/note-detail-screen.tsx:320` | Orphan jump-gate `status === "orphaned"` → `!== "orphaned"` | `note-detail-screen.test.tsx` | ❌ Survived (5 passed) → fixed in ab4a69f |
| 7 (re-run, ab4a69f) | `notes/note-detail-screen.tsx:320` | Same gate inversion, against the strengthened fixture | `note-detail-screen.test.tsx` | ✅ **Killed** (1 failed) |

**Sensor depth**: lightweight+ (7 mutants across schema/resolver/reconcile/owner/regex/frontend layers).
**Result**: 7/7 killed after ab4a69f (M7 was the sole survivor pre-fix; independently re-verified killed post-fix).

### M7 resolution (fixed in ab4a69f, independently re-verified)

Pre-fix, `note-detail-screen.test.tsx` built `orphanAnchor = { ...liveAnchor, id, quote_exact, status: "orphaned" }`, so the orphaned and live anchors shared the same `anchor` and `source_id`. Inverting the jump-back gate made the *active* anchor render "This passage is no longer in the book" and the *orphaned* one render the jump-link — but the jump-link count stayed 1 and the shared href was unchanged, so the mutant survived. The production code was already correct (orphaned → no jump, active → jump); only the test under-discriminated the gate's direction.

Commit **ab4a69f** gives the orphaned fixture distinct identifiers (`source_id: "s9"`, `anchor: "chapter-9.xhtml#vanished"`). Now inverting the gate renders the orphan's `/sources/s9/read?anchor=chapter-9.xhtml%23vanished` href, so the live-href assertion (`note-detail-screen.test.tsx:124-127`, expects `/sources/s1/read?anchor=chapter-1.xhtml%23core-idea`) fails. Independent re-run of the same gate-inversion mutant against ab4a69f: **1 failed** (mutant killed); working tree restored pristine afterward. No production code changed.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ (SPEC_DEVIATION for NF-08 documented in-code; no speculative source-delete route added) |
| Surgical changes / only required files | ✅ |
| Matches existing patterns (quiz reconcile, sources auth, quiz.ts client, TestClient house style) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage: domain 1:1 ACs; routes happy+edge+error for every route | ✅ |
| Every test maps to a spec AC / edge / Done-when — no unclaimed tests | ✅ |
| Documented guidelines followed | ✅ (Test Coverage Matrix in tasks.md; house DB-gated integration + colocated unit + vitest 1:1) |

---

## Gate Check

- **Backend** (`uv run pytest -q`, OFFLINE, no LEARNY_TEST_DATABASE_URL): **777 passed, 402 skipped**, 2 warnings. Matches expected baseline.
- **Backend lint** (bare `uv run ruff check`): **All checks passed** (exit 0).
- **Frontend** (`npx vitest run`): **210 passed** (30 files). Matches expected baseline.
- **Frontend types** (`npx tsc --noEmit`): clean (exit 0).
- **DB-gated (optional, live test DB up)** `tests/test_repositories_notes.py` with LEARNY_TEST_DATABASE_URL: **22 passed** — confirms inverse-cascade (NF-01), SET NULL, per-user tag uniqueness, and end-to-end capture→re-ingest→reconcile→orphan + source-delete→orphan (NF-07/08) at the live-DB level.
- Skipped tests are the DB-gated suites (no offline DB) — justified by the house DB-gated-integration convention; the notes DB suite was additionally run green above.

---

## Requirement Traceability Update

| Requirement | New Status |
| ----------- | ---------- |
| NF-01 .. NF-13 | ✅ Verified |
| NF-14 | ✅ Verified (orphan jump-back gate direction now pinned + re-verified, ab4a69f) |

---

## Summary

**Overall**: ✅ Ready — no open gaps

**Spec-anchored check**: 14/14 ACs matched spec outcome; the one flagged discrimination gap (NF-14/NF-10 orphan jump-back direction) was fixed in ab4a69f and independently re-verified.
**Sensor**: 7/7 mutants killed (M7 was the sole pre-fix survivor; re-run against ab4a69f is killed).
**Gate**: backend 777 passed / 402 skipped, ruff clean; frontend 210 passed, tsc clean; DB notes suite 22 passed.

**What works**: Full notes aggregate — schema with the inverse-cascade invariant, block hashing, pure anchor resolver, owner-scoped CRUD with derived wikilink/tag indexes, atomic highlight capture, the 4-tier exact reconcile cascade wired after quiz reconcile, the web API with full auth/CSRF/rate/error coverage, the browser client, the reader capture popover, and the list/detail screens with orphan badges and jump-back.

**Issues found**: None open. The pre-fix M7 survivor (shared orphan/live anchor fixtures under-discriminating the jump-back gate direction) is resolved by ab4a69f's distinct orphan identifiers; re-verified killed. No production code was affected.

**Next steps**: None required — shippable as-is.
