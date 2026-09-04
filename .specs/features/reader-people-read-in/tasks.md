# reader-people-read-in Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/reader-people-read-in/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines: `CLAUDE.md` (`make infra`, `make test-backend`, `make test-frontend`, `make lint`), pytest under `backend/tests/`, vitest + Testing Library under `frontend/tests/`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Image encoder adapter | unit | SVG drop, empty-alt omit path is markdown's job; raster → webp; oversize downscale; bomb/undecodable → None; same bytes → same sha256 | `backend/tests/test_ingestion_images.py` | `cd backend && uv run pytest tests/test_ingestion_images.py` |
| Markdown rewrite | unit | href map rewrites src; html_fragment not passed in; alt metacharacters not nested markdown | `backend/tests/test_application_media.py` | `cd backend && uv run pytest tests/test_application_media.py` |
| EPUB parser media | unit | ITEM_IMAGE bytes appear on `ParsedBook.media`; document-only spine unchanged | `backend/tests/test_ingestion_epub_parser.py` | `cd backend && uv run pytest tests/test_ingestion_epub_parser.py` |
| BuildCorpus wiring | unit/integration | markdown URL shape; put_object key; one bad image does not fail job; html_fragment hash unchanged | `backend/tests/test_application_corpus.py` (or sibling) | `cd backend && uv run pytest tests/test_application_corpus.py` |
| Media HTTP | integration | owner 200 webp; stranger 404; missing 404; malformed hash 404 | `backend/tests/test_web_sources.py` | `cd backend && uv run pytest tests/test_web_sources.py` |
| Settings | unit | defaults 1600 / 1572864 | `backend/tests/test_config.py` | `cd backend && uv run pytest tests/test_config.py` |
| Chapter Streamdown | unit (jsdom) | `/api/sources/` → `<img>`; `https://evil` and `data:` not fetched; MessageResponse answers unchanged | `frontend/tests/chapter-reader.test.tsx` (or `chapter-markdown.test.tsx`) | `cd frontend && npm test -- chapter-reader chapter-markdown cited-answer` |
| Highlight paint | unit | `img` not wrapped | `frontend/tests/` highlight-paint | `cd frontend && npm test -- highlight-paint` |
| `/read` shell | unit | no AppSidebar/AuthHeader; other app routes still have them | `frontend/tests/app-shell.test.tsx` + read page test | `cd frontend && npm test -- app-shell read` |
| Shortcuts / measure | unit | `[` TOC `]` dock; 65ch with overlay dock | `frontend/tests/chapter-reader.test.tsx` `reading-column.test.tsx` | `cd frontend && npm test -- chapter-reader reading-column use-key-shortcuts` |
| Phone dock / capture | unit | sheet below lg; pointerup opens capture; Highlight primary; 44px; no H-scroll at 200% | `frontend/tests/reader-panel.test.tsx` `capture-popover.test.tsx` `chapter-reader.test.tsx` | `cd frontend && npm test -- reader-panel capture-popover chapter-reader` |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| backend unit (no DB) | Yes | in-process fakes | `tests/fakes.py` |
| backend DB-gated | No across workers sharing `learny_test` | one pytest process per gate | `conftest.py` LEARNY_TEST_DATABASE_URL |
| frontend vitest | Yes within one `npm test` | jsdom per file | `frontend/tests/` |

`[P]` is not used across tasks that share the test DB in the same phase worker (single process, order-free is fine).

## Gate Check Commands

> `uv` may be off PATH: `backend/.venv/bin/python -m pytest` / `backend/.venv/bin/ruff`. Prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local` if needed. `jq` is not installed.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After a backend unit task | `cd /home/augusto/projects/learny/backend && uv run pytest <touched module>` |
| Full | After HTTP or frontend tasks | touched backend module and/or `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary | `cd /home/augusto/projects/learny && make lint` plus the cycle's backend + frontend suites (`make test-backend`, `make test-frontend`) |

---

## Execution Plan

Four phases, sequential. One Opus worker per phase (encoder caps, ownership 404, Streamdown harden, and layout/capture all fail quietly if under-specified). No Haiku-safe unit. Verifier after T15.

### Phase 1 — Ingest kernel

```
T1 → T2 → T3 → T4
```

### Phase 2 — Media GET

```
T5 → T6
```

### Phase 3 — Desktop reader

```
T7 → T8 → T9 → T10
```

### Phase 4 — Phone

```
T11 → T12 → T13 → T14 → T15
```

---

## Task Breakdown

### T1: ImageEncoderPort + Pillow adapter + caps

