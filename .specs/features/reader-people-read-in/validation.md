# reader-people-read-in Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/reader-people-read-in/spec.md`
**Diff range**: `32142484^..5903b542` (`32142484` planning; `fd08cd9f`..`5903b542` implementation). Unrelated gitignore chore `a17fd760` is not in this range.
**Verifier**: independent sub-agent (author ≠ verifier)
**Verdict**: ✅ PASS

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | ✅ Done | `fd08cd9f` — Pillow encoder + caps; all Done-when boxes checked |
| T2 | ✅ Done | `aea16fab` — `ParsedBook.media` |
| T3 | ✅ Done | `c7e13efe` — markdown rewrite |
| T4 | ✅ Done | `90e91db2` — BuildCorpus store + rewrite |
| T5 | ✅ Done | `88381d07` — owner GET 200 / else 404 |
| T6 | ✅ Done | `8be1d532` — env examples |
| T7 | ✅ Done | `86278893` — chapter Streamdown allowlist |
| T8 | ✅ Done | `6eab9b93` — paint skip `img` |
| T9 | ✅ Done | `c5ad3245` — `(read)` route group |
| T10 | ✅ Done | `1d8fcc86` — `[` / `]` + overlay 65ch |
| T11 | ✅ Done | `fb640a07` — bottom sheet below `lg` |
| T12 | ✅ Done | `87eaa2c7` — pointerup / selectionchange |
| T13 | ✅ Done | `c272b451` — Highlight-first compact bar |
| T14 | ✅ Done | `99ce8ea4` — 44px targets |
| T15 | ✅ Done | `5903b542` — no H-scroll at 200% |

