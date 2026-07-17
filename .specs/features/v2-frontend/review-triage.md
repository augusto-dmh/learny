# PR #24 Review Triage — v2-frontend (RFC-002 Cycle D)

Review: 14 comments (12 inline + 2 PR-level) posted by the six-subagent pr-review run
(security, requirements, tests, architecture, regression, performance). 6 inline
positive highlights + 6 finding-comments collapsing to **4 distinct findings** (two
were double-posted by Architecture and Regression); both PR-level comments are
informational (requirements review: all 22 requirements implemented, nothing blocking;
consolidation summary). Every finding was re-verified against the code before verdict.

| # | Source comment(s) | File:line | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| R1 | 3599488988 (performance) | `frontend/app/components/shell/app-sidebar.tsx:168` | `SourceTree` is conditionally mounted (`open ? <SourceTree/> : null`), so each re-expand re-runs the structure fetch — no cache | **Real** (pattern confirmed at :168; `useEffect` keyed on `sourceId` re-runs on remount) | **Fix** — cache fetched structures per source in the sidebar so re-expanding reuses them | Cheap fix; repeated proxy round-trips for immutable-until-reingest data is real waste; no recorded decision conflicts |
| R2 | 3599490828 + 3599497373 (arch + regression, duplicate posts) | `frontend/app/components/library-screen.tsx:43` ↔ `frontend/app/components/shell/app-sidebar.tsx:44` | `statusVariant` status→badge mapping duplicated byte-for-byte | **Real** (both defs confirmed) | **Fix** — extract to one shared module; both components import it | Two copies of the status→badge contract will drift; trivial extraction |
| R3 | 3599490882 + 3599497331 (arch + regression, duplicate posts) | `frontend/app/components/ask-screen.tsx:94` ↔ `frontend/app/components/teach-screen.tsx:251` | `assistantView(message)` parts-reader helper duplicated verbatim | **Real** (both defs confirmed) | **Fix** — move next to the `LearnyUIMessage` contract in `app/lib/streaming.ts` and import in both screens | The helper encodes the stream-part contract; one home beside the type it reads |
| R4a | 3599486512 (tests) | `backend/app/infrastructure/db/repositories.py:464` | Duplicate-anchor → first-in-reading-order resolution is documented, load-bearing, and untested | **Real** (no duplicate-anchor test exists in `test_repositories.py`/`test_web_corpus.py`) | **Fix** — add an integration test: two sections sharing an anchor → `get_section` returns the lower `position` one | Pins the deterministic citation round-trip behavior the comment promises |
| R4b | 3599486540 (tests) | `frontend/app/lib/tree.ts:21` | `flattenSections` (shared by sidebar + teach picker) has no dedicated unit test | **Real** (no `tests/tree*` file) | **Fix** — add a unit test: nested fixture → flattened order, depth, breadcrumb label | Shared recursive util; the other new lib modules all have dedicated tests |
| — | 3599486088, 3599486479, 3599490114, 3599490771, 3599497435 (positive highlights) + PR-level 2× | various | Positive highlights / informational summaries | N/A | None | No action required |

**Outcome:** all four fixed and pushed — R2+R3 `6a02a08` (extract `statusVariant` → `app/lib/status.ts`, `assistantView` → `app/lib/streaming.ts`), R1 `e1825fe` (structure fetch lifted to `SourceItem` with per-source cache; failed fetch still retries on re-expand), R4a `fda3df5`, R4b `dd12e64`. Post-fix gates: frontend 135 passed/23 files + tsc + build; backend 657 passed, 10 skipped + ruff clean. All 14 PR comments deleted after triage (0 inline / 0 PR-level remaining; no submitted reviews).

**Totals:** 4 real / 0 false; 4 fix / 0 won't-fix. Non-blocking Verifier edge-case notes
(403-CSRF component render, mid-stream disconnect sans `error` part) were NOT raised by
the review and stay as recorded observations in `validation.md` — not expanded into
fixes here (scope discipline; mechanisms are unit-covered).
