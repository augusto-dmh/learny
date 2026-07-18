# RQ02 — Sub-Section Highlight Anchoring

- **Date:** 2026-07-18 (research executed 2026-07-17)
- **Status:** Complete
- **Question:** How should Learny anchor user highlights below the section level so they survive re-ingestion — comparing char-offset ranges, quote-based anchoring (W3C Web Annotation `TextQuoteSelector`, URL text fragments), and block-id+offset hybrids — and how do Hypothesis, Readwise, and browser text-fragment implementations survive document re-processing?
- **Scope constraint:** The recommendation must compose with Learny's existing section anchors (`href[#fragment]` for EPUB, `pdf:{slug-path}/b{ordinal}-{sha256[:16]}` for PDF), `anchor_aliases`, content hashing, and the quiz-item snapshot/reconcile precedent (no corpus FK, `(source_id, content_key)` upsert, AD-078/QUIZ-16).

---

## 1. Learny's existing anchoring substrate (code facts)

Verified directly in the repo (2026-07-17):

- Sections carry a canonical `anchor` plus `anchor_aliases` for anchors that normalization merged away, "so no saved citation dangles" (`backend/app/domain/entities.py`, `ParsedSection`). Blocks carry `position`, `block_type`, raw `html_fragment`, and optional `page_span`; chunks carry `section_path` + `anchor` and never cross section boundaries.
- Quiz items deliberately have **no corpus FK**: they snapshot `section_path`, `anchor`, `source_excerpt`, and `chunk_hash` (SHA-256 of the chunk text) so a corpus replace cannot cascade-delete them (`QuizItem` docstring, AD-078).
- The reconcile precedent (`ReconcileQuizItems`, `backend/app/application/quiz.py`) runs after re-ingest and resolves each item by value, not by id:
  - anchor still present ∧ excerpt verbatim in that section → keep `active`;
  - anchor present ∧ excerpt gone → `stale`;
  - anchor now an alias of a merge survivor ∧ excerpt in the survivor → relocate to the survivor's canonical anchor (canonical always beats alias on collision);
  - anchor gone ∧ excerpt found verbatim elsewhere → relocate to that section;
  - otherwise → `stale`. Only `anchor`/`section_path`/`status` are ever rewritten.

Any highlight model that does not reuse this machinery would create a second, divergent survival story for the same re-ingest event.

## 2. The three anchoring model families

### 2.1 Char-offset ranges (`TextPositionSelector` family)

