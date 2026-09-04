# reader-people-read-in Specification (RFC-0007 Cycle B / Bet 2)

## Problem Statement

Learny already has a study-reader skeleton (chapter flow, 65ch serif, `Aa`, receding chapter bar, five-verb capture, Ask/Teach dock). A 2026-09-03 walkthrough still cannot *finish a book here*: EPUB figures render as `[Image blocked: …]` because binaries are never extracted and Streamdown's harden allowlist is empty; `/read` sits inside the full app shell (sidebar + auth header) so the 65ch measure dies beside the 26rem dock; capture is `onMouseUp` only and the dock is a desktop column. Strangers upload, ask one question, and go back to Kindle for the remaining pages (rq06 P0 1–3).

## Goals

- [ ] Raster figures from an ingested book render as same-origin `<img>` in the chapter, never `[Image blocked]`, without iframing EPUB HTML or giving it script rights.
- [ ] `/read` is a long-form surface: product sidebar and auth header are gone; `[` / `]` toggle TOC and dock; the 65ch measure survives the dock.
- [ ] A phone viewport can read and highlight: bottom-sheet dock, touch capture, 44px targets, no horizontal scroll at 200% zoom.

## Out of Scope

| Feature | Reason |
|---|---|
| Native apps, PWA install | RFC-0007 Cycle B out; RFC-004 already excluded native |
| Pagination / page-flip | rq06: Readwise rejected it; vertical scroll stays |
| Multi-color highlights | Hypothesis/RFC-004: one wash + tags |
| Intra-section resume (word offset / CFI) | rq06 later cycle; position stays section-granular |
| Typography pack (Atkinson, measure stepper, `lang` on article) | rq06 P1, not this bet |
| Keyboard reading mode (`j`/`k`, paragraph focus, `G`) | rq06 later cycle; this cycle only `[` / `]` |
| Image-area snapshot / figure highlight as a verb | Needs figures first; Zotero crop is a follow-up |
| Media garbage-collection / MinIO prefix delete | Cycle F owns deletion; orphans bounded by source lifetime |
| Signed/public figure URLs, CDN, vision to Claude | Same-origin cookie GET only; rq13 vision is blocked on this extract but is not this cycle |
| Serving raw SVG | Script vehicle (rq06); drop, do not rasterize via extra deps |
| Changing Ask/Teach Streamdown harden | Chapter reader only; answers stay default-hardened |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Pipeline shape | Parser yields media bytes; `BuildCorpus` re-encodes, `put_object`s, rewrites **derived markdown only** | Matches rq06 cycle text + ADR-0002/0009/0013. HTML fragments stay byte-stable so `content_hash` / note-anchor reconcile does not churn | auto (AD-274, AD-282) |
| Raster format | Always re-encode to WebP; key `sources/{user_id}/{source_id}/media/{sha256}.webp` | One content-type; zip-bomb cap is one encoder path. Pillow becomes a **core** dep so the default EPUB worker can encode (AD-284) | auto |
| Caps | Long edge ≤ 1600px and encoded size ≤ 1_572_864 bytes (`LEARNY_MEDIA_MAX_EDGE_PX` / `LEARNY_MEDIA_MAX_BYTES`) | rq06 zip-bomb bound. One downscale pass then drop | auto (AD-275) |
| SVG / undecodable | Drop the asset. Non-empty `alt` remains as markdown emphasis. Empty alt → omit | Do not add cairosvg; do not serve XML-as-image | auto |
| Empty-alt rasters | Omit from markdown (collapsed decorative) | rq06 P0 1 | auto |
| Auth on GET | Cookie session; non-owner and missing both 404 | Existing ownership collapse (`sources.py` non-owner 404) | auto (AD-276) |
| Rate limit | None on media GET (same as chapter GET) | Read of already-owned bytes; upload limiter stays on POST source | auto |
| Streamdown | Chapter reader: `allowedImagePrefixes` includes `/api/sources/`, `defaultOrigin` = app origin, `allowDataImages: false`. Ask/Teach `MessageResponse` unchanged | Pin in Learny code (rq06 evidence gap). Do not loosen answer markdown | auto (AD-277) |
| `/read` shell | Move the read page into a `(read)` route group with no `AppSidebar` / `AuthHeader` | CSS-hiding leaves them in the a11y tree; pathname conditionals in `(app)/layout` are fragile | auto (AD-278) |
| `[` / `]` | `[` toggles TOC; `]` toggles dock (`?panel=`). TOC defaults **closed**. Dock still URL-driven | Readwise copy; long-form default. Discoverability via icon buttons on the thin reader bar | auto (AD-279) |
| Measure vs dock | Below `xl`, open dock **overlays**; it MUST NOT shrink `.prose-reading` below `65ch`. At `xl+` the dock may sit beside if 65ch still fits; rail already yields | rq06 P0 2 | auto |
| Phone dock | Below `lg`, dock is shadcn `Sheet` `side="bottom"`, not `w-[26rem]` | Existing `Sheet` is only used by the app sidebar today | auto (AD-280) |
| Touch capture | `pointerup` + `selectionchange` in addition to `mouseup`; compact bar = Highlight primary, other verbs overflow | RFC: "touch capture for highlights"; five verbs do not fit 320px | auto |
| Already-ingested books | Figures appear after **re-ingest**; no silent backfill | Corpus replace already exists; rewriting old markdown in place would desync hashes we are explicitly keeping stable | auto (AD-286) |
| PDF/Docling | Same rewrite when the parser already supplies picture bytes; no new Docling work if bytes are absent | RFC named EPUB; the markdown defect is format-agnostic | auto (AD-285) |
| One-image failure | Drop that image; ingest continues | A single corrupt figure must not fail a book | auto |
| StoragePort | Unchanged (`put_object` / `get_object` bytes). Content-Type on GET is `image/webp` from the `.webp` suffix | Avoid widening the port this cycle | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Safe figures ⭐ MVP

