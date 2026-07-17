# v2-frontend Validation

**Date**: 2026-07-16
**Spec**: `.specs/features/v2-frontend/spec.md`
**Diff range**: `2041577..0c68f33` (feat/v2-frontend HEAD `0c68f337d10a12ffaaae29971262fe43f2cbe4e1`; 20 commits)
**Verifier**: independent sub-agent (author ≠ verifier); evidence re-derived from tests, no author claims trusted

---

## Task Completion

All 20 tasks (A1–A4, B1–B5, C1–C5, D1–D4, E1–E2) marked done in tasks.md. No blocked/partial tasks. Diff surface: `frontend/` (rebuilt UI + tests) + one new backend read endpoint (`get_section`/`ReadSection`/`GET /api/sources/{id}/section`).

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| **FE-01** frontend builds with Tailwind v4 + shadcn + AI Elements; build/tsc/vitest pass | All three gates exit 0 | Gate evidence (config-only AC): `frontend` — vitest 130 passed/22 files, `tsc --noEmit` exit 0, `next build` exit 0 | ✅ PASS |
| **FE-02** theme toggle switches light/dark AND persists across reload | `dark` class on `<html>`; `localStorage.theme==="dark"`; restored on remount | `frontend/tests/theme-provider.test.tsx:54` — `expect(document.documentElement.classList.contains("dark")).toBe(true)`; `:55` — `localStorage.getItem("theme")).toBe("dark")`; `:67` restore on fresh mount; `frontend/tests/app-shell.test.tsx:160-161` | ✅ PASS |
| **FE-03** shell renders on authed routes; no shell on login/register | `(app)` layout has header+sidebar; `(auth)` layout shell-free | `frontend/tests/app-shell.test.tsx:194-196` — email + "Library" + page content; `:206-208` — `queryByText("Library")).toBeNull()` for `(auth)` | ✅ PASS |
| **FE-04** sidebar lists sources w/ badges; ready expand to tree; links to Ask/Teach/Read; tree click → reader anchor | Status text per source; tree from structure; encoded anchor href | `frontend/tests/app-sidebar.test.tsx:139-141` badges; `:155-161` Ask/Teach/Read hrefs; `:180-181` tree expands; `:200-202` — `href` = `/sources/s-ready/read?anchor=text%2Fchapter-1.xhtml%23core-idea` | ✅ PASS |
| **FE-05** logout or any 401 → redirect `/login` | `router.replace("/login")` | `frontend/tests/app-shell.test.tsx:134` — logout `replace("/login")`; `:172` — 401 from `/me` `replace("/login")`; per-screen: `ask-screen.test.tsx:339`, `teach-screen.test.tsx:433` | ✅ PASS |
| **FE-06** submit → POST `{question}` + `X-CSRF-Token` to stream URL | body exactly `{question:<text>}`, header present | `frontend/tests/ask-screen.test.tsx:142-147` — `JSON.parse(body)).toEqual({question:...})` + `X-CSRF-Token` "csrf-xyz"; `streaming.test.ts:87-89` api/body/headers | ✅ PASS |
| **FE-07** text-delta parts render progressively before finish | partial text visible pre-finish | `frontend/tests/ask-screen.test.tsx:153-156` — contains "Ada Lovelace" AND not the later text before finish | ✅ PASS |
| **FE-08** terminal citations render; `not_found_in_source` → distinct state, no citations | citation chip on answered; not-found node + no citation chips | `frontend/tests/ask-screen.test.tsx:179-181` — Citation chip; `:212-215` — `not-found` testid + `queryByRole(/^Citation:/)).toBeNull()` | ✅ PASS |
| **FE-09** error part / non-OK (incl. 429) / stop → readable state, partial retained, input re-enabled | `role="alert"` message, partial text kept, textarea `disabled===false` | `frontend/tests/ask-screen.test.tsx:245-251` (error part); `:268-273` (429 readable + re-enabled) | ✅ PASS |
| **FE-10** in-flight → submit disabled; empty never submits | Stop replaces Submit, one request; no POST on empty | `frontend/tests/ask-screen.test.tsx:293-299` — Stop shown, `queryByRole Submit` null, 1 request; `:321-323` — no stream POST on empty | ✅ PASS |
| **FE-11** Teach open → target picker + resume list w/ turn counts | flattened section options; "N turns" | `frontend/tests/teach-screen.test.tsx:222-226` — options incl. nested "Chapter 1 › Section 1.1"; `:396` — `getByText(/2 turns/)` | ✅ PASS |
| **FE-12** send → POST `{message}` to turns stream; resume renders persisted turns + citations | body `{message}`+CSRF; seeded history w/ citation | `frontend/tests/teach-screen.test.tsx:252-257` — `{message:...}`+`X-CSRF-Token`; `:401-405` — resumed turn text + `Citation: Chapter 1 › Intro` | ✅ PASS |
| **FE-13** teach error/429/not_found → same contract as Ask | alert message / not-found node | `frontend/tests/teach-screen.test.tsx:319-320` not-found; `:341` 429 alert; `:373-374` error part alert + partial text | ✅ PASS |
| **FE-14** owner GET section → 200 shape; 404 missing/non-owner/no-corpus/unknown-anchor; 401 unauth | exact 200 body + each 404 + 401 (+422 empty) | `backend/tests/test_web_corpus.py:255-260` 200 shape (anchor/title/section_path/markdown); `:274` unknown-anchor 404; `:286` 401; `:294` missing 404; `:309` non-owner 404; `:323` no-corpus 404; `:336/:339` empty/missing anchor 422. Repo: `test_repositories.py:858-862` hit, `:881` unknown None, `:907` cross-source None | ✅ PASS |
| **FE-15** reader loads → fetch section, render markdown, scroll into view + transient highlight | markdown text; `data-highlight="on"`; scrollIntoView called | `frontend/tests/section-reader.test.tsx:97-102` markdown; `:127` `data-highlight==="on"`; `:130` `scrollIntoView` called | ✅ PASS |
| **FE-16** citation click → popover (path+snippet+"Open in book") navigates to reader anchor | breadcrumb + snippet + encoded href | `frontend/tests/citations.test.tsx:57-58` breadcrumb+snippet; `:63-65` href `/sources/s1/read?anchor=part1%2Fchapter-1.xhtml%23core-idea`; loop `citation-reader-loop.test.tsx:167-168,187` | ✅ PASS |
| **FE-17** reader unknown anchor → not-found; no anchor → pick-a-section empty | readable not-found + back link; empty state, no fetch | `frontend/tests/section-reader.test.tsx:145-148` not-found + back-to-library href; `:159-162` empty state + no fetch | ✅ PASS |
| **FE-18** ingestion client GETs `/api/sources/{id}/ingestion` | GET, same-origin, no CSRF, parsed summary | `frontend/tests/ingestion-client.test.ts:100-106` — url/method GET/credentials/no `X-CSRF-Token`; `:114-116` 401 error | ✅ PASS |
| **FE-19** processing source polls every 3s, updates badge, stops on terminal + unmount | fires at 3s; patch ready/failed; no further polls after terminal/unmount | `frontend/tests/use-ingestion-polling.test.tsx:69-70` 3s + arg; `:83` ready; `:94` failed; `:108-109` stops after terminal; `:124-125` cleared on unmount; `:143-144` failed tick skipped | ✅ PASS |
| **FE-20** failed → latest event message visible + restart control | exact message text + Restart button | `frontend/tests/sources-screen.test.tsx:410` — `failure-s-fail` text "EPUB is missing its spine."; `:412-414` Restart ingestion button | ✅ PASS |
| **FE-21** library upload control styled; validation/errors readable | upload error alert; nothing added; empty-file validation | `frontend/tests/sources-screen.test.tsx:201-204` API-reject error + nothing added; `:223` "Choose an EPUB file to upload." | ✅ PASS |
| **FE-22** SSE relay unbuffered; streaming headers survive; encoding/length stripped | first chunk readable before close; 3 headers kept; 2 stripped | `frontend/tests/proxy-forwarding.test.ts:155-160` headers kept/stripped; `:167-169` chunk-1 read while upstream open; `:174-175` chunk-2 in order | ✅ PASS |