Working tree at verify time: one uncommitted checkbox in `spec.md` (phone goal marked done). Product code unchanged. Sensor ran in `/tmp/learny-verify-reader` worktree and was removed.

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| READ-01 packaged raster ingest → same-origin markdown URL, no EPUB-relative `src` | `![alt](/api/sources/{source_id}/media/{sha256})`; `cover.png` absent | `backend/tests/test_application_corpus.py:715-716` — `f"![Cover image]({expected_url})" in markdown` and `"cover.png" not in markdown`; `backend/tests/test_application_media.py:27-29` — rewritten equals that URL shape | ✅ PASS |
| READ-02 stored bytes → object key via `put_object` | `sources/{user_id}/{source_id}/media/{sha256}.webp` | `backend/tests/test_application_corpus.py:710-712` — `(key, "image/webp") in storage.put_calls` and `storage.objects[key] == _WEBP_BYTES` | ✅ PASS |
| READ-03 oversize long edge or encoded bytes | downscale until `media_max_edge_px` (1600) and `media_max_bytes` (1572864) hold, or drop | `backend/tests/test_config.py:165-166` — defaults `== 1600` / `== 1572864`; `backend/tests/test_ingestion_images.py:114-116` — `max(encoded.size) <= settings.media_max_edge_px`; `:125-127` — `len(result.data) <= 80` or `None` | ✅ PASS |
| READ-04 SVG / undecodable | no `put_object`, no image URL; non-empty alt → emphasis; empty alt → omit | `backend/tests/test_ingestion_images.py:59` — SVG encode `is None`; `backend/tests/test_application_corpus.py:753-755` — `"*Gone*" in markdown` and `"bad.png" not in markdown`; `:817-819` — no `/api/sources/` / `![` after empty-alt | ✅ PASS |
| READ-05 owner GET stored figure | 200, `Content-Type: image/webp`, stored bytes | `backend/tests/test_web_sources.py:617-619` — `status_code == 200`, `headers["content-type"] == "image/webp"`, `resp.content == FIGURE_BYTES` | ✅ PASS |
| READ-06 stranger / missing / malformed hash GET | 404, never 403 | `backend/tests/test_web_sources.py:631` — cross-user `== 404`; `:641` missing hash `== 404`; `:651` missing blob `== 404`; `:662-669` uppercase/short/non-hex `== 404` | ✅ PASS |
| READ-07 rewritten figure markdown in chapter | `<img>` whose `src` starts with `/api/sources/`; no `[Image blocked` | `frontend/tests/chapter-markdown.test.tsx:42-45` — `src.startsWith("/api/sources/")`, `src === MEDIA_SRC`, text not `[Image blocked`; `frontend/tests/chapter-reader.test.tsx:371-375` same in `ChapterFlow` | ✅ PASS |
| READ-08 `http:` / `https:` / `data:` / EPUB-relative; `allowDataImages` false | those srcs not fetched; no `data:` img | `frontend/tests/chapter-markdown.test.tsx:60-72` — `[Image blocked: hostile]` and src not evil/http/data; `:83` — `img[src^='data:']` is null | ✅ PASS |
| READ-09 `paintHighlights` on a section with `<img>` | does not wrap the image | `frontend/tests/highlight-paint.test.ts:165-166` — `figure.closest("mark")` / `querySelector("mark")` null; `:181-182` quote only inside img → marks length 0 | ✅ PASS |
| READ-10 image extract rewrite | `html_fragment` and `content_hash` unchanged vs un-rewritten parse | `backend/tests/test_application_corpus.py:783-788` — `html_fragment == _COVER_HTML`; `block_hashes[1] == sha256(normalize(raw_markdown))` with `raw_markdown == "![Cover image](cover.png)"` | ✅ PASS |
| READ-11 no EPUB HTML iframe; no `allow-scripts` / `allow-same-origin` sandbox | no iframe / sandbox on chapter renderer | `frontend/tests/chapter-markdown.test.tsx:97-99` — `iframe` null, `[sandbox]` null; `frontend/tests/chapter-reader.test.tsx:345-349` — no live `<script>` / `onerror` | ✅ PASS |
| READ-12 one image decode/encode failure | ingest continues; that image omitted; job does not fail | `backend/tests/test_application_corpus.py:749-755` — `len(replace_calls) == 1`; one media key; Keep URL present; Gone emphasized | ✅ PASS |
| READ-13 same raster bytes twice | identical object key hash | `backend/tests/test_ingestion_images.py:106-107` — `first.data == second.data` and `first.sha256 == second.sha256` (key is that sha256) | ✅ PASS |
| READ-14 Ask/Teach `MessageResponse` harden | no chapter allowlist leak | `frontend/tests/cited-answer.test.tsx:353` — generated answer still has `img src="https://evil.example/x.png"`; `:358-360` — `message.tsx` source not contain `allowedImagePrefixes` / `/api/sources/` / `allowDataImages` | ✅ PASS |
| READ-15 reintroduced EPUB-relative `src` in derived markdown | that test fails | `backend/tests/test_application_corpus.py:716` — `"cover.png" not in markdown`; `backend/tests/test_application_media.py:29` — `"cover.png" not in rewritten` | ✅ PASS |
| READ-16 `/read` shown | `AppSidebar` and `AuthHeader` absent from the document; other `(app)` routes still render both | `frontend/tests/read-page.test.tsx:59-64` — Bookshelf/Account/Log out/theme/email queries null; `frontend/tests/app-shell.test.tsx:180-182` — `(app)` still has email + Bookshelf; `:204-207` — `(read)` layout has neither | ✅ PASS |
| READ-17 focused `[` / `]` without modifier, not in input | `[` toggles TOC; `]` toggles dock via `?panel=` | `frontend/tests/chapter-reader.test.tsx:2100-2107` — `[` → TOC `data-state` open then closed; `:2132-2134` — `]` → `replace(".../read?panel=ask")`; `:2144-2146` — second `]` drops panel; `:2117-2122` / `:2156-2158` input/modifier ignored | ✅ PASS |
| READ-18 `/read` with no `?panel=` | TOC starts closed; dock closed unless `?panel=` names a tab | `frontend/tests/chapter-reader.test.tsx:2081-2090` — TOC `data-state` closed + `hidden`, no `reader-panel`, both `aria-expanded` false | ✅ PASS |
| READ-19 dock open, viewport `< xl` | dock overlays; `.prose-reading` max-width stays `65ch` | `frontend/tests/reading-column.test.tsx:214-222` — `getComputedStyle(prose).maxWidth === "65ch"`; panel classes contain `max-xl:fixed` / `max-xl:inset-y-0` / `max-xl:right-0`, not bare `shrink-0`; CSS source `max-width` is `65ch` | ✅ PASS |
| READ-20 thin reader chrome | progress, `Aa`, TOC and dock icon buttons remain; receding still applies | `frontend/tests/chapter-reader.test.tsx:2168-2176` — bar has `transition-transform`, progress, Reading settings, TOC/dock buttons inside bar; `frontend/tests/reader-chrome.test.tsx:120-122` — `motion-reduce:transition-none` | ✅ PASS |
| READ-21 test mounts `/read` inside app shell | that test fails | `frontend/tests/read-page.test.tsx:44-49` — `(app)/.../read/page.tsx` `existsSync` false, `(read)/...` true; `:59-64` shell queries empty | ✅ PASS |
| READ-22 viewport `< lg`, dock open | bottom `Sheet` `side="bottom"`, not `w-[26rem]` side column | `frontend/tests/reader-panel.test.tsx:568-572` — `data-side === "bottom"`, neither sheet nor panel has `w-[26rem]`; `:585-593` at `lg` sheet null and panel has `w-[26rem]` | ✅ PASS |
| READ-23 pointer or touch selection release | capture appears (not `mouseup`-only) | `frontend/tests/chapter-reader.test.tsx:448-451` — `pointerup` only → Capture highlight dialog + Highlight; `:472-474` — `selectionchange` opens dialog | ✅ PASS |
| READ-24 capture below `lg` | Highlight is primary; remaining verbs behind overflow | `frontend/tests/capture-popover.test.tsx:183-194` — Highlight in `capture-verb-row`; Explain/Ask/Note/Create card null in row until overflow; `:202-209` — `lg+` five-verb bar, no overflow | ✅ PASS |
| READ-25 new/relocated `/read` targets | min CSS size 44×44px | `frontend/tests/chapter-reader.test.tsx:2189-2190` — TOC/dock `minWidth`/`minHeight` ≥ 44; `frontend/tests/capture-popover.test.tsx:217-218` Highlight; `:227-228` overflow; `frontend/tests/reader-panel.test.tsx:605-606` sheet Close | ✅ PASS |
| READ-26 200% zoom on 320px-wide layout | article does not require horizontal scrolling | `frontend/tests/reading-column.test.tsx:264-265` — `.prose-reading img` `max-width: 100%`; `:303-304` — `article.scrollWidth <= article.clientWidth` at 320px / zoom 2 with a figure | ✅ PASS |