The W3C Web Annotation Data Model defines `TextPositionSelector` as a `start`/`end` character pair over the normalized text stream (position 0 before the first character; `start` inclusive, `end` exclusive). The spec itself flags the failure mode: it "does not require text to be copied from the Source document … but is **very brittle with regards to changes to the resource**" ([W3C Web Annotation Data Model, §Text Position Selector](https://www.w3.org/TR/annotation-model/), accessed 2026-07-17). Any insertion or deletion upstream of a highlight shifts every downstream offset, and a bare offset pair carries no evidence to detect that it now points at the wrong text.

### 2.2 Quote-based anchoring (`TextQuoteSelector`, URL text fragments)

`TextQuoteSelector` copies the selected text (`exact`) plus optional `prefix`/`suffix` context "to distinguish between multiple copies of the same sequence of characters", computed over normalized text (tags removed, entities resolved, logical order) ([W3C Web Annotation Data Model, §Text Quote Selector](https://www.w3.org/TR/annotation-model/), accessed 2026-07-17). The model explicitly permits multiple selectors on one target: "Multiple Selectors SHOULD select the same content … Consuming user agents MUST pick one of the described segments" — i.e., the standard anticipates position + quote redundancy rather than choosing one.

URL text fragments (`#:~:text=[prefix-,]start[,end][,-suffix]`) are the quote model with **exact matching only**: the algorithm returns the *first* match satisfying the context terms, matches only on word boundaries, and on failure "degrade[s] gracefully into an ordinary link" — silently, with no fuzzy recovery and no orphan signal ([WICG URL Fragment Text Directives draft](https://wicg.github.io/scroll-to-text-fragment/) and [repo](https://github.com/WICG/scroll-to-text-fragment), accessed 2026-07-17). This is the cautionary tale: quote-only + exact-only + silent failure means a reader never learns a highlight was lost.

### 2.3 Block-id + offset hybrids

Anchor to a stable sub-document unit (block/paragraph id), then offsets within it. This is what Learny's PDF block anchors (`b{ordinal}-{sha256[:16]}`) already are: identity = position + content hash. Offsets inside a content-hashed block are *provably* valid — if the hash matches, the text is byte-identical, so the offsets cannot have drifted. The weakness is the cliff: when the block's content changes at all, the id is gone and a pure hybrid has nothing to fall back on.

## 3. How real systems survive re-processing

### 3.1 Hypothesis: redundant selectors + a four-step fallback cascade

Hypothesis stores **three selectors per target** and tries them in order ([Fuzzy Anchoring, Hypothesis blog, 2013](https://web.hypothes.is/blog/fuzzy-anchoring/), accessed 2026-07-17):

1. `RangeSelector` (XPath pair + string offsets) — fastest, works when the DOM is unchanged;
2. `TextPositionSelector` (global char offsets over the extracted text) — survives structural/markup change when text content is stable;
3. context-first fuzzy match — fuzzy-search for the stored 32-char `prefix` near the expected position, then the `suffix`, then compare the span between them against `exact`;
4. selector-only fuzzy match — fuzzy search for `exact` alone.

Fuzzy steps use a modified google-diff-match-patch (Bitap matching, Myers diff). Every re-anchor is **verified against the stored quote** — position hits that don't match the quote are rejected and the cascade continues.

Orphan handling: when the cascade fails (e.g., the paragraph was deleted — "even the smartest algorithm isn't going to help"), the annotation becomes an **orphan: kept, never deleted**, surfaced in a dedicated Orphans tab (client 1.2.0+) and still reachable from the user's profile ([Showing Orphaned Annotations, Hypothesis blog](https://web.hypothes.is/blog/showing-orphaned-annotations/), accessed 2026-07-17). Hypothesis also maintains [anchoring-test-tools](https://github.com/hypothesis/anchoring-test-tools) to regression-test anchoring across document types — evidence that re-anchoring is an evergreen QA surface, not a solved one-off.

### 3.2 Browsers (text fragments): exact-or-nothing

Covered in §2.2: first exact match with word-boundary context, silent degradation on failure. No re-processing survival story at all — the model assumes the document may change and accepts loss.

### 3.3 Readwise Reader: avoid the problem by never re-processing

Reader "will never try to re-parse previously saved content, so the version in your Reader library will always reflect the way you originally read it, and your highlights and notes will never lose their context." The only refresh path is delete-and-resave, which "will also delete any highlights and notes associated with the document, in both Reader and Readwise" ([Readwise Reader docs, Parsing FAQ](https://docs.readwise.io/reader/docs/faqs/parsing), accessed 2026-07-17). Readwise's internal anchoring representation is not documented publicly (unverified beyond absence in [their docs](https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes)). The strategic lesson: freezing the parsed document sidesteps re-anchoring entirely — but Learny explicitly re-ingests (atomic corpus replace) to pick up parser and normalization improvements, so this escape hatch is unavailable. Learny's quiz layer already chose the opposite bet: snapshot + reconcile.

### 3.4 EPUB CFI (considered, not a family above)

EPUB Canonical Fragment Identifiers ([spec](https://idpf.org/epub/linking/cfi/)) address into the raw EPUB DOM by element step path. They are EPUB-only, address the *publisher's* markup rather than Learny's normalized corpus (which merges sections and re-derives Markdown), and have no meaning for PDF-derived blocks. Real-world adoption outside dedicated reading systems is limited (unverified). Not pursued further.

## 4. Options

| | A. Char-offsets only | B. Quote-only (text-fragment style) | C. Block-hash + offsets only | **D. Layered block-hash + offsets + quote (recommended)** |
|---|---|---|---|---|
| Exact re-highlight after unchanged re-ingest | Yes, if nothing shifted | Yes (search cost) | Yes, O(1), hash-verified | Yes, O(1), hash-verified |
| Survives markup/structure change, text stable | No (offsets shift) | Yes | Yes (block hash is over normalized text) | Yes |
| Survives text edits near highlight | No | Only with fuzzy engine | No — hard cliff | Yes (quote + context fallback; fuzzy optional later) |
| Detects that re-anchor is wrong | No evidence stored | Self-verifying | Hash verifies block, not span semantics | Self-verifying at every tier |
| Orphan signal | Silent corruption | Silent miss (text-fragment precedent) | Immediate orphan on any block change | Explicit status after cascade exhausts |
| Fit with Learny anchors/aliases/quiz precedent | Poor | Partial (no block reuse) | Good but incomplete | Direct reuse of anchor→alias resolution + reconcile shape |

### Option A — Section-scoped char-offset ranges only

- **Why recommend:** Trivial to implement and O(1) to render; smallest storage; exactly reproduces the user's selection when nothing changed.
- **Why not:** The W3C spec itself labels bare positions "very brittle"; any normalization tweak in a re-ingest silently shifts every highlight after the first changed character, with no stored evidence to even detect the corruption. Fails the "exact re-highlight after re-ingest" requirement except in the luckiest case.

### Option B — Quote-only anchoring (TextQuoteSelector / text-fragment style)

- **Why recommend:** Self-describing and self-verifying; survives arbitrary structural change; the snapshot doubles as display text for orphans; aligns with the quiz `source_excerpt` snapshot.
- **Why not:** Every render pays a text search; repeated phrases (common in textbooks: definitions, formulas) need careful prefix/suffix disambiguation; the browser text-fragment experience shows exact-only quote matching fails *silently* — and without a positional/block hint there is no cheap "unchanged document" fast path even though re-ingests usually leave most blocks byte-identical.

### Option C — Block-id (content hash) + offsets, no quote

- **Why recommend:** Exploits infrastructure Learny already has (PDF anchors already embed `sha256[:16]` of block content); O(1), provably-correct re-highlight whenever the block survives re-ingest unchanged, which is the overwhelmingly common case for books.
- **Why not:** A one-character fix inside the block orphans the highlight instantly with nothing to fall back on and nothing to display; cannot relocate a highlight whose paragraph moved to a merged section without re-implementing quote search anyway. Hypothesis's data point: position-style selectors alone are only step 1–2 of four for a reason.

### Option D — Layered selector: section anchor + block content-hash + in-block offsets + quote snapshot ★ RECOMMENDED

Store per highlight (value-based, **no corpus FK**, mirroring AD-078):

- `anchor` (section, canonical at save time) + `section_path` snapshot;
- `block_hash` = SHA-256 of the block's normalized text (align with `chunk_hash` precedent) + `block_ordinal` (position within section, disambiguates identical blocks);
- `start`/`end` char offsets within that block's normalized text (`TextPositionSelector` semantics: 0-based, end-exclusive);
- `exact` quote + 32-char `prefix`/`suffix` computed over section-normalized text (`TextQuoteSelector` semantics, Hypothesis's proven context width);
- `status` ∈ {`active`, `relocated`, `orphaned`} (naming TBD; quiz uses `active`/`stale`).

Post-re-ingest reconcile cascade (same job family as `ReconcileQuizItems`, same alias resolution, canonical-beats-alias):

1. **Exact:** resolve section by `anchor` (or via `anchor_aliases`); find block with matching `block_hash` (prefer same ordinal on collision) → offsets are valid by construction → re-highlight, done.
2. **Quote-in-section:** block hash gone → exact search for `prefix + exact + suffix` (then `exact` with word-boundary context, text-fragment style) in the resolved section's normalized text → recompute block + offsets, keep `active`.
3. **Quote-in-document:** section resolution failed or quote not in section → exact quote search across the source's sections (quiz-relocate precedent) → adopt the found section's canonical `anchor` + `section_path`, mark `relocated`/`active`.
4. **Fuzzy (deferred, optional):** Bitap/edit-distance matching à la diff-match-patch only if real-world re-ingests show text actually mutating (parser changes mostly reshuffle markup, and normalization happens before hashing, so exact-quote fallback should cover most drift). Deferring keeps step counts honest and avoids a dependency until evidence demands it.
5. **Orphan:** cascade exhausted → `orphaned`, **never deleted** (Hypothesis precedent); the stored `exact` quote still renders in an "orphaned highlights" view with the last-known `section_path`, and the user can manually re-attach or delete. Re-running reconcile after a later re-ingest may resurrect an orphan (status is always recomputed, as with quiz items).

- **Why recommend:** Each tier is exactly one of the proven industry mechanisms — Hypothesis's redundant-selector cascade shape, W3C's multiple-selectors-per-target model, text-fragment context matching — mapped onto identity Learny already maintains (section anchors, aliases, block content hashes, normalized text). The common case is O(1) and hash-verified; every fallback is verified against the quote so a wrong re-anchor is structurally impossible; orphans are explicit, displayable, and recoverable. It is the quiz snapshot/reconcile pattern extended one level down, so re-ingest keeps a single survival story.
- **Why not:** The most complex option: four stored fields beyond the quote, a reconcile cascade to test (needs golden fixtures per tier, matching the project's evaluation posture), and a status lifecycle in the UI. Block-ordinal collision handling and the exact normalization boundary (block-normalized vs. section-normalized text for offsets vs. quotes) must be pinned in the design doc or offsets and quotes can disagree. Storage is ~a few hundred bytes per highlight (quote + context), strictly more than A or C.

## 5. Answers to the specific sub-questions

- **Exact re-highlight after re-ingest:** tier 1 — block content hash match makes stored offsets provably valid; no search, no ambiguity. This is where D beats every quote-first system: Hypothesis must run its cascade per page load because it controls neither document nor diff; Learny controls both sides of the replace and can reconcile once, at ingest time, persisting the result (exactly as quiz reconcile does).
- **Fuzzy re-attach when text shifts:** tiers 2–3 give exact-quote-with-context relocation (survives block splits/merges/moves and section merges via aliases). True fuzzy (edit-distance) matching is deliberately deferred with a named upgrade path (diff-match-patch/Bitap, per Hypothesis) — add it only when orphan telemetry shows text mutation, not markup drift, is the real cause.
- **Orphan handling:** keep forever, explicit status, dedicated UI surface (Hypothesis Orphans-tab precedent), quote snapshot guarantees the highlight remains readable and exportable (Anki projection can include orphaned highlights' text), and reconcile re-runs can resurrect. Never the Readwise path (destroy on refresh) and never the text-fragment path (silent loss).

## 6. Sources

- W3C Web Annotation Data Model — https://www.w3.org/TR/annotation-model/ (accessed 2026-07-17)
- Hypothesis, "Fuzzy Anchoring" — https://web.hypothes.is/blog/fuzzy-anchoring/ (accessed 2026-07-17)
- Hypothesis, "Showing Orphaned Annotations" — https://web.hypothes.is/blog/showing-orphaned-annotations/ (accessed 2026-07-17)
- Hypothesis anchoring test tools — https://github.com/hypothesis/anchoring-test-tools (accessed 2026-07-17)
- WICG, URL Fragment Text Directives (scroll-to-text-fragment) — https://wicg.github.io/scroll-to-text-fragment/ and https://github.com/WICG/scroll-to-text-fragment (accessed 2026-07-17)
- Readwise Reader docs, Parsing FAQ — https://docs.readwise.io/reader/docs/faqs/parsing (accessed 2026-07-17)
- Readwise Reader docs, Highlights/Tags/Notes FAQ — https://docs.readwise.io/reader/docs/faqs/highlights-tags-notes (accessed 2026-07-17; anchoring internals not documented)
- EPUB Canonical Fragment Identifiers — https://idpf.org/epub/linking/cfi/ (not fetched this session; adoption claims marked unverified)
- Learny code: `backend/app/domain/entities.py` (`ParsedSection`, `ParsedBlock`, `QuizItem`), `backend/app/application/quiz.py` (`ReconcileQuizItems`), `backend/app/application/normalization.py` (read 2026-07-17)