**What**: Add `ImageEncoderPort` / `EncodedRaster`, Pillow adapter, `LEARNY_MEDIA_MAX_EDGE_PX` (1600) and `LEARNY_MEDIA_MAX_BYTES` (1572864), core `pillow` dependency.
**Where**: `backend/app/domain/ports.py`, `backend/app/domain/entities.py`, `backend/app/infrastructure/ingestion/images.py`, `backend/app/core/config.py`, `backend/pyproject.toml` / lock
**Depends on**: None
**Reuses**: `get_settings()`; Fake pattern in `backend/tests/fakes.py`
**Requirement**: READ-03, READ-04, READ-13

**Tools**: Skill `uv` for lock; no new provider SDK

**Done when**:

- [x] SVG / undecodable / pixel-bomb → `None`
- [x] PNG/JPEG → WebP under both caps; identical input → identical sha256
- [x] PIL is not imported from `app/domain` or `app/application`
- [x] Gate: `uv run pytest tests/test_ingestion_images.py tests/test_config.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(ingestion): re-encode book rasters to capped webp`

---

### T2: ParsedBook.media from the EPUB parser

**What**: `ParsedMedia` on `ParsedBook`; ebooklib adapter fills it from packaged image items (href + bytes + content type).
**Where**: `backend/app/domain/entities.py`, `backend/app/infrastructure/ingestion/epub.py`
**Depends on**: T1
**Reuses**: `EbooklibEpubParser` spine loop — do not change document reading order
**Requirement**: READ-01, READ-11

**Done when**:

- [x] A fixture EPUB with one raster yields one `ParsedMedia` with non-empty `data`
- [x] Spine/document parse tests still pass
- [x] Gate: `uv run pytest tests/test_ingestion_epub_parser.py tests/test_domain_entities.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(ingestion): collect packaged EPUB image bytes`

---

### T3: Rewrite derived markdown image srcs

**What**: Pure `rewrite_markdown_images` mapping original hrefs to `/api/sources/{id}/media/{sha256}`.
**Where**: `backend/app/application/media.py`
**Depends on**: T2
**Reuses**: None (keep out of `markup.py` so html_fragment stays untouched)
**Requirement**: READ-01, READ-10, READ-15

**Done when**:

- [x] Mapped href becomes the allowlisted path; unmapped href unchanged
- [x] Function never receives/returns HTML fragments
- [x] Gate: `uv run pytest tests/test_application_media.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(corpus): point figure markdown at same-origin media`

---

### T4: BuildCorpus encodes, stores, rewrites; one image cannot fail the job

**What**: Wire encoder + `put_object` + markdown rewrite into `BuildCorpus`. Empty-alt rasters omitted. Non-empty alt on dropped assets kept as emphasis. `html_fragment` / `content_hash` unchanged.
**Where**: `backend/app/application/corpus.py`, worker composition root that already builds `BuildCorpus`
**Depends on**: T3
**Reuses**: `StoragePort.put_object`; key `sources/{user_id}/{source_id}/media/{sha256}.webp`
**Requirement**: READ-01, READ-02, READ-04, READ-10, READ-12, READ-13, READ-15

**Done when**:

- [x] Test ingest puts the webp key and markdown URL
- [x] Injected encoder `None` for one of two images still completes the job with one figure
- [x] Block hash of an img html_fragment equals the pre-rewrite parse
- [x] Gate: `uv run pytest tests/test_application_corpus.py tests/test_ingestion_markup.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(corpus): store figure bytes beside the canonical markdown`

---

### T5: Owner GET media 200 / everyone else 404

**What**: `GET /api/sources/{source_id}/media/{sha256}` — cookie auth, owner 200 `image/webp`, non-owner/missing/malformed hash 404 never 403. No CSRF (safe method). No new rate limit.
**Where**: `backend/app/application/sources.py` (or `media.py` use case), `backend/app/infrastructure/web/sources.py`
**Depends on**: T4
**Reuses**: `_authorize` 404 collapse
**Requirement**: READ-05, READ-06

**Done when**:

- [x] Owner GET returns stored bytes and `Content-Type: image/webp`
- [x] Other user, missing key, and non-hex hash are 404
- [x] Gate: `uv run pytest tests/test_web_sources.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(sources): serve owned figure bytes at a media URL`

---

### T6: Pin media settings in `.env.example`

**What**: Document `LEARNY_MEDIA_MAX_EDGE_PX` and `LEARNY_MEDIA_MAX_BYTES` next to other ingest knobs.
**Where**: `backend/.env.example` (and prod example if ingest knobs live there)
**Depends on**: T1
**Reuses**: existing env-example sections
**Requirement**: READ-03

**Done when**:

- [ ] Names and defaults match settings
- [ ] Gate: `uv run pytest tests/test_config.py` (already covering defaults)

**Tests**: unit
**Gate**: quick
**Commit**: `docs: document figure encode caps`

---