**User Story**: As a learner, I want diagrams and plates from my book to appear in the chapter so I can study illustrated text here instead of in Kindle.

**Why P1**: Walkthrough blocker; rq06 P0 1; largest “I cannot study here” defect.

**Acceptance Criteria**:

1. (READ-01) WHEN an EPUB containing a decodable raster (`img`/`figure` whose bytes are in the package) is ingested THEN each derived section markdown image SHALL use `![alt](/api/sources/{source_id}/media/{sha256})` and SHALL NOT keep the EPUB-relative `src`.
2. (READ-02) WHEN those bytes are stored THEN the object key SHALL be `sources/{user_id}/{source_id}/media/{sha256}.webp` via `StoragePort.put_object`.
3. (READ-03) WHEN a raster's long edge is greater than `LEARNY_MEDIA_MAX_EDGE_PX` (default 1600) OR the encoded payload would exceed `LEARNY_MEDIA_MAX_BYTES` (default 1572864) THEN the encoder SHALL downscale and re-encode until both caps hold, or SHALL drop the image if it cannot.
4. (READ-04) WHEN the asset is SVG or not a decodable raster THEN the system SHALL NOT `put_object` it and SHALL NOT emit an image URL; IF `alt` is non-empty THEN markdown SHALL keep that alt as emphasis text; IF `alt` is empty THEN the node SHALL be omitted.
5. (READ-05) WHEN `GET /api/sources/{source_id}/media/{sha256}` is issued by the source owner for a stored figure THEN the system SHALL return 200, `Content-Type: image/webp`, and the stored bytes.
6. (READ-06) WHEN that GET is issued by a different authenticated user, or the hash is missing or not 64 lowercase hex THEN the system SHALL return 404 (never 403).
7. (READ-07) WHEN the chapter reader renders rewritten figure markdown THEN the figure SHALL appear as an `<img>` whose `src` starts with `/api/sources/` and SHALL NOT render the harden blocked-image indicator.
8. (READ-08) WHEN chapter markdown still contains `http:`, `https:`, `data:`, or EPUB-relative image URLs THEN the chapter reader SHALL NOT fetch them (blocked indicator or omit). `allowDataImages` SHALL be false on the chapter renderer.
9. (READ-09) WHEN `paintHighlights` walks a section that contains an `<img>` THEN it SHALL NOT wrap the image (skip `img` the way it already skips `[data-reader-scaffold]`).
10. (READ-10) WHEN image extract rewrites markdown THEN `corpus_blocks.html_fragment` and its `content_hash` SHALL be unchanged versus a parse without extract.
11. (READ-11) The reader SHALL NOT iframe EPUB HTML and SHALL NOT grant book content `allow-scripts` or `allow-same-origin` sandbox rights.
12. (READ-12) WHEN a single image fails to decode or encode THEN ingestion SHALL continue and SHALL omit that image; the job SHALL NOT fail solely because of that image.
13. (READ-13) WHEN the same raster bytes are ingested twice THEN the object key (hash) SHALL be identical (idempotent `put_object`).
14. (READ-14) Ask/Teach `MessageResponse` Streamdown SHALL keep its pre-cycle harden behavior (no chapter image allowlist leaked onto generated answers).
15. (READ-15) IF a test reintroduces EPUB-relative `src` in derived markdown for a packaged raster THEN that test SHALL fail.

