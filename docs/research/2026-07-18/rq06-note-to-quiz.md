# Learny research — RQ06: note-to-quiz mapping

Generated 2026-07-17 by a web-research agent. Sources/dates inline; verify load-bearing claims before implementation. All web sources accessed 2026-07-17.

---

# Feeding user notes into quiz generation: what changes, and the identity rule

## 0. Question and scope

Learny's quiz pipeline today generates free-recall/cloze items from the **book corpus**: candidates are grounded by verbatim quote-in-chunk checks, deduplicated by embedding cosine, persisted under a `(source_id, content_key)` upsert where `content_key = sha256(item_type ⟂ norm(question) ⟂ norm(answer))`, scheduled with FSRS, and reconciled against the corpus on re-ingest without ever touching `quiz_item_scheduling`/`review_log` (`backend/app/application/quiz.py`, `quiz_qc.py`). This report asks what breaks when the "source" is **user prose** (notes), how RemNote/Anki-family tools handle note-edit vs card-identity, and recommends the mapping + identity rule.

## 1. What actually changes when the source is user prose

Four things change, and they are not independent:

1. **The source is mutable and authored by the learner.** A book is replaced atomically and rarely; a note is edited continuously, in small increments, with no "ingest event" the user thinks of as a version boundary. Every mechanism Learny keys off content — `content_key`, `source_excerpt` containment, embedding dedup — was designed against a source that changes only at re-ingest.
2. **Groundedness changes meaning.** For book items, "the `anchor_quote` appears verbatim in the cited chunk" chains to a trustworthy canonical text. For note items the same check only proves *faithfulness to the note* — the note itself is the user's possibly-wrong belief. Groundedness stops implying correctness.
3. **Duplication becomes cross-source.** A note about chapter 3 and the book-derived deck for chapter 3 can produce near-identical items. Today's dedup (`_is_duplicate`, cosine ≥ threshold) only runs within one deck-generation pass.
4. **Provenance at review time forks.** "Cited from *Book*, §3.2" and "from your note, which cites §3.2" are different claims, and the note may have drifted since the item was generated.

## 2. Prior art: note-edit vs card-identity

The surveyed tools converge on one invariant: **card identity and scheduling are bound to a stable ID, never to card content; edits update content in place; resetting scheduling is always an explicit user action.**

### RemNote (notes *are* the card source)