### T7: Chapter Streamdown allowlist; answers unchanged

**What**: Chapter renderer allowlists `/api/sources/` with `defaultOrigin` and `allowDataImages: false`. `MessageResponse` used by Ask/Teach is untouched.
**Where**: new `frontend/app/components/chapter-markdown.tsx` (or equivalent), `chapter-reader.tsx` swap from `MessageResponse`
**Depends on**: T5
**Reuses**: Streamdown; do not edit `message.tsx` harden
**Requirement**: READ-07, READ-08, READ-11, READ-14

**Done when**:

- [ ] Rewritten markdown renders `<img src="/api/sources/...">`
- [ ] `https://evil.example/x.png` and `data:image/png;base64,...` do not become fetched imgs
- [ ] Existing cited-answer harden test still passes without allowlist leak
- [ ] Gate: `cd frontend && npm test -- chapter-reader chapter-markdown cited-answer`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): allow same-origin book figures`

---

### T8: paintHighlights skips img

**What**: Tree walker rejects `IMG` so highlights never wrap figures.
**Where**: `frontend/app/lib/highlight-paint.ts`
**Depends on**: T7
**Reuses**: existing scaffold `FILTER_REJECT`
**Requirement**: READ-09

**Done when**:

- [ ] A section with an img and a matching quote wraps only text nodes
- [ ] Gate: `cd frontend && npm test -- highlight-paint`

**Tests**: unit
**Gate**: quick
**Commit**: `fix(reader): do not paint highlights onto figures`

---

### T9: `/read` leaves the app shell

**What**: Move the read page into `app/(read)/` so `AppSidebar` and `AuthHeader` are not in the document. Fill the viewport without the 3rem header offset. Other `(app)` routes unchanged.
**Where**: `frontend/app/(read)/sources/[id]/read/page.tsx` (delete `(app)` copy)
**Depends on**: T7
**Reuses**: `ChapterReader`
**Requirement**: READ-16, READ-20, READ-21

**Done when**:

- [ ] `/read` render has no sidebar/header; a library route still has both
- [ ] Gate: `cd frontend && npm test -- app-shell` plus the read-page test

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): hide the app chrome on the read route`

---

### T10: `[` / `]` toggles; 65ch overlay dock

**What**: `[` toggles TOC (default closed). `]` toggles dock via `?panel=`. Below `xl`, open dock overlays and `.prose-reading` computed max-width stays `65ch`. Icon buttons on the thin bar. Receding chrome still applies.
**Where**: `frontend/app/components/chapter-reader.tsx`, `reader-panel.tsx`, `use-key-shortcuts.ts`
**Depends on**: T9
**Reuses**: `useKeyShortcuts`, `dockTabFromParam`
**Requirement**: READ-17, READ-18, READ-19, READ-20

**Done when**:

- [ ] Key tests for `[` / `]` ; TOC starts closed; overlay + 65ch assertion below `xl`
- [ ] Gate: `cd frontend && npm test -- chapter-reader reading-column use-key-shortcuts`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): toggle TOC and dock without shrinking the measure`

---

### T11: Bottom-sheet dock below `lg`

**What**: Below `lg`, open dock is `Sheet` side `bottom`, not `w-[26rem]`. At `lg+` keep the side dock (overlay rules from T10 still apply below `xl`).
**Where**: `frontend/app/components/reader-panel.tsx`
**Depends on**: T10
**Reuses**: `frontend/components/ui/sheet.tsx`
**Requirement**: READ-22

**Done when**:

- [ ] Viewport `<lg` + open dock → sheet; `lg` → not a full-width bottom sheet covering the article
- [ ] Gate: `cd frontend && npm test -- reader-panel`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): sheet the dock on a phone column`

---

### T12: Pointer and touch capture

**What**: Selection release via `pointerup` and `selectionchange` opens capture, not `mouseup` alone.
**Where**: `frontend/app/components/chapter-reader.tsx`
**Depends on**: T11
**Reuses**: `deriveCaptureSelection`, `handleCapture`
**Requirement**: READ-23

**Done when**:

- [ ] A test that only fires `pointerup` (no mouse) opens the popover
- [ ] Gate: `cd frontend && npm test -- chapter-reader capture-popover`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): open capture from touch selection`

---

### T13: Compact Highlight-first capture below `lg`

**What**: Below `lg`, visible primary verb is Highlight; remaining verbs behind overflow.
**Where**: `frontend/app/components/capture-popover.tsx`
**Depends on**: T12
**Reuses**: existing `CaptureAction` set
**Requirement**: READ-24

**Done when**:

- [ ] Narrow viewport: Highlight visible; Explain/Ask/Note/Create card not all in the first row
- [ ] `lg+` keeps the five-verb bar (no silent removal)
- [ ] Gate: `cd frontend && npm test -- capture-popover`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): keep highlight first on a narrow selection bar`