**Status**: ✅ 22/22 ACs covered with assertions matching the spec-defined outcome. 0 uncovered, 0 spec-precision gaps on ACs.

---

## Discrimination Sensor

Standard-risk feature; 6 behavior-level mutations across backend + frontend layers, each mutate → run covering test(s) → revert; working tree verified clean of every mutation.

| # | File:line | Description | Covering test(s) | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `backend/app/application/corpus.py:189` | `ReadSection`: removed `authorized_source(...)` ownership check | `test_web_corpus.py` | ✅ Killed — `test_section_non_owner_source_returns_404` got 200 (1 failed) |
| 2 | `backend/app/infrastructure/db/repositories.py:463` | `get_section`: dropped `anchor == anchor` WHERE (returns first section) | `test_repositories.py`, `test_web_corpus.py` | ✅ Killed — 3 failed (hit/unknown-None/unknown-404) |
| 3 | `frontend/app/lib/proxy.ts:65` | `relayResponse`: stopped stripping `content-encoding` | `proxy-forwarding.test.ts` | ✅ Killed — 2 failed (D1 header strip + FE-22 SSE relay) |
| 4 | `frontend/app/lib/streaming.ts:131` | `prepareSendMessagesRequest`: sent full `{messages}` instead of `{question}` | `streaming.test.ts`, `ask-screen.test.tsx` | ✅ Killed — 2 failed (body-shape asserts both files) |
| 5 | `frontend/app/components/ask-screen.tsx:175` | Dropped the `not_found_in_source` branch (`notFound=false`) | `ask-screen.test.tsx` | ✅ Killed — 1 failed (not-found state test) |
| 6 | `frontend/app/components/use-ingestion-polling.ts:57-61` | Never `clearInterval` on terminal status | `use-ingestion-polling.test.tsx` | ✅ Killed — 1 failed (stops-polling-once-terminal) |

