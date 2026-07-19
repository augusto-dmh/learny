# v4-reader-core Validation

**Date**: 2026-07-19
**Spec**: `.specs/features/v4-reader-core/spec.md`
**Diff range**: `main..HEAD` (`4c55775..HEAD`; implementation `2eb7811..HEAD`; RD-05 fix `13a440a`)
**Verifier**: independent sub-agent (author ≠ verifier); evidence-or-zero, read-only over the real tree

---

## Verdict

**PASS** — 31/31 ACs traced to a spec-matching assertion. The prior gap **RD-05 (sticky chapter-title boundary)** was closed in fix commit `13a440a`: a new test asserts the top bar renders the chapter title AND its positioning container carries `sticky top-0`. All gates green (offline 825, DB-gated reader 137, frontend 324, tsc clean); 8/8 discrimination mutations killed (7 in round 1 + 1 targeted at the RD-05 fix).

---

## Task Completion

All Phase A–D tasks (A1–A6, B1–B4, C1–C4, D1–D3) are marked done in tasks.md and their commits are present in `2eb7811..HEAD`. No task blocked or partial.

---

## Spec-Anchored Acceptance Criteria

### P1 Chapter-flow reading (RD-01..06)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-01 chapter endpoint shape (sections, chapter meta, prev/next, percent) | 11-field body; sections carry anchor/title/section_path/markdown/word_count; prev null, next "c2"; word sums 0/5/10 | `backend/tests/test_web_reading.py:182` — `assert set(body) == {…11 fields…}`; `:203` `[s["anchor"] for s in sections]==["c1","c1s1"]`; `:204` `word_count==3`; `backend/tests/test_application_reading.py:138-148` | ✅ PASS |
| RD-02 unknown anchor / non-owner / missing → identical 404, no disclosure | all 404; `non_owned.json()==missing.json()` | `backend/tests/test_web_reading.py:240-244`; app `:282-296` `SourceNotFound` for intruder + missing | ✅ PASS |
| RD-03 continuous article render + DOM ids | every section in order inside one `.prose-reading`; wrapper id == anchor | `frontend/tests/chapter-reader.test.tsx:199-203` — `wrappers.map(id)==[S1,S2]`; `:220-224` `.prose-reading` present | ✅ PASS |
| RD-04 `?anchor=` in-flow scroll + transient highlight | scrollIntoView called; only target heading `data-highlight="on"` | `frontend/tests/chapter-reader.test.tsx:285-293` — `scrollIntoView` toHaveBeenCalled; flashed `on`, other `off` | ✅ PASS |
| RD-05 current chapter title stays visible via sticky boundary | chapter title rendered inside a sticky element while scrolling | `frontend/tests/chapter-reader.test.tsx:214-227` — `topBar.textContent` contains `"Chapter One"`; `stickyContainer.className` contains `"sticky"` and `"top-0"` (impl `chapter-reader.tsx:439`) | ✅ PASS |
| RD-06 prev/next chapter nav, hidden at edges | links to both adjacent chapters; absent at first/single | `frontend/tests/toc-panel.test.tsx:174-181` links encoded; `:184-188` omits prev at first; `:190-195` `container.firstChild` null single-chapter | ✅ PASS |

### P1 Reading position & progress (RD-07..13)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-07 scroll-idle debounced write, once per idle | exactly one write after 2s of a burst, last topmost anchor | `frontend/tests/use-scroll-position.test.tsx:117-120` — not called pre-idle; `toHaveBeenCalledTimes(1)`; `("s1", B, "csrf-xyz")` | ✅ PASS |
| RD-08 upsert + server-computed percent | row per (user,source); percent 30.0 at c1s1 (3/10) | `backend/tests/test_web_reading.py:298-299` `percent==30.0`; repo `test_repositories_reading.py:220-231` roundtrip; app `:314-318` | ✅ PASS |
| RD-09 invalid anchor → 404, store nothing | 404; `reading_positions` empty | `backend/tests/test_web_reading.py:333-339` 404 + `count==[]`; app `:348-352` `upsert_calls==[]` | ✅ PASS |
| RD-10 resume on open / first-chapter fallback | no-anchor loads stored chapter, else first | `frontend/tests/chapter-reader.test.tsx:506-531` resume→S2 scroll; app `:216-252` stored/first; web `:247-278` | ✅ PASS |
| RD-11 percent + minutes-left display, updates on scroll | 10%/3min at top → 40%/1min after section change | `frontend/tests/chapter-reader.test.tsx:700-715` — `"10%"`,`"3 min"` then `"40%"`,`"1 min"` | ✅ PASS |
| RD-12 last-write-wins concurrency | later write overwrites the single row | `backend/tests/test_repositories_reading.py:250-255` — `anchor=="a9"`,`percent==90.00`,`updated_at==second` | ✅ PASS |
| RD-13 write fails → usable + silent retry | rejection swallowed; retried next idle | `frontend/tests/use-scroll-position.test.tsx:148-156` — first rejects silently; 2nd call retries B | ✅ PASS |

