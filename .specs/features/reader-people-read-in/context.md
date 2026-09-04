# reader-people-read-in Context

**Gathered:** 2026-09-04
**Spec:** `.specs/features/reader-people-read-in/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-0007 Cycle B / Bet 2: safe figures (extract → MinIO → allowlisted `<img>`), immersive `/read` chrome (`[` / `]`, hide app shell, 65ch survives the dock), phone-usable column (bottom-sheet dock, touch capture). Explicitly out: native apps, pagination, multi-color highlights, intra-section resume.

---

## Implementation Decisions

### Image pipeline (D-1 / AD-274, AD-275, AD-282, AD-284)

- **Chosen:** `DocumentParserPort` grows a `media` list on `ParsedBook` (original href + bytes + declared type). `BuildCorpus` encodes via a new `ImageEncoderPort` (Pillow adapter), `put_object`s under `sources/{user}/{source}/media/{sha256}.webp`, and rewrites **derived markdown only**. `html_fragment` / `content_hash` stay the parse output.
- **Rejected:** Re-opening the EPUB with ebooklib inside application code (ADR-0009). Serving EPUB-relative URLs with a looser Streamdown `*`. Iframing spine HTML. Rasterizing SVG with cairosvg.
- **Why-recommend:** rq06's cycle text is this shape; note-anchor reconcile keys on block hashes.
- **Why-not:** Ingest gets heavier; Pillow joins the default worker image.

### Caps and drop rules (D-2)

- Always WebP. Long edge 1600px, 1.5 MiB encoded. SVG / undecodable / empty-alt rasters dropped (alt-as-emphasis if non-empty).
- One-image failure does not fail the job. Same bytes → same hash.

### Media GET (D-3 / AD-276)

- `GET /api/sources/{id}/media/{sha256}` cookie-auth, owner 200, everyone else 404 (including missing and malformed hash). No extra rate limit. `Content-Type: image/webp`. Catch-all Next proxy already relays bytes (`relayResponse`).

### Streamdown (D-4 / AD-277)

- Allowlist **only** on the chapter renderer: prefixes `/api/sources/`, `defaultOrigin` = app origin, `allowDataImages: false`.
- Ask/Teach `MessageResponse` stays as-is so generated answers cannot pull arbitrary images.

### `/read` chrome (D-5 / AD-278, AD-279)

- Move `sources/[id]/read` into `app/(read)/` so it does not inherit `(app)/layout.tsx`.
- `[` = TOC, `]` = dock. TOC default closed. Dock still `?panel=`. Overlay below `xl`. Thin bar keeps progress + `Aa` + icon toggles; receding chrome unchanged.

### Phone (D-6 / AD-280)

- Below `lg`: `Sheet` side bottom. Capture: `pointerup` + `selectionchange` in addition to `mouseup`. Highlight primary, other verbs overflow. 44px targets. No horizontal scroll at 200% / 320px.

### Agent's Discretion

- Encoder quality parameter (WebP ~80) as long as caps hold.
- Exact overflow control (menu vs `…` button) as long as Highlight is the visible primary below `lg`.
- Whether two identical rasters share one object (content-addressing implies yes).

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decided every gray area (see spec Assumptions table). None left unmarked.

---

## Specific References

- rq06 P0 1–3 and its three cycle-sized moves (`docs/research/2026-09-03/rq06-reading-experience.md`).
- RFC-0007 Cycle B (`docs/rfc/0007-public-launch-roadmap.md`).
- Foliate-js / Grimmory: do not iframe book HTML with script rights.
- Ownership collapse already at `backend/app/application/sources.py` (non-owner 404).
- Markup today: `markup.py` `_image` → `![alt](src)` with EPUB-relative `src`.
- Reader today: `MessageResponse`/`Streamdown`; capture `onMouseUp` only; dock `w-[26rem]`.

---

## Deferred Ideas

- Intra-section resume; typography pack; keyboard reading mode; image-area snapshot; media GC on source delete (Cycle F); vision/multimodal Ask (rq13, blocked on this extract but not this cycle).
- Splitting Bet 2 into three PRs — rejected: RFC sizes it as one cycle; the three P0s are independently testable stories inside one PR.