**Status**: ✅ All 26 ACs covered — asserted values match spec-defined outcomes; 0 spec-precision gaps

---

## Discrimination Sensor

Scratch: `git worktree add /tmp/learny-verify-reader HEAD` (symlinked `.venv` / `node_modules` only). Each mutant restored with `git checkout -- <file>` before the next. Worktree removed. Real tree product code unchanged (only the pre-existing `spec.md` checkbox).

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `backend/app/application/sources.py:128-131` | Non-owner `NotAuthorized` re-raised (403) instead of collapsed to `SourceNotFound` (404) | ✅ Killed — `test_get_cross_user_media_returns_404` `assert 403 == 404` |
| 2 | `backend/app/application/corpus.py:168` | `block_hashes` hashed **rewritten** markdown instead of pre-rewrite `block_texts` | ✅ Killed — `test_html_fragment_hash_matches_pre_rewrite_markdown` |
| 3 | `frontend/components/ai-elements/message.tsx:328-335` | Leaked `allowedImagePrefixes={["/api/sources/"]}` onto `MessageResponse` | ✅ Killed — `cited-answer.test.tsx` source scan (`allowedImagePrefixes` / `/api/sources/`) |
| 4 | `frontend/app/globals.css:182` | `.prose-reading { max-width: 65ch }` → `40ch` | ✅ Killed — `reading-column.test.tsx` `declaration(..., "max-width") === "65ch"` |
| 5 | `frontend/app/components/reader-panel.tsx:341` | Inverted `if (belowLg)` → `if (!belowLg)` (sheet at `lg+`, side column below) | ✅ Killed — READ-22 sheet vs `w-[26rem]` tests |
| 6 | `frontend/app/lib/highlight-paint.ts:131` | Dropped `\|\| element.tagName === "IMG"` from the tree-walker reject | ✅ Killed — quote only inside img painted a `mark` |