- Editing a rem does **not** disrupt its schedule. RemNote staff (hannesfrank): "The schedule is linked to the rem id which is fixed when you created the rem." ([forum.remnote.io/t/.../1496](https://forum.remnote.io/t/does-editing-a-flashcard-disrupt-the-srs-spaced-repetition-schedule/1496), accessed 2026-07-17)
- Major content changes are handled by an **explicit, user-initiated reset**: "If you make major changes to the content of a card, the previous scheduling history may no longer give an accurate picture of how well you know the card." A reset appends a `Reset` entry to the card's scheduling history rather than deleting it. ([help.remnote.com — Resetting Flashcard Scheduling](https://help.remnote.com/en/articles/7230389-resetting-flashcard-scheduling), accessed 2026-07-17)
- Net: RemNote never guesses whether an edit was "major"; identity is the rem ID, drift detection is left to the user, and reset is auditable.

### Anki (note/card split)

- Notes and cards are separate objects; scheduling lives on cards. On text import, "If notes are updated in place, the existing scheduling information on all their cards will be preserved" — matching is by **GUID** when present, else by **first field within the note type**. ([docs.ankiweb.net/importing/text-files.html](https://docs.ankiweb.net/importing/text-files.html), accessed 2026-07-17)
- Duplicate detection is deliberately shallow: "Anki checks the first field for uniqueness … The uniqueness check is limited to the current note type." No semantic or cross-notetype dedup. ([docs.ankiweb.net/editing.html](https://docs.ankiweb.net/editing.html), accessed 2026-07-17)
- Net: Anki's identity rule is "stable key (GUID/first field) → update in place, keep scheduling"; content is free to change under a fixed identity.

### Markdown-notes-to-Anki bridges (the closest analog to Learny's problem)

These tools sync mutable prose files into a scheduler, which is exactly Learny's notes case:

- **Obsidian_to_Anki** writes a persistent ID back into the note (`<!--ID: 1566052191670-->`); re-running the sync updates the existing Anki note instead of creating a duplicate. ([Obsidian_to_Anki wiki — Updating existing notes](https://github.com/Pseudonium/Obsidian_to_Anki/wiki/Updating-existing-notes), accessed 2026-07-17)
- **yanki-obsidian** stores Anki's `noteId` in the Markdown frontmatter after first sync: "When you edit a local Obsidian note, Yanki makes every effort to update rather than recreate it in the Anki database so that review progress is preserved." Losing the ID is the failure mode: "If it goes missing, Yanki might consider the ID-less note in Anki to be an orphan … you will lose stats in Anki" — it then falls back to content matching as best-effort recovery. ([github.com/kitschpatrol/yanki-obsidian](https://github.com/kitschpatrol/yanki-obsidian), accessed 2026-07-17)
- **obsidian-spaced-repetition** takes the no-external-ID route: scheduling is an HTML comment (`<!--SR:!2021-08-20,13,290-->`) stored adjacent to the card text in the file. ([stephenmwangi.com — Reviewing](https://stephenmwangi.com/obsidian-spaced-repetition/flashcards/reviewing/), accessed 2026-07-17) The docs do not state what happens when card text is edited; because identity is positional adjacency of the comment, editing the card text while the comment stays adjacent preserves scheduling, and separating them breaks the card (see e.g. [issue #1182](https://github.com/st3v3nmw/obsidian-spaced-repetition/issues/1182), accessed 2026-07-17) (identity-by-adjacency characterization: inference from the storage format, unverified against an explicit spec statement).

Lesson: tools that use **content as identity** (first-field matching, positional adjacency) all document duplicate/orphan failure modes and grow ID mechanisms over time; tools that mint a **stable ID at creation** (RemNote rem ID, Anki GUID, Obsidian_to_Anki ID comment, yanki `noteId`) preserve scheduling through arbitrary edits by construction.

## 3. Where Learny's current machinery does and doesn't transfer

Verified against the code (2026-07-17):

- `content_key` is a **content hash** (`quiz_qc.content_key`) and the upsert identity `(source_id, content_key)`. This works for books because regeneration over an unchanged corpus reproduces byte-identical items; over an *edited note*, regeneration produces different question/answer text → a new `content_key` → a **new item with fresh FSRS state**, while the old item lingers pointing at prose that no longer exists. Content-hash identity collapses under a mutable source.
- Grounding (`_ground` + `quote_in_text`) is source-agnostic: "quote appears verbatim (normalized) in the cited block" works identically when the block is note prose. Only its *meaning* changes (§1.2).
- `ReconcileQuizItems` is precisely the right shape for note edits: excerpt-containment → keep `active`; anchor alive but excerpt gone → `stale`; excerpt found elsewhere → relocate; else `orphaned` — and it never touches scheduling. It just needs a trigger on note-save (debounced) instead of re-ingest, and it needs the *insert/update* half that re-ingest gets for free from deck regeneration.
- FSRS state (`quiz_item_scheduling`, `review_log`) has no content dependence — nothing in the scheduler requires a reset when item text changes; reset is purely a product decision, which prior art says must be explicit (§2).

## 4. Options

### 4.1 Identity rule for note-derived items (the core decision)

| | Option | Why recommend | Why not |
|---|---|---|---|
| **→** | **B. Stable block-ID identity + in-place content update** — notes get stable block IDs minted at block creation (the "rem ID"; e.g. anchor `note:{note_id}/blk-{uuid7}`, never content-derived); a quiz item carries `origin_block_anchor`; on note edit, regenerate candidates per changed block and match them to that block's existing items (reuse the cosine-dedup machinery); matched → update question/answer/`source_excerpt`/`content_key` **in place, same item id, scheduling untouched**; unmatched old → `stale`; unmatched new → insert. Never auto-reset; show a "note changed" badge with an explicit reset affordance. | This is the invariant every surveyed tool converged on (RemNote rem ID, Anki GUID update-in-place, Obsidian_to_Anki/yanki persisted IDs): scheduling rides a fixed ID, content moves under it, progress survives arbitrary edits. Reuses Learny's existing reconcile + dedup code paths; `content_key` survives as a per-source uniqueness fingerprint rather than the identity. Matches the FSRS reality that scheduling has no content dependence. | Requires notes to have stable block IDs from day one of the notes schema (retrofit is painful — yanki's orphan warning is what losing IDs looks like). The candidate↔item matching step can mis-pair when a block spawns several similar items; a bad match silently rewrites a card the user has history on (mitigation: high threshold, prefer `stale`+insert over doubtful update). |
| | A. Extend today's `(source_id, content_key)` content-hash identity to notes | Zero schema or pipeline change; identical code path for books and notes; correct whenever the note is never edited after generation. | Collapses on the first edit: new hash → new item + fresh scheduling, old item orphaned — the exact duplicate/lost-progress failure mode content-matched tools document (Anki first-field limits, yanki orphan recovery). Notes are *defined* by continuous editing; this fails the common case. |
| | C. Frozen items (Obsidian_to_Anki-style explicit sync) — items never change on note edit; user manually triggers "regenerate & review diff" per note | Maximal safety: no silent rewrite of reviewed cards, no matching heuristics; simple mental model; auditable. | High friction for a single-user self-hosted app whose pitch is automation; cards drift arbitrarily far from the live note between manual syncs; in practice users stop syncing (the failure Obsidian_to_Anki's auto-run-on-directory feature exists to paper over). Fine as a *mode*, wrong as the default. |
| | D. Auto-reset scheduling when an edit is "major" (semantic-distance threshold) | Honest scheduling: FSRS history genuinely mispredicts recall of substantially rewritten content (RemNote's stated rationale for reset existing at all). | No surveyed tool auto-resets — RemNote and Anki both make reset an explicit user action, because a threshold cannot know whether the *tested fact* changed or just its wording; silent destruction of review history is the worst failure available. Keep reset manual, per item or per note. |

### 4.2 Groundedness for user prose

| | Option | Why recommend | Why not |
|---|---|---|---|
| **→** | **B. Same verbatim gate, re-labeled + chained** — QC gate stays `quote_in_text(anchor_quote, note_block)`; provenance type records the item as note-grounded ("faithful to your note"), and when the note block itself cites a book anchor, store that as a secondary citation link (no verification against the book at generation) | Keeps the QC pipeline deterministic and source-agnostic (the code already is); honest about what is proven; preserves the citation chain note→book for display and future checks without blocking generation on fact-checking. | "Grounded" now means two different strengths in one system; a confidently wrong note yields confidently wrong cards that pass QC — the UI label has to carry that distinction. |
| | A. Verify note claims against the cited book passage before accepting an item | Catches note errors at generation; strongest groundedness story. | This is LLM fact-checking, not quote verification — probabilistic, expensive, and wrong to gate on (a note may legitimately paraphrase, disagree with, or go beyond the book). Also unavailable for notes that cite nothing. Defer; at most emit a non-blocking "note may conflict with source" warning later. |
| | C. No groundedness for note items (trust the note) | Simplest; the user wrote it. | Loses the anti-hallucination property entirely: the *LLM* can still invent content not in the note, which is exactly what the verbatim gate catches. The gate is cheap; keep it. |

### 4.3 Dedup vs book-derived items on the same passage

| | Option | Why recommend | Why not |
|---|---|---|---|
| **→** | **B. Cross-source dedup only when the note cites a book anchor** — at note-item generation, load embeddings of existing *active book items* whose anchor matches the note's cited anchor (plus its aliases) and run the existing cosine check; on hit, keep the book item and link the note item's block to it instead of inserting a twin | Bounded and cheap (anchor-scoped, not whole-library); uses the already-shipped `_is_duplicate` machinery; prefers the item with the stronger grounding chain; the citation link means "show related book card" is still possible at review. | Misses duplicates when the note doesn't cite the passage (common for quick notes); anchor scoping can miss a duplicate that cites a neighboring section. Accept the miss: some overlap is harmless extra practice. |
| | A. No cross-source dedup (separate decks, like Anki's per-notetype scoping) | Matches prior art — Anki explicitly scopes dup checks and survives fine; zero work; reviewing a concept twice from two phrasings is arguably beneficial (varied retrieval). | FSRS schedules the two twins independently, so the user meets near-identical cards in the same session with no explanation — reads as a bug in a generated system even if tolerable in a hand-made one. |
| | C. Global semantic dedup across the whole library per generation run | Catches everything, including uncited overlap. | O(all items) embedding comparisons per note save; threshold tuning across sources is fragile (same concept, different book wording); punishes the debounced-regeneration loop that Option 4.1-B needs to stay cheap. |

### 4.4 Provenance display at review time

| | Option | Why recommend | Why not |
|---|---|---|---|
| **→** | **B. Typed provenance + drift badge** — note items render "From your note *{title}*" with the snapshotted excerpt; if the block still contains the excerpt, offer "open note"; if reconcile marked it `stale`, show a "your note changed" badge with actions *update card* (accept regenerated text, keep scheduling) / *reset scheduling* / *retire*; chained book citation shown beneath when present | The snapshot model (already how book items work) keeps review self-contained offline; the badge surfaces exactly the drift the identity rule tolerates, and puts the RemNote-style reset where the user can see why it's offered. | More UI states than book items; needs reconcile to run promptly on note edits or badges lag reality. |
| | A. Always show the live note block (RemNote-style: the note is the card) | Zero drift by construction; simplest provenance story. | Breaks Learny's snapshot invariant (quiz items deliberately have no corpus/note FK); a deleted or heavily rewritten block leaves the card with no reviewable content mid-session; conflicts with the atomic-replace/orphan model already shipped. |

## 5. Recommendation (final)

**Recommended: 4.1-B + 4.2-B + 4.3-B + 4.4-B.** Treat a user note as a mutable source whose blocks carry **stable, creation-minted block IDs**, and make that block ID — not the content hash — the identity that note-derived quiz items hang off. Concretely: mint `note:{note_id}/blk-{uuid}` anchors when blocks are created; quiz items store this anchor plus a snapshotted excerpt exactly as book items do today; on debounced note-save, run the existing reconcile logic (excerpt containment → active/stale/relocated) plus a regeneration-and-match step per changed block that **updates matched items in place under their existing item id** — `content_key` demotes from identity to a per-source uniqueness fingerprint that is rewritten on update. FSRS scheduling and review logs are never touched by edits, and scheduling reset is only ever an explicit user action surfaced through a "your note changed" badge at review time — this is the invariant RemNote (schedule bound to rem ID), Anki (GUID/update-in-place preserves scheduling), and the Obsidian→Anki bridges (persisted IDs; orphaned stats when IDs are lost) all converged on independently. The groundedness gate stays the verbatim quote-in-block check but is *re-labeled*: it proves faithfulness to the note, not truth; when the note cites a book anchor, store the chained citation for display and scope cross-source dedup to that anchor using the existing cosine machinery, preferring the book-grounded item on collision.

**Why not the alternatives, in one line each:** extending content-hash identity to notes (4.1-A) loses scheduling on the first edit — the documented failure mode of every content-matched sync tool; frozen manual sync (4.1-C) trades Learny's automation pitch for drift; auto-reset on "major" edits (4.1-D) silently destroys review history no surveyed product destroys; verifying notes against the book at generation (4.2-A) turns a deterministic QC gate into probabilistic fact-checking; global semantic dedup (4.3-C) is unbounded work for marginal gain; live-note cards (4.4-A) break the shipped no-FK snapshot invariant.

## 6. Open issues

- **Match-step precision:** the candidate↔existing-item matching inside a block (cosine threshold) has no ground truth; a mis-match rewrites a reviewed card. Needs a golden fixture set (edited-note before/after pairs) before shipping, and a conservative bias to `stale`+insert on ambiguity.
- **Block-ID durability across note operations:** splits, merges, and copy-paste between notes need alias rules analogous to `anchor_aliases`/AD-085; unspecified here.
- **Edit debounce/versioning:** what counts as "one edit" for regeneration (per-save? idle-timer? explicit "sync cards" affordance as an escape hatch) is a product decision this report does not settle.
- **obsidian-spaced-repetition identity characterization** is inferred from its storage format, not from an explicit spec statement (marked unverified above); it is corroborating, not load-bearing.
- **When notes ship:** Learny has no notes feature yet; the block-ID requirement must be designed into the notes schema from the start — retrofitting IDs is the yanki orphan scenario.
