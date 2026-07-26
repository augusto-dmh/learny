# Context — v6-workspace-conversations

Auto-decisions taken under the ship-cycle autonomy contract (options formulated with
why-recommend and why-not; recommended option chosen; no escalation trigger met).
Mirrored as AD-203..AD-209 in `.specs/project/STATE.md`.

---

## D-1 — RFC-006 Cycle D is split; this cycle is the conversation axis

**Context.** RFC-006 §Cycle D pre-authorized a split "at spec time" with the seam
"dock + redirects" / "notes & review re-scoping". The opening survey found three of
Cycle D's headline deliverables already shipped:

- `/sources/[id]/ask` and `/sources/[id]/teach` are already `redirect()` tombstones
  into `/read?panel=ask|teach` (RFC-004 Cycle C, RA-04).
- The contents rail already exists as `TocPanel`, rendered beside the article and
  toggled by `tocOpen`.
- The per-source due-cards filter already exists end to end
  (`GET /api/reviews/due?source_id=`, `ReviewScreen({ sourceId })`).

So the residue is not "dock + redirects" vs "notes & review" but two independent axes.

**Options.**

- **One PR for all of Cycle D** *(rejected)*. Why it appeals: one review, one merge
  gate, the roadmap row closes as written. Why not: it couples a high-risk backend
  retirement (deleting two web modules, two application modules, a presenter, a
  repository method, three settings knobs, and two ~1000-line legacy test files) to
  additive notes/review work that shares no seam with it beyond one component file.
  Cycle C — comparable size — produced 25 review findings on one PR; doubling the
  diff degrades review quality exactly where the risk is concentrated.
- **Split along the RFC's literal seam** *(rejected)*. Why it appeals: it is the
  driver's recorded wording. Why not: the literal first half is now nearly empty —
  redirects and rail are shipped — so it would produce one trivial PR and one that
  still carries both the retirement and the notes work.
- **Split by axis: conversations now, notes & review next** *(chosen)*. Why: the two
  halves touch disjoint domains (conversations/generation ports vs notes/quiz
  repositories), disjoint endpoints, and disjoint tests; the only shared file is
  `reader-panel.tsx`, and the halves touch it sequentially, not concurrently. It also
  puts the whole deletion risk in one focused review. Why not: two pipeline runs
  instead of one, and the roadmap row must be split into two rows — accepted, since
  the RFC explicitly authorized a split and the cost is bookkeeping.

**Decision.** Split. This cycle = `v6-workspace-conversations`. Queued next =
`v6-workspace-notes` (dock Notes + Review tabs, `GET /api/notes?source_id=`, `/notes`
per-book filter, notes-provenance retirement of title-only creation, and the
save-to-note anchorless fallback). ROADMAP row D becomes two rows.

---

## D-2 — Legacy routes are deleted outright, with no deprecation window

**Options.** (a) Delete outright *(chosen)*. (b) Keep them returning 410 Gone for a
window. (c) Keep them wired but undocumented.

**Why (a).** RFC-006 Assumption 5 records that the author is the only user and that
nothing is owed beyond redirects for retired *frontend* routes — which already exist.
A 410 shim is still a compatibility surface to maintain, test, and eventually delete;
it converts a finished job into a deferred one. **Why not (a):** any bookmark or
script hitting the API directly breaks with 404 rather than an explanatory 410 —
accepted, because the only client is this repo's frontend, which moves in the same PR.

---

## D-3 — Mode is passed explicitly to the converged port; target-presence is not the discriminator

**Context.** ADR-0029 says the two ports "become one `GenerationPort` whose target
section path is optional and whose message parameter has one name, and both mode
branches go." The tempting reading is that a present target *means* teach.

**That reading is unsafe.** AD-194 sets the target trio as a snapshot of the *scope
head* at creation — so an **answer**-mode conversation scoped to a chapter can carry a
non-null target. Inferring mode from target-presence would silently route chapter-scoped
ask turns through the teaching prompt. This is a correctness trap, not a style choice.

**Options.** (a) Infer from target-presence *(rejected — silently wrong, see above)*.
(b) Pass `mode` explicitly alongside an optional target *(chosen)*. (c) Keep two ports
*(rejected — this is the requirement)*.

