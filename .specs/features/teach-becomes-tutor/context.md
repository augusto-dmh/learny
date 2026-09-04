# teach-becomes-tutor Context

**Gathered:** 2026-09-04
**Spec:** `.specs/features/teach-becomes-tutor/spec.md`
**Status:** Ready for design

---

## Feature Boundary

RFC-0007 Cycle C / Bet 3: Teach becomes a tutor. Frozen playbook, tutor-opens with section-first retrieval, Ask+Teach merged into one Chat dock (Answer | Tutor), a passed unaided check offers exactly one FSRS card. Explicitly out: new models, BKT, forbidding answers, auto-inserting cards, decks-from-sessions, path-matched chunk pinning, LLM miss-classification.

---

## Implementation Decisions

### Chat dock (D-1 / AD-288)

- **Chosen:** One Chat tab. `?panel=ask` / `?panel=teach` / `?panel=chat` all open it. Aliases arm Answer vs Tutor. Strip: Chat | Notes | Review.
- **Rejected:** Keep two conversation tabs with a shared empty state (RFC says merge). Drop the aliases (would break RFC-004 Explain/Ask and `?panel=teach` deep links).
- **Why-recommend:** Conflict resolution 5 in the RFC. Discoverability from the tutor opening, not from a second tab.
- **Why-not:** Every Ask/Teach panel test and the tab map have to move in one cycle.

### Tutor-opens (D-2 / AD-289, AD-290)

- **Chosen:** Tutor Start = `POST /api/conversations` then stream `TUTOR_OPENING_MESSAGE` as teach turn 0. Retrieval query for that turn is `target_title` (else `target_anchor`). Answer stays lazy-create (CONV-10).
- **Rejected:** Keep lazy-create for Tutor (the tutor never speaks). A dedicated `open_tutor` flag on create that generates inside the create handler (would block HTTP on generation).
- **Why-recommend:** Matches rq03 move 2 and the Khanmigo lesson. Create stays fast; the existing stream path owns generation failure (AD-262).
- **Why-not:** Bounce-offs pay one generation; empty tutor rows appear in the list if the learner leaves during opening.

### Ladder (D-3 / AD-291..AD-294, AD-299)

- **Chosen:** Columns on `conversations`. Pure `TeachingPolicy` advances from the learner message (ordinary vs two frozen chip strings vs opening sentinel). Check after 3 ordinary turns or after assert. Close is 409 for any further turn. Tutor threads reject `mode=answer`.
- **Rejected:** JSON trailer from the model (Citations API mutually exclusive). Classifying "wrong gist" with a second LLM call. A new aggregate.
- **Why-recommend:** RFC must-be-true: state is application-owned. MathTutorBench: prompt-only pedagogy drifts inside the 6-turn history window.
- **Why-not:** A fluent restatement on turn 1 does not close until check is asked; that is deliberate (production of the unaided check, not grading).

### Grounding carve-out (D-4 / AD-295)

- **Chosen:** Teach mode: non-sentinel + blank citations → `answered`. Sentinel unchanged. Answer mode unchanged (AD-027).
- **Rejected:** Drop grounding for teach entirely (would persist invented book claims). Structured outputs on teach (400 with citations).
- **Why-recommend:** The playbook's Socratic turns are not book claims. Today's guard makes them `not_found_in_source`.
- **Why-not:** A model that neither cites nor sentinels on a book claim will persist. The frozen prompt still requires cites on claims; that is a prompt bug to catch in dogfood, not a second judge this cycle.

### Envelope (D-5 / AD-296)

- **Chosen:** Optional `tutor_phase` / `hint_level` on `GenerationPort.generate` and `generate_stream`. Anthropic adapter interpolates into the teach user text beside the existing section line. System prompt stays a constant.
- **Rejected:** Application-concatenated envelope inside `message` (adapters would double-wrap). New generation port.
- **Why-not:** Every fake and both adapters must accept the new kwargs (default `None`).

### Card (D-6 / AD-297, AD-298)

- **Chosen:** `AcceptTutorCard` from the closed conversation. `origin='tutor'`. Question template + `tutor_check_text`. Excerpt from opening citation or `target_title`. `conversation_id` nullable FK ON DELETE SET NULL. Partial unique on `conversation_id WHERE origin='tutor' AND conversation_id IS NOT NULL`. Reconcile: tutor origin keeps while the target anchor (or alias) exists, else orphans — no excerpt-stale path.
- **Rejected:** `suggest_cards` on the section (empty-deck trap; "exactly one" would still need a pick). New `note` wrapping the restatement (couples notes). Reuse `highlight` origin (lies about `note_anchor_id`).
- **Why-recommend:** The check *is* the card. Opt-in so a bad restatement never silently enters the due queue.

### Agent's Discretion

- Exact playbook wording inside `TEACHING_SYSTEM_PROMPT` as long as TUTOR-02's constraints are present and the constant stays byte-stable.
- Chip labels in the UI ("Just explain" / "I don't know") as long as they send the frozen message bytes.
- Chat empty-state layout as long as both modes are named and Tutor Start has a section picker defaulting to the on-screen chapter.

### Declined / Undiscussed Gray Areas → Assumptions

Ship-cycle auto-decided every gray area (see spec Assumptions table). None left unmarked.

---

## Specific References

- RFC-0007 Cycle C (`docs/rfc/0007-public-launch-roadmap.md`).
- rq03 teach-session blueprint (`docs/research/2026-09-03/rq03-ai-tutor-pedagogy.md`).
- ADR-0020 (byte-stable system prompt, Citations ⊕ structured outputs).
- ADR-0029 (unified conversations; dispatch on `mode`, never on target presence).
- AD-027 grounding (superseded for teach mode only by AD-295).
- AD-147 notes default off for teach.
- AD-262/263 failed turns persist; retry is a new turn.
- CONV-10 lazy-create (kept for Answer).
- `TEACHING_SYSTEM_PROMPT` at `backend/app/infrastructure/answering/prompts.py:36`.
- `_retrieve_evidence` query=message at `backend/app/application/conversations.py:736`.
- `AcceptCard` at `backend/app/application/cards.py:240` (highlight-only; do not overload it).

---

## Deferred Ideas

- Path-matched chunk pinning as document 0..k on opening retrieval.
- LLM miss-classifier / structured trailer once a citations-compatible channel exists.
- Raising `LEARNY_TUTOR_CHECK_AFTER_TURNS` toward rq03's 8–14 tutor-turn envelope after dogfood.
- `tutor` cards in the margin rail.
- Mixing Answer follow-ups onto a closed tutor thread.
