# v3-notes-loop Context — Auto-Decided Gray Areas

Auto-decided per the ship-cycle autonomy contract (no user prompt except merge gate); each option set recorded here and as AD-143..AD-148 in `.specs/project/STATE.md`. ADR-0026 decisions 4–6 are binding and were not relitigated.

## AD-143 — Note scope for source-scoped Q&A

Q&A retrieval is hard-scoped to one `source_id`; notes are user-global and may be anchored to zero or many sources. Which notes are candidates?

- **All the user's notes (RECOMMENDED, chosen)** — why: the second-brain payoff is cross-book synthesis; most notes are un-anchored and would otherwise never surface; RRF relevance + smaller per-arm limits already suppress off-topic notes. Why not: a note about book B can be cited while reading book A, which may momentarily surprise; slightly larger candidate set.
- Only notes anchored to the queried source — why: tight topical guarantee, smallest candidate set. Why not: excludes every un-anchored note (the majority), gutting the feature; anchoring is a capture detail, not a topical signal.
- All notes with an anchored-to-this-source boost — why: middle ground. Why not: invents a tuning knob with no evaluation signal to set it; more query complexity for unproven benefit.

## AD-144 — When regenerate-and-match runs, and what it may do

- **Promoted-notes-only, async on save; update matched in place, flag unmatched, never create or delete items (RECOMMENDED, chosen)** — why: ADR d5's invariant is edit-stability; unpromoted notes have nothing to match; never-create keeps edits non-surprising (no cards appearing unbidden) and re-promotion is the explicit path to new cards; never-delete preserves review history. Why not: an edited note that grew won't generate new cards automatically; users must re-promote.
- Regenerate for every note on every save — why: no promotion bookkeeping. Why not: burns generation tokens on notes that feed nothing; creates cards nobody asked for.
- Synchronous regeneration in the save request — why: no async complexity. Why not: puts a M-scale LLM call in an interactive save path; violates the worker-not-handler constraint (CLAUDE.md).

## AD-145 — Note deletion vs note-derived items

- **Items survive; `note_id` SET NULL; provenance by join, absent once severed; item renders from its own stored text (RECOMMENDED, chosen)** — why: mirrors the inverse-cascade invariant already shipped twice (note_anchors→sources, quiz_items.note_anchor_id SET NULL) AND the AD-136 join-based provenance precedent (renamed note shows current title; severed shows none) — no snapshot-title column to drift. Why not: an item can outlive its source of truth with no title line; QC re-verification for severed items is impossible (acceptable: they're frozen).
- CASCADE delete items with the note — why: no orphans. Why not: destroys scheduled review state the user invested in; contradicts the domain's no-cascade precedent.

## AD-146 — Export delivery mechanism

- **Single `GET /api/export/vault` returning a zip, fixed zip timestamps (RECOMMENDED, chosen)** — why: exactly the shipped Anki-export seam (pure bytes builder in `infrastructure/export/`, service, file-download route); fixed timestamps + stable ordering make NL-19 byte-determinism testable. Why not: whole-vault in one response body; at author scale (hundreds of notes) this is megabytes, fine — a streaming/job-based export is the recorded upgrade if it ever isn't.
- Worker-generated export stored to S3 with a download link — why: scales to huge vaults. Why not: infrastructure for a problem author-scale doesn't have; slower to ship; another lifecycle to manage.

## AD-147 — "Include my notes" toggle transport

- **Per-request boolean `include_notes`; server defaults on for Q&A / off for teaching; client persists the preference locally (RECOMMENDED, chosen)** — why: smallest true-to-ADR change; server owns the differing defaults (flag absent → route default) so API consumers get ADR semantics for free. Why not: preference doesn't roam across browsers (acceptable single-user).
- Server-side user preference table — why: roams. Why not: a migration + CRUD + UI for one boolean; ADR asks for a toggle, not a settings subsystem.

## AD-148 — Note-derived item linkage & identity

- **Third origin value `'note'` + nullable `note_id` FK (SET NULL) + title/excerpt snapshot columns; identity = minted row id; `content_key` kept as rewritable fingerprint with NO uniqueness for note items (RECOMMENDED, chosen)** — why: follows the two-identity-modes precedent in `quiz_items` (deck=content-hash unique, highlight=anchor unique) and ADR d5's minted-ID mandate; SET NULL implements AD-145; snapshots make provenance deletion-proof. Why not: a third partial-unique regime adds schema complexity; `quiz_items` accretes note columns (acceptable: same table keeps the whole review pipeline — due queue, FSRS, export — working untouched).
- Reuse `note_anchor_id` to reach the note via an anchor — why: no new column. Why not: un-anchored notes (the majority) have no anchor; wrong join direction — the card derives from the note, not from a highlight.
- Separate `note_quiz_items` table — why: clean separation. Why not: forks the entire review pipeline (queue, scheduling, export, UI) for no behavioral difference.

## Escalation check

None of AD-143..148 changes product direction beyond the cycle, locks a new provider, or lacks a defensible recommendation — no user escalation required (ship-cycle Stage 1 rule).