**Decision.** One `GenerationPort`; `mode` is an explicit parameter; `target_section_path`
is optional and carries the teach target when the mode is teach. What ADR-0029 removes
is the *port-selection* branch in the turn service and the union return type — not the
mode concept. A sensor must pin that a chapter-scoped answer conversation with a
non-null target snapshot still generates through the answer path.

---

## D-4 — Pagination is bounded `limit`/`offset`

**Options.** (a) `limit`/`offset` *(chosen)*. (b) Keyset/cursor on `(updated_at, id)`.
(c) No pagination.

**Why (a).** It matches the shipped convention on `GET /api/reviews/due`
(`limit: int = 20, ge=1, le=100`), and the `(updated_at DESC, id DESC)` index created
by migration 0017 makes the order *total*, so offset paging cannot skip or duplicate
rows under ties — the usual objection to offset paging does not apply here.
**Why not (a):** offset paging degrades on very large offsets and can shift under
concurrent writes. Accepted: single-user app, and a conversation list is bounded by
human authorship. (b) is strictly better at scale but adds cursor encoding for no
present benefit; revisit if the list ever grows past thousands.

---

## D-5 — `not_found_in_scope` becomes wire-visible and gets its own message

**Options.** (a) Keep collapsing scope→source *(rejected — the collapse presenter
exists only to freeze the legacy wire; keeping it defeats the retirement)*.
(b) Surface it with a distinct reader-facing message *(chosen)*.

**Why (b).** AD-196 recorded the three-value vocabulary as domain truth and the
collapse as a wire concession. A reader who scoped a conversation to one chapter and
got nothing needs to know the answer might exist elsewhere in the book — that is
actionable, where "not in this book" is misleading. **Why not (b):** one more UI
string and one more branch in the panel. Accepted; it is the point of the model.

---

## D-6 — Ask threads and teach sessions share one dock list

**Options.** (a) One list, mode-agnostic *(chosen)*. (b) Separate lists per tab.

**Why (a).** `list_for_user(source_id=…)` already returns both modes; the
`target_anchor IS NOT NULL` filter existed only to keep ask-created conversations out
of the *legacy* teach panel and dies with it (AD-195). One list is also the product
claim of ADR-0029: scope × mode is one space. **Why not (a):** a reader looking for a
teaching session scrolls past Q&A threads. Accepted — the list shows each
conversation's mode, and per-mode filtering is cheap to add later if it bites.

---

## D-7 — Retired-knob scaffolding is removed with the knobs

**Options.** (a) Delete the three fields only. (b) Delete the fields and the
`_RETIRED_KNOBS` / `_warn_about_retired_knobs` machinery if nothing remains for it to
warn about *(chosen)*.

**Why (b).** The warning loop was built in Cycle C specifically so deployed `.env`
files would keep validating across this removal; once the fields are gone it must keep
accepting those variable names (WSC-08 AC-4) but has no *field* left to warn about.
Whether the machinery is deleted or kept as an env-name allowlist is a design detail
resolved in `design.md` — the binding requirement is that startup must not fail for a
deployment that still sets them. **Why not (b):** if a future cycle retires another
knob it must rebuild the mechanism. Accepted — cheap to rebuild, and dead scaffolding
is precisely what this cycle exists to remove.

---

## D-8 — Execution shape

Four phases, one worker each, all Opus; fresh Opus Verifier.

- **A — port convergence** (domain protocol, both adapter families, composition root)
- **B — unified surface completion** (pagination, list/rename/delete service+web edges)
- **C — frontend re-point** (Ask/Teach panels onto `/api/conversations`, dock
  conversation management, scope-miss message, copy + explicit notes choice)
- **D — legacy retirement** (delete modules/knobs/repository method; re-anchor the
  wire-freeze coverage onto the unified surface)

No Haiku-safe unit: every phase carries either a correctness invariant (mode
discrimination, stream parity, rate-limit coverage, ordering) or a design decision.
Phase D is last because deleting the legacy tests is only safe once C proves the
panels no longer depend on the legacy wire.