**Sensor depth**: P0-full (≥5 targeted behavior-level mutations on media 404, hash stability, Streamdown allowlist, 65ch overlay, sheet-only-below-`lg`)
**Result**: 6/6 killed — PASS ✅

---

## Interactive UAT Results (if performed)

| # | Test | Result | Details |
| --- | --- | --- | --- |
| 1 | Browser / interactive UAT | ⏭️ Skip | Ship-cycle defers browser checks to Stage 7 merge gate |

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ — `eval_runner.py` / worker `encoder=` are required now that `BuildCorpus` takes `ImageEncoderPort` |
| Matches patterns | ✅ — ports/adapters, ownership 404 collapse, Streamdown harden isolated to chapter |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ — encoder/rewrite/corpus unit; media GET owner 200 + stranger/missing/malformed 404; chapter vs answer Streamdown; shell/keys/sheet/capture |
| Every test maps to a spec requirement — no unclaimed tests | ✅ — new tests map to READ-01..26 or listed edge cases; pre-existing tests in touched files remain prior-feature ACs |
| Documented guidelines followed: `CLAUDE.md` (`make lint`, cycle pytest, `npm test`), tasks.md Test Coverage Matrix | ✅ |

---

## Edge Cases

- [x] Uppercase / short / non-hex media hash → 404 — `backend/tests/test_web_sources.py:654-669`
- [x] `get_object` miss after a rewritten URL → 404 — `backend/tests/test_web_sources.py:644-651`
- [x] `alt` markdown metacharacters copied verbatim — `backend/tests/test_application_media.py:56-65`
- [x] Two images MAY share one content-addressed key — key is `encoded.sha256`; identical bytes → identical digest (`test_ingestion_images.py:101-107`). Spec is MAY, not SHALL.
- [x] Capture selection including a figure still uses served markdown; no image-highlight verb — `frontend/tests/chapter-reader.test.tsx:500-527`
- [x] `prefers-reduced-motion`: receding chrome keeps `motion-reduce:transition-none` (`frontend/tests/reader-chrome.test.tsx:118-122`); sheet adds `motion-reduce:animate-none motion-reduce:transition-none` (`frontend/app/components/reader-panel.tsx:354`)

---

## Gate Check

- **Gate command**: `cd /home/augusto/projects/learny && make lint` plus cycle backend files and `cd frontend && npm test`
- **Result**: lint passed; 160 backend cycle passed, 0 failed, 0 skipped; 821 frontend passed, 0 failed, 0 skipped
- **Test count before feature**: 2865 (`def test_` + `it(` at `32142484^`)
- **Test count after feature**: 2938 at `HEAD` (vitest reports 821 including `it.each` expansions)
- **Delta**: +73 new tests (count did not decrease)
- **Skipped tests**: none
- **Failures**: none
- **Notes**: one Starlette/`httpx` deprecation warning from `TestClient` (pre-existing). `make infra` was already up (`db`/`minio`/`redis`). Env: `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`

Cycle backend files: `tests/test_ingestion_images.py tests/test_config.py tests/test_ingestion_epub_parser.py tests/test_domain_entities.py tests/test_application_media.py tests/test_application_corpus.py tests/test_ingestion_markup.py tests/test_web_sources.py` — 160 passed.

---

## Fix Plans (if issues found)

None.

---

## Requirement Traceability Update

Update spec.md requirement statuses:

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| READ-01..READ-26 | Done | ✅ Verified |

Goals 1–2 and Success Criteria 1–4 marked complete in `spec.md` (phone goal was already checked in the working tree).

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 26/26 ACs matched spec outcome | 0 spec-precision gaps
**Sensor**: 6/6 mutations killed
**Gate**: lint + 160 backend + 821 frontend passed

**What works**: Packaged rasters re-encode to capped WebP, land at content-addressed keys, and render as same-origin chapter `<img>`s; media GET is owner-200 / everyone-else-404; Ask/Teach harden is unchanged; `/read` leaves the app shell; `[` / `]` toggle TOC/dock without shrinking 65ch below `xl`; below `lg` the dock is a bottom sheet with Highlight-first 44px capture and no horizontal overflow at 320px/200% zoom.

**Issues found**: none

**Next steps**: Stage 7 merge-gate browser UAT (deferred). Do not commit from this verifier.