### P1 Word counts (RD-14..16)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-14 build persists per-section word_count | word_count == whitespace-token count of markdown | `backend/tests/test_application_corpus.py:276-278` — `[record.word_count]==[2,2]` == `len(markdown.split())` | ✅ PASS |
| RD-15 migration backfills every existing row (no NULLs) | 0011 backfill matches len(split()); blank/ws → 0 | `backend/tests/test_migrations.py:1097-1098` — cases 5/1/0/0/4; `:1084-1085` NOT NULL | ✅ PASS |
| RD-16 empty markdown → 0, no divide-by-zero | word_count 0; percent 0.00 at zero total | `backend/tests/test_application_corpus.py:297` `empty.word_count==0`; `test_reading_pure.py:127-129` zero-total `Decimal("0.00")` | ✅ PASS |

### P1 Aa reading controls (RD-17..21)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-17 four controls (size/spacing/appearance/theme) | each step calls its setter | `frontend/tests/reading-controls.test.tsx:114-137` — size→23, spacing→1.8, Paper→"paper", theme→"dark"/"system" | ✅ PASS |
| RD-18 size/spacing via reader-scoped CSS vars | `.prose-reading` reads `var(--reading-size,19px)`/`var(--reading-leading,1.6)` | `frontend/tests/theme-tokens.test.ts:119-120` pins the var-with-fallback declarations; setters `reading-controls.test.tsx:114-122` | ✅ PASS |
| RD-19 Paper applies (light), chrome stays Iron Gall | `data-appearance="paper"` on `.prose-reading` only, not top-bar | `frontend/tests/reading-controls.test.tsx:179-182` — article `"paper"`, `reader-top-bar` has no attr | ✅ PASS |
| RD-20 dark overrides appearance (AD-119), axis still shown | `.dark` authoritative while attr present; night-palette note | `reading-controls.test.tsx:151-158` note visible; `:199-202` attr `"paper"` + `.dark` on `<html>` | ✅ PASS |
| RD-21 persistence + no-flash re-apply | change persisted under versioned key, read back on reload | `frontend/tests/use-reading-settings.test.tsx:43-53` — JSON blob; reloaded hook reads 23/1.8/paper | ✅ PASS |
| RD-06(defaults) 19px/1.6/Default/System | untouched defaults | `frontend/tests/use-reading-settings.test.tsx:27-31` — size 19, leading 1.6, appearance default | ✅ PASS |

### P1 In-reader TOC (RD-22..25)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-22 structure list + current position marked | current section carries `aria-current="location"`, moves with scroll | `frontend/tests/toc-panel.test.tsx:88-107` — S1 current then S2 after rerender | ✅ PASS |
| RD-23 click-to-navigate + URL update | same-chapter in-flow scroll (no push); cross-chapter push encoded | `toc-panel.test.tsx:119-122` onSameChapterNavigate(B), no push; `:130-133` push cross-chapter | ✅ PASS |
| RD-24 back-after-jump affordance | chip appears on jump-away, returns, dismisses on use/scroll | `frontend/tests/reader-chrome.test.tsx:131-135` appears; `:142-155` return+replace URL, gone; `:157-169` dismiss on scroll | ✅ PASS |
| RD-25 narrow-viewport collapse | closed hidden below lg; toggle opens | `toc-panel.test.tsx:150-156` state closed/open + `hidden`/`block`; `:158-170` top-bar toggle | ✅ PASS |