**Independent Test**: ingest a tiny EPUB with one PNG; assert markdown URL, MinIO key, owner GET 200 / stranger GET 404; render chapter and assert `<img>` not “Image blocked”; mutate html_fragment hash and show it still matches the un-rewritten fragment.

### P1: Immersive `/read` chrome ⭐ MVP

**User Story**: As a learner, I want the book column to feel like a book — not like the rest of the app — so I can read for an hour without the library chrome eating the measure.

**Why P1**: rq06 P0 2. Receding chapter bar already exists; product nav does not recede.

**Acceptance Criteria**:

16. (READ-16) WHEN the `/sources/{id}/read` route is shown THEN `AppSidebar` and `AuthHeader` SHALL be absent from the document (not merely `hidden`). Other `(app)` routes SHALL still render both.
17. (READ-17) WHEN the reader is focused and `[` is pressed (no modifier, not in an input) THEN the TOC SHALL toggle. WHEN `]` is pressed under the same rules THEN the dock SHALL toggle via the existing `?panel=` URL state.
18. (READ-18) WHEN `/read` loads with no `?panel=` THEN the TOC SHALL start closed. The dock SHALL stay closed unless `?panel=` names a tab.
19. (READ-19) WHEN the dock is open and the viewport is narrower than the `xl` breakpoint THEN the dock SHALL overlay the column; computed `max-width` of `.prose-reading` SHALL remain `65ch`.
20. (READ-20) A thin reader chrome (progress, `Aa`, TOC and dock icon buttons) SHALL remain; existing receding-chrome behavior SHALL still apply to that bar.
21. (READ-21) IF a test mounts `/read` inside `AppSidebar`/`AuthHeader` THEN that test SHALL fail.

**Independent Test**: render `/read` and assert sidebar/header queries are empty; press `[` / `]` ; at a width below `xl` with dock open, computed style of `.prose-reading` is still `65ch`.

### P1: Phone-usable column ⭐ MVP

**User Story**: As a learner on a phone, I want to read the column, highlight a sentence, and open Ask without a 26rem side dock covering the book.

**Why P1**: rq06 P0 3; RFC-0007 Cycle B. Native apps stay out.

**Acceptance Criteria**:

