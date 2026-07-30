# v6-answer-experience — Decision Context

Auto-decided per the ship-cycle protocol (options weighed, recommended picked, recorded here + STATE.md). None met the escalation bar: no product-direction change beyond the cycle, no new provider dependency (RFC-006 excludes SDK changes and ADR-0019/0020 hold), and every decision had a defensible recommendation.

## D-1 — Generation config values (AD-219)

**Options:**
- **(a) Config knob for effort (`LEARNY_GENERATION_EFFORT`, default `medium`) + `max_tokens` default 4096 + `thinking adaptive/summarized` on both request paths — CHOSEN.** Why: no measured latency baseline exists in the repo (the RFC's "chosen against Cycle A measurements" has nothing captured to choose against), so a knob keeps the value tunable from live instrument data without a code change; `medium` is the documented Sonnet 5 sweet spot (≈ Sonnet 4.6 `high`) for evidence-grounded Q&A. Why not: the default is still a judgment call, not a measurement — mitigated by the knob + effort now visible in the per-call log.
- (b) Run a live latency measurement campaign first. Why: literal reading of the RFC. Why not: needs the prod stack + provider keys mid-cycle, produces one-off numbers the knob obsoletes, and RFC-005 owns eval/measurement maturity.
- (c) Hardcode `effort=medium` without a knob. Why: less config surface. Why not: re-tuning would need a deploy; contradicts the RFC's "deliberately chosen" intent.

`thinking={"type": "adaptive", "display": "summarized"}` goes on **both** stream and buffered calls (one request shape; buffered `_parse_message` already skips non-text blocks). SDK note: pass `thinking`/`output_config` as typed kwargs if `anthropic 0.116` accepts them, else via `extra_body` — never a version bump (RFC exclusion).

## D-2 — Reasoning is transient, mode-agnostic, provider-optional (AD-220)

**Options:**
- **(a) Reasoning streams live but is never persisted; applies to both Ask and Teach; local adapter emits none — CHOSEN.** Why: the persisted turn is the durable record of the *answer*; storing scratchpad text would need a schema change and replay semantics for content the UI collapses anyway; the dock is mode-agnostic (AD-208); the deterministic adapter's network-free contract is untouched. Why not: a restored conversation can't re-show reasoning — accepted, it's ephemeral by nature.
- (b) Persist reasoning on the turn. Why: full-fidelity restore. Why not: migration + storage for transient UI; RFC never asks for it.

## D-3 — Wire encoding + where the "searching" phase is emitted (AD-221)

**Options:**
- **(a) Native UI Message Stream v1 `reasoning-*` parts for thinking, plus a `data-phase` part emitted before retrieval; retrieval moves *inside* the stream generator while auth/ownership/validation guards stay eager — CHOSEN.** Why: the frontend already speaks this protocol via `@ai-sdk/react` (reasoning parts land in `message.parts` with no custom transport work); a pre-retrieval frame is impossible today because `PostConversationTurn.stream()` runs `_preflight` (including retrieval) before returning the iterator, so the split is: guards + history stay eager (HTTP status codes before first byte — the existing tests' contract), retrieval + generation move into the generator behind an immediate `searching` frame. Why not: retrieval errors change failure mode from HTTP 5xx to an in-stream `error` part — acceptable, the panel renders both identically (`errorMessageFor` maps them to the same wording), and it must be covered by a test.
- (b) Invent custom `data-reasoning` parts. Why: no reliance on AI-SDK reasoning semantics. Why not: reimplements what the protocol already carries; more frontend parsing.
- (c) Keep retrieval eager and fake the searching state client-side on submit. Why: no backend change. Why not: lies about the phase (shows "searching" during network wait too, and can't distinguish retrieval from generation start); RFC explicitly says "requires emitting a status event before eager retrieval".

New Learny-owned events (ADR-0007/0009 boundary intact): domain `AnswerReasoningDelta` in the `AnswerStreamEvent` union (adapter-emitted); application `StreamReasoningDelta` and `StreamPhase` in `TurnStreamEvent`; the SSE vocabulary stays only in `ui_message_stream.py`. **Trap:** `hold_back_deltas` buffers text deltas for sentinel detection — reasoning deltas must pass through immediately without touching the accumulated-text logic. **Trap:** the adapter's `_run_stream` filters `event.type == "text"` and silently drops thinking deltas today.

## D-4 — Inline citation marks are backend-inserted text markers (AD-222)

The Citations API returns block-level citation attachments; no positions survive `_parse_message`, and the `Citation` entity has no span. For marks *inline in the text* that survive persistence and restore identically (spec AC6), position must live in the answer text itself.

**Options:**
- **(a) Adapter inserts plain-text marker tokens (`[^n]`) into the answer text at citation attachment points, in both stream and buffered paths; numbering is first-occurrence order of the cited chunk — the same order `_parse_message` builds `cited_chunk_ids` — so marker *n* maps to `citations[n-1]` by construction. Frontend renders tokens as interactive marks; the answer-save-to-note path strips them — CHOSEN.** Why: stream, persisted turn, and restore are consistent for free (the marker is just text); no schema change; numbering can't drift from the citation list because both derive from the same first-occurrence walk. Why not: markers leak into model-visible history text and into saved notes — history is harmless (models tolerate it), notes strip on save; a grounding-dropped citation leaves a dangling marker — the frontend renders a markerless token as plain text (spec edge case).
- (b) Frontend-only marks appended per paragraph. Why: no backend change. Why not: not actually inline (finding 10 asks for marks at positions); guesswork placement.
- (c) Persist citation spans on the turn (schema change). Why: cleanest data model. Why not: migration + span bookkeeping for what a text token encodes for free; overkill for the cycle.

Streaming mechanics: the marker is emitted as its own text delta when the SDK surfaces a citation attachment (citation event or `citations_delta` on the raw stream — the worker verifies which the installed SDK exposes and may fall back to per-block insertion at `content_block_stop`); the buffered path inserts markers after each cited block in `_parse_message`'s walk. Marker token `[^n]` chosen for distinctiveness (footnote-shaped, vanishingly rare in book prose); the frontend intercepts it before/within Streamdown rendering (pre-process or footnote-component override — worker's latitude), and the sentinel path never carries markers (a sentinel reply has no citations).

## D-5 — In-flow passage panel replaces the overlay (feature-local)

Activating mark *n* (or chip *n* — the numbered chip row below the answer stays as the fallback and the citation inventory, spec AC4) expands **one** passage region beneath the answer message: snippet + section breadcrumb, clamped height, "Show in book" via the existing `onShowInBook` → `chapter-reader` anchor-scroll path, "Open note" preserved for note-origin citations. The full-height `Popover` in `citations.tsx` is deleted. One expansion region (not per-mark accordions) keeps the answer readable and matches "opens in flow beneath the answer".

## D-6 — Navigation pending pattern (AD-223)

**Options:**
- **(a) Two shared primitives: a link-pending indicator using Next's `useLinkStatus` (rendered inside `<Link>`), and a `useNavigateWithTransition` hook wrapping `router.push` in `startTransition` and exposing `isPending` for buttons — CHOSEN.** Why: App Router has no global router events; per-navigation pending state is the framework-native pattern; two primitives cover both navigation styles the app uses (`<Button asChild><Link/></Button>` and programmatic `router.push`). Indicator is animation-delayed (~100–150ms) so cached routes don't flash. Why not: pending feedback is per-control, not a global progress bar — accepted, it's what finding 2 describes ("Resume looks frozen").
- (b) Global top progress bar via a third-party package. Why: one indicator everywhere. Why not: new dependency for what the framework provides; App Router lacks the events such packages patch in via monkey-patching.

Applied surfaces (spec AC4 minimum): Home two-card actions, library entries, sidebar links, TOC entries; `margin-rail`/`citations` links may adopt the same primitive where trivial.

## D-7 — Execution plan (AD-224)

Four phases, one Opus worker each, fresh Opus Verifier; no Haiku-safe unit exists (every phase carries a correctness invariant or cross-cutting UI judgment):

- **A — Generation config + reasoning stream (backend):** knobs + validation, adapter request params, `AnswerReasoningDelta` end-to-end (adapter → hold-back passthrough → SSE reasoning parts), `data-phase` + retrieval moved inside the generator. Invariants: guards-before-first-byte, sentinel hold-back untouched, provider-stream close on disconnect, offline contract.
- **B — Inline citation markers (backend):** marker insertion in stream + buffered paths, numbering/first-occurrence parity, sentinel/no-citation cases. Depends on A only for merge hygiene (same files); runs after A.
- **C — Answer experience UI (frontend):** phase indicator, collapsible reasoning, inline marks + in-flow passage, overlay deletion, note-save marker strip, restore parity.
- **D — Navigation pending (frontend):** shared primitives + applied surfaces. Independent; runs last (smallest risk, easiest to cut if the window closes).

A→B→C ordering is a dependency chain (C consumes A+B wire shapes); D is independent. Gate scoping per ship-cycle: affected module per commit, full suite at phase boundary.