### P1 Load-path fix (RD-26..27)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-26 parallel fetches | both `/api/auth/me` and chapter dispatched before either resolves | `frontend/tests/chapter-reader.test.tsx:451-454` — `toHaveBeenCalledTimes(2)`, urls contain both | ✅ PASS |
| RD-27 401 preserved + skeleton (not bare text) | onRequireAuth fires + signed-out; skeleton, no "Loading…" | `chapter-reader.test.tsx:482-483` redirect; `:458-459` `reading-skeleton`, `queryByText("Loading…")` null | ✅ PASS |

### P2 Highlights render inline (RD-28..29)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-28 listing endpoint + ownership (all statuses) | owner-scoped 6-field rows; non-owner/unknown 404 | `backend/tests/test_web_notes.py:743-753` fields+status; `:757-773` non-owner/unknown 404; repo `test_repositories_reading.py:275-308` scoping + all statuses | ✅ PASS |
| RD-29 active-only paint, disambiguation, silent non-match | active paints in anchoring section only; stale never; dup→context; absent→null | `frontend/tests/chapter-reader.test.tsx:578-587` one mark in S1; `:606` stale 0; `highlight-paint.test.ts:38-49` ambiguous/absent→null; `:109-124` stale/orphaned/absent 0 marks; `:138-146` text unchanged | ✅ PASS |

### P2 Ink-line & receding chrome (RD-30..31)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RD-30 ink fill proportional to book percent, tokens only | `width:10%`, `bg-primary` (no raw hex) | `frontend/tests/reader-chrome.test.tsx:104-107` — `style.width=="10%"`, className has `bg-primary`; leak scan `theme-tokens.test.ts:205-233` | ✅ PASS |
| RD-31 chrome recede/restore + reduced-motion | hide on down, restore on up; `motion-reduce:transition-none` | `reader-chrome.test.tsx:78-83` down→true, up→false; `:119-121` motion-reduce class | ✅ PASS |

**Status**: ✅ All 31 ACs matched their spec-defined outcome.

---

## Edge Cases

- [x] Alias anchor resolves as a primary — `test_web_reading.py:216-220` alias 200 canonical; app `test_application_reading.py:171-184`; `test_reading_pure.py:86-95`.
- [x] Single-chapter book: prev/next absent + percent correct — `toc-panel.test.tsx:190-195` ChapterNav renders nothing; `test_reading_pure.py:69-71` single span.
- [x] Stale stored anchor → first-chapter fallback, row untouched — `test_application_reading.py:254-276` `chapter_index==0`, `upsert_calls==[]`.
- [x] Total word count 0 → percent 0, minutes 0 — `test_reading_pure.py:127-129`; `reading-client.test.ts:216-219` `minutesLeft(0)==0`.
- [x] localStorage unavailable → in-memory settings — `use-reading-settings.test.tsx:83-89` setter no-throw, nothing persisted.
- [x] Formatting-boundary non-match acceptable, never mis-paint — `highlight-paint.test.ts:38-49,119-124` null / no paint.

---

## Discrimination Sensor

Scratch-only (Edit → run targeted file → `git checkout -- <file>` → verify `git status` clean). Working tree clean after each.

| # | File:line | Mutation | Target file | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `app/application/reading.py:69` | partition boundary `depth == 0` → `depth == 1` | `test_reading_pure.py` | ✅ Killed (4 failed) |
| 2 | `app/application/reading.py:104` | percent off-by-one `index[:row_idx]` → `index[:row_idx + 1]` | `test_reading_pure.py` | ✅ Killed (2 failed) |
| 3 | `app/application/reading.py:90` | locate precedence: alias returns immediately (breaks canonical-wins) | `test_reading_pure.py` | ✅ Killed (1 failed) |
| 4 | `app/application/reading.py:260` | SaveReadingPosition stores `anchor` not `index[target_idx].anchor` (alias→canonical) | `test_application_reading.py` | ✅ Killed (1 failed) |
| 5 | `app/lib/highlight-paint.ts:57` | findQuoteOffset ambiguity `matches.length === 1` → `>= 1` (returns first match) | `highlight-paint.test.ts` | ✅ Killed (1 failed) |
| 6 | `app/lib/highlight-paint.ts:90` | active-only filter inverted `!== "active"` → `=== "active"` | `highlight-paint.test.ts` | ✅ Killed (4 failed) |
| 7 | `app/components/chapter-reader.tsx:301` | percent denominator drops `words_before_chapter` | `chapter-reader.test.tsx` | ✅ Killed (1 failed) |
| 8 | `app/components/chapter-reader.tsx:439` | RD-05 re-verify: `sticky top-0 z-20` → `top-0 z-20` (drop `sticky`) | `chapter-reader.test.tsx` | ✅ Killed (RD-05 test only) |