22. (READ-22) WHEN the viewport is below the `lg` breakpoint and the dock is open THEN the dock SHALL render as a bottom sheet (`Sheet` side bottom), not as a `w-[26rem]` side column.
23. (READ-23) WHEN the learner selects chapter text with a pointer or touch and releases THEN the capture control SHALL appear (not `mouseup`-only).
24. (READ-24) WHEN capture opens below `lg` THEN the primary action SHALL be Highlight and the remaining verbs SHALL sit behind an overflow control.
25. (READ-25) Interactive targets added or relocated by this cycle on `/read` (TOC/dock toggles, sheet close, capture Highlight, overflow) SHALL have a minimum CSS size of 44×44px.
26. (READ-26) WHEN the reading column is shown at 200% zoom on a 320px-wide layout THEN the article SHALL NOT require horizontal scrolling.

**Independent Test**: set viewport `<lg`, open dock, assert sheet; fire `pointerup` with a selection and assert capture; assert Highlight is the visible primary verb; assert no `scrollWidth > clientWidth` on the article at 200% zoom.

---

## Edge Cases

- WHEN the media hash in the URL is uppercase, too short, or contains non-hex THEN the system SHALL 404.
- WHEN `get_object` raises (missing blob after a rewritten URL) THEN GET SHALL 404; ingest SHALL have already succeeded.
- WHEN `alt` contains markdown metacharacters THEN it SHALL be treated as plain text in the rewritten `![alt](url)` (no nested markup injection).
- WHEN two images share bytes THEN they MAY share one object key (content-addressed); both markdown URLs MAY use the same hash.
- WHEN capture selection includes an image node THEN quote derivation SHALL keep using served markdown text (existing `deriveCaptureSelection`); it SHALL NOT require a new image-highlight verb.
- WHEN `prefers-reduced-motion` is set THEN receding chrome SHALL keep its existing reduced-motion behavior (do not add a new motion on the sheet that ignores the media query).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| READ-01 | P1: Safe figures | T3, T4 | Done |
| READ-02 | P1: Safe figures | T4 | Done |
| READ-03 | P1: Safe figures | T1, T6 | Done |
| READ-04 | P1: Safe figures | T1, T4 | Done |
| READ-05 | P1: Safe figures | T5 | Done |
| READ-06 | P1: Safe figures | T5 | Done |
| READ-07 | P1: Safe figures | T7 | Done |
| READ-08 | P1: Safe figures | T7 | Done |
| READ-09 | P1: Safe figures | T8 | Done |
| READ-10 | P1: Safe figures | T3, T4 | Done |
| READ-11 | P1: Safe figures | T2, T7 | Done |
| READ-12 | P1: Safe figures | T4 | Done |
| READ-13 | P1: Safe figures | T1, T4 | Done |
| READ-14 | P1: Safe figures | T7 | Done |
| READ-15 | P1: Safe figures | T3, T4 | Done |
| READ-16 | P1: Immersive chrome | T9 | Done |
| READ-17 | P1: Immersive chrome | T10 | In Tasks |
| READ-18 | P1: Immersive chrome | T10 | In Tasks |
| READ-19 | P1: Immersive chrome | T10 | In Tasks |
| READ-20 | P1: Immersive chrome | T9, T10 | In Tasks |
| READ-21 | P1: Immersive chrome | T9 | Done |
| READ-22 | P1: Phone column | T11 | In Tasks |
| READ-23 | P1: Phone column | T12 | In Tasks |
| READ-24 | P1: Phone column | T13 | In Tasks |
| READ-25 | P1: Phone column | T14 | In Tasks |
| READ-26 | P1: Phone column | T15 | In Tasks |

**ID format:** `READ-NN`

**Coverage:** 26 total, 26 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] A packaged PNG in a test EPUB becomes a same-origin `<img>` in the chapter after ingest, with owner GET 200 and stranger GET 404.
- [ ] `/read` has no app sidebar or auth header; `[` and `]` toggle TOC and dock; 65ch holds with the dock open below `xl`.
- [ ] Below `lg`, the dock is a bottom sheet and a touch/pointer selection opens Highlight-first capture.
- [ ] Zero iframe of book HTML; SVG never served; data: images not allowlisted on the chapter renderer.
