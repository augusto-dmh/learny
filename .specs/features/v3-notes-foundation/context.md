# v3-notes-foundation — Decision Context

Auto-decided per ship-cycle rules under ADR-0026's binding blocks. Mirrored as AD-109..AD-114 in `.specs/project/STATE.md`.

## D-1 — Notebooks deferred (AD-109)
- **Defer the `notebooks` hierarchy out of E (CHOSEN)** — why: ADR-0026 marks it optional; tags + backlinks cover organization at author scale; keeps E's schema surface to the anchoring core, the cycle's real risk. Why not: folder-style organization waits; additive migration later (adjacency list design already researched, rq03).
- Ship it now — why: one more table while migrating anyway. Why not: zero table-stakes value (rq01), UI cost (tree CRUD) crowds out the anchor cascade's test budget.

## D-2 — Server-side anchor resolution at save (AD-110)
- **Client sends selection evidence (section anchor, exact quote, 32-char prefix/suffix, offsets in served markdown); server resolves block hash/ordinal/in-block offsets at save (CHOSEN)** — why: blocks live only server-side (survey §7 — no hashes/ordinals exposed today), so this needs zero read-API expansion, keeps the anchor payload's authority in one place, and the client stays a dumb evidence-collector. Why not: one extra lookup per capture (trivial).
- Expose blocks (hash/ordinal/offsets) through the section endpoint and resolve client-side — why: exact block binding at selection time. Why not: widens the read API for every reader load to serve a rare write, duplicates resolution logic in TS, and couples the client to block internals.

## D-3 — `corpus_blocks.content_hash` at build, nullable, no backfill (AD-111)
- **CHOSEN** — why: build path already walks every block (hash is one line with the existing normalize+sha256 idiom); existing corpora self-heal on next re-ingest; the reconcile cascade's quote tiers (2–3) fully cover NULL-hash blocks meanwhile, so nothing breaks. Why not: tier-1 O(1) rebinding unavailable for old corpora until re-ingest (accepted; author has few books).
- SQL backfill migration — why: immediate tier-1 coverage. Why not: needs html→normalized-text parity with Python in SQL (markup stripping in the DB — divergence risk for zero user-visible gain).

## D-4 — Links from wikilinks; tags explicit (AD-112)
- **CHOSEN**: `[[Title]]` parsed on save into `note_links` (case-insensitive title match, unresolved keeps text); tags set via API field, lowercase-normalized, chips UI. Why: matches rq03's derived-index model and rq07's export syntax; explicit tags avoid magic-parsing surprises in prose. Why not: no inline `#tag` capture (can add later without migration).

## D-5 — Highlight = note with an anchor (AD-113)
- **One concept (CHOSEN)**: capture creates a Note (body optional) + one NoteAnchor; notes hold 0..N anchors. Why: resolves the ADR's open cardinality question with the smallest model — no separate highlights table, no join complexity, "add a note to this highlight" is just editing the note body. Why not: a bare highlight shows as a note with empty body in lists (styled as a quote card — acceptable, arguably desirable).
- Separate highlights table — why: cleaner "annotation vs document" split. Why not: doubles the schema/reconcile/UI surface for a distinction users don't feel at this scale.

## D-6 — Status vocabulary reuse (AD-114)
- **active/stale/orphaned, relocation stays active (CHOSEN)** — mirrors the shipped quiz vocabulary exactly (survey §2: no "relocated" status; relocation rewrites anchor under active), so the reconcile step, tests, and UI badges rhyme with what exists. Why not: a distinct "relocated" state would surface moves to the user — deferred until someone asks.