---

### T14: 44px targets on new `/read` controls

**What**: TOC/dock toggles, sheet close, capture Highlight, overflow control meet 44×44px.
**Where**: thin reader bar, sheet, `capture-popover.tsx`
**Depends on**: T13
**Reuses**: existing button components if they already meet the size; pad if not
**Requirement**: READ-25

**Done when**:

- [ ] Tests assert min width/height 44px on those controls
- [ ] Gate: `cd frontend && npm test -- chapter-reader capture-popover reader-panel`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): size reading controls for a finger`

---

### T15: No horizontal scroll at 200% on a 320px column

**What**: Reading article does not overflow horizontally at 320px width with 200% zoom (or equivalent `zoom`/`transform` in jsdom — assert `scrollWidth <= clientWidth` on the article under the narrow layout).
**Where**: `.prose-reading` / `.book-column` padding; images `max-width: 100%`
**Depends on**: T7, T11
**Reuses**: `globals.css` `.prose-reading`
**Requirement**: READ-26

**Done when**:

- [ ] Assertion holds with a figure in the markdown
- [ ] Gate: `cd frontend && npm test -- reading-column chapter-reader` then phase-boundary `make lint` + backend/frontend cycle suites

**Tests**: unit
**Gate**: build
**Commit**: `feat(reader): keep the column from scrolling sideways`

---

## Parallel Execution Map

```
Phase 1 (sequential): T1 → T2 → T3 → T4
Phase 2 (sequential): T5 → T6
Phase 3 (sequential): T7 → T8 → T9 → T10
Phase 4 (sequential): T11 → T12 → T13 → T14 → T15
```

No `[P]` tasks — each task mutates overlapping reader/ingest files.

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1 encoder + settings + pillow | cohesive ingest kernel | ✅ |
| T2 parser media DTO | one adapter + DTO | ✅ |
| T3 pure rewrite | one function | ✅ |
| T4 BuildCorpus wire | one use case | ✅ |
| T5 media GET | one endpoint | ✅ |
| T6 env.example | docs | ✅ |
| T7 chapter Streamdown | one renderer | ✅ |
| T8 paint skip img | one walker change | ✅ |
| T9 route group | one page move | ✅ |
| T10 keys + overlay | one chrome slice | ✅ |
| T11 sheet dock | one breakpoint shell | ✅ |
| T12 pointer capture | one event path | ✅ |
| T13 compact verbs | one popover variant | ✅ |
| T14 44px | one a11y pin | ✅ |
| T15 overflow | one layout pin | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | Phase 1 start | ✅ |
| T2 | T1 | T1 → T2 | ✅ |
| T3 | T2 | T2 → T3 | ✅ |
| T4 | T3 | T3 → T4 | ✅ |
| T5 | T4 | Phase 2 after T4 | ✅ |
| T6 | T1 | listed after T5; depends T1 not T5 | ⚠️ sequential in phase 2 only for worker simplicity; no T5→T6 arrow required |
| T7 | T5 | Phase 3 after T5 | ✅ |
| T8 | T7 | T7 → T8 | ✅ |
| T9 | T7 | T7 → T9 (after T8 in worker order) | ✅ Match order-in-phase, T9 does not depend on T8 |
| T10 | T9 | T9 → T10 | ✅ |
| T11 | T10 | T10 → T11 | ✅ |
| T12 | T11 | T11 → T12 | ✅ |
| T13 | T12 | T12 → T13 | ✅ |
| T14 | T13 | T13 → T14 | ✅ |
| T15 | T7, T11 | after T11; also needs T7 which is already done | ✅ |

T6 depends on T1 only; it sits in Phase 2 so env docs land with the HTTP surface. T9 depends on T7 not T8. T15 depends on T7+T11.

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | encoder / settings | unit | unit | ✅ |
| T2 | EPUB parser | unit | unit | ✅ |
| T3 | markdown rewrite | unit | unit | ✅ |
| T4 | BuildCorpus | unit | unit | ✅ |
| T5 | media HTTP | integration | integration | ✅ |
| T6 | settings docs | unit (config already) | unit | ✅ |
| T7 | chapter Streamdown | unit | unit | ✅ |
| T8 | highlight paint | unit | unit | ✅ |
| T9 | `/read` shell | unit | unit | ✅ |
| T10 | shortcuts / measure | unit | unit | ✅ |
| T11 | phone dock | unit | unit | ✅ |
| T12 | capture events | unit | unit | ✅ |
| T13 | compact capture | unit | unit | ✅ |
| T14 | 44px | unit | unit | ✅ |
| T15 | overflow | unit | unit | ✅ |