**Sensor depth**: lightweight+ (8 mutations across backend-pure, backend-app, frontend-pure, frontend-component; #8 targeted at the RD-05 fix).
**Result**: 8/8 killed — ✅.

---

## Gate Check

| Gate | Command | Result |
| --- | --- | --- |
| Backend offline | `.venv/bin/python -m pytest -q` | **825 passed**, 429 skipped, 0 failed |
| DB-gated reader modules | `pytest -q` on the 8 listed files w/ `LEARNY_TEST_DATABASE_URL` | **137 passed**, 0 failed |
| Frontend | `npm test` | **324 passed** (38 files), 0 failed (was 323; +1 RD-05 test) |
| Typecheck | `npx tsc --noEmit` | exit 0, clean |

`test_web_corpus.py` excluded per instructions (documented MinIO-503 noise, unrelated). No test count decrease; assertions not weakened.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / surgical changes | ✅ |
| No scope creep (Out-of-Scope table respected: no pagination, no virtualization, prefs device-local) | ✅ |
| Matches existing patterns (ReadSection ownership shape, AD-071 fetchImpl/routedFetch, AD-118 CSS pins) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a spec AC / edge / Done-when — no unclaimed tests | ✅ |
| Documented guidelines followed | ✅ (`CLAUDE.md`, `.specs/STATE.md` AD-071/AD-118, `vitest.config.ts`, `ci.yml`) |

---

## Fix Plans

### Fix 1: RD-05 sticky chapter-title boundary has no test — RESOLVED (`13a440a`)

- **Root cause (round 1)**: The chapter title rendered inside `<div className="sticky top-0 z-20">` (`chapter-reader.tsx:439`), satisfying the AC in code, but no test asserted the title renders or that it sits in a sticky boundary. Evidence-or-zero → uncovered.
- **Fix applied**: `chapter-reader.test.tsx:214-227` — asserts `topBar.textContent` contains the chapter title and `stickyContainer.className` contains `sticky` + `top-0`.
- **Re-verified**: assertion matches RD-05's spec outcome; targeted mutation (drop `sticky` from the container) failed the RD-05 test only (sensor #8), confirming it is discriminating. ✅ Closed in one iteration.

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| RD-01..31 (all 31) | Design/Done | ✅ Verified |

---

## Distilled Lesson (candidate — not written to disk per orchestrator's "commit nothing")

Presentational "SHALL remain visible via a sticky/pinned element" ACs are easy to implement and easy to leave untested — the fixture data carries the value but no assertion targets it. When an AC names a layout affordance (sticky, pinned, fixed), pin both that the content renders and that its container carries the positioning class, the same way CSS-pin tests (AD-118) pin declarations jsdom cannot apply.

---

## Summary

**Overall**: ✅ Ready — all 31 ACs verified, RD-05 gap closed and re-verified.

**Spec-anchored check**: 31/31 ACs matched spec outcome.
**Sensor**: 8/8 mutations killed (7 round-1 + 1 RD-05 re-verify).
**Gate**: 825 backend offline + 137 DB-gated reader + 324 frontend, 0 failed; tsc clean.

**What works**: chapter endpoint shape/ownership/aliases, resume + first-chapter fallback, server-computed percent + minutes-left, word-count build + migration backfill, sticky chapter-title boundary, Aa four-axis controls with reader-scoped vars + Paper/dark semantics, TOC position context + jump/return + collapse, parallel load + skeleton, active-only inline highlight painting with disambiguation, ink-line + receding chrome.

**Issues found**: none outstanding.

**Next steps**: ready to proceed (publish / merge gate).