**Sensor depth**: lightweight ×6 (2 backend seams incl. the P0-ish auth-scoped ownership check + anchor filter; 4 frontend incl. the P0-ish stream error/proxy relay seams).
**Result**: 6/6 killed — ✅ PASS. No surviving mutants → no fix tasks.

---

## Edge Cases

- [x] Empty library → empty state + upload affordance — `app-sidebar.test.tsx:217-219`, `sources-screen.test.tsx:161`.
- [x] Deep TOC (≤4 levels) navigable via collapsible nesting — nested section rendered on expand `app-sidebar.test.tsx:180-181`; flattened nested option `teach-screen.test.tsx:223-225`.
- [x] Raw HTML in section markdown NOT injected as live DOM — `section-reader.test.tsx:184-190` (`querySelector("script")` null, no `onerror`, `__xss` undefined).
- [x] Source not ready (409) → readable "not ready" message — `errorMessageFor(409)` "still processing" unit-asserted `streaming.test.ts:174`; rendered via the non-OK→banner path exercised at 429 (`ask-screen.test.tsx:268-273`, `teach-screen.test.tsx:341`).
- [~] CSRF missing/stale (403) → error state, no crash — mechanism covered: `errorMessageFor(403)` unit-asserted `streaming.test.ts:172` and non-OK start → banner path proven at 429; no dedicated 403 *component* render test. Minor observation (same code path), not a gap.
- [~] Stream disconnects mid-answer without an `error` part → settle non-streaming, partial retained — the SDK-settle-on-close path is exercised (stop/`done()` → Stop button clears, `ask-screen.test.tsx:301-304`), but no dedicated test closes the body mid-answer *without* a `finish`. Minor observation; retention + no-forever-spinner behavior is otherwise asserted.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / no scope creep beyond spec | ✅ — one new backend endpoint (FE-14, only stated gap); UI rebuild per D-1..D-7 |
| Surgical changes, matches existing patterns | ✅ — `ReadSection` mirrors `ReadSourceStructure`; clients follow `fetchImpl`-injection convention; `streaming.ts` isolates the protocol as designed |
| Spec-anchored outcome check (asserted values match spec) | ✅ — assertions target values/state (bodies, statuses, DOM), not call counts |
| Per-layer coverage: repo integration hit+miss+isolation; route happy+edge+error; components happy+not-found+error+disabled | ✅ |
| Every test maps to a spec AC / edge case / Done-when | ✅ — no unclaimed tests observed |
| Documented guidelines followed | ✅ — AD-071 test conventions (node `fetchImpl`, jsdom `routedFetch` + v1 SSE fixtures); accepted deviations recorded in context.md (incl. the `citations.tsx` SPEC_DEVIATION for book-anchor popover) |

---

## Gate Check

- **Frontend** (`cd frontend && npx vitest run && npx tsc --noEmit && npm run build`):
  - vitest: **130 passed / 22 files**, exit 0
  - `tsc --noEmit`: exit 0
  - `npm run build`: exit 0
- **Backend** (`cd backend && uv run pytest -q && uv run ruff check .`, `LEARNY_TEST_DATABASE_URL` set, DB up):
  - pytest: **656 passed, 10 skipped** (skips justified: OpenAI live key unset / no committed generation snapshots), exit 0
  - `ruff check .`: All checks passed, exit 0
- Test-integrity: counts match tasks.md expectations (frontend 130/22, backend 656) — no decrease, no weakened assertions observed.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| FE-01..FE-22 | Implemented — verification pending | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 22/22 ACs matched the spec-defined outcome; 0 spec-precision gaps on ACs.
**Sensor**: 6/6 mutations killed.
**Gate**: frontend 130 passed + tsc + build (all exit 0); backend 656 passed / 10 skipped + ruff clean.

**What works**: Full vertical slice restored — styled shell + navigation (FE-03/04/05), streaming Ask (FE-06..10) and Teach with resume (FE-11..13), citation → reader round-trip for hostile `/`+`#` anchors (FE-14..17), 3s ingestion polling with terminal/unmount cleanup (FE-18..20), upload UX (FE-21), and the unbuffered SSE proxy relay regression test (FE-22). The two P0-ish seams (owner-scoped section endpoint; stream/proxy error handling) both have discriminating tests.

**Issues found**: None blocking. Two spec Edge Cases (403 CSRF component render; mid-stream disconnect without an `error` part) are covered by the shared code path and unit-level message mapping but lack a dedicated component test — minor observations, not gaps.

**Next steps**: Proceed to publish/review. Optional (non-blocking) hardening: add one component test that closes the SSE body mid-answer without a `finish`, and one that renders the 403 banner, to convert the two edge-case observations into direct evidence.
