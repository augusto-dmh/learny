# RFC-005: Evidence-Gated Hardening with a Product Beachhead

- **Status**: Draft — work-in-window authorized (2026-07-24); formal acceptance pending the RFC-004 dogfood retrospective (~2026-08-04)
- **Date**: 2026-07-24
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Claude
- **Impact**: MEDIUM

## Background

Every roadmap cycle is shipped: the MVP (TDD-001 Phases 1–10), RFC-002 (v0.2.0), RFC-003 (v0.3.0), and RFC-004's six student-experience cycles. RFC-004 does not *close* yet — its success gate is the author studying daily in Learny for 14 consecutive days, a window that opened 2026-07-21 and whose retrospective (~2026-08-04) is what produces the UX-fatigue evidence the next product bet depends on. That retrospective is calendar-bound, not a build cycle.

So this RFC is written *into an open window*. The honest move is to spend it paying the ungated, high-consensus debt that has accumulated across four roadmaps — none of it on a surface the dogfooding author sees — while committing zero dogfood-*dependent* product direction until the evidence exists. Three debts stand out:

1. **The eval judge gate is stuck.** The eval-deepening cycle (PR #46) built the machinery to switch the judge to `claude-opus-4-8`, then had that switch **stripped at the merge gate** because Opus scores declined/not-found answers faithfulness `0.0` while Learny's convention treats a claim-free answer as vacuously faithful (`1.0`) — an unresolved semantics clash that would drag the nightly faithfulness mean below the `0.90` floor. The switch cannot be re-litigated until that convention is settled and baselines are re-derived under Opus. This is the highest-leverage deferred debt on the board; nearly every framing in the planning panel converged on it.
2. **The offline suite is not honest.** Local `backend/.env` real-provider values leak into the deterministic suite (pydantic-settings loads `.env`, overriding the network-free `local` defaults), so roughly a dozen DB-gated tests that build the real adapter via `get_settings()` depend on `pytest` being prefixed with `LEARNY_GENERATION_PROVIDER=local` / `LEARNY_EMBEDDING_PROVIDER=local`. The MVP promised a network-free baseline; today it only holds by accident of how you invoke it.
3. **Workers idle silently.** Celery ingestion/corpus workers occasionally die or idle after a phase and need a manual nudge — a recurring pain that even hit the ship-cycle tooling. There is no liveness signal; a stalled phase hangs instead of surfacing.

A planning panel (six independent framings scored by three adversarial lenses — learning value, debt closure, risk/compliance — then synthesized) ranked a disciplined *evidence-gated hardening* shape highest on debt closure and lowest on risk, but flagged one unanimous weakness: it advances zero product differentiation, half of Learny's explicit north star (Learny is a learning project; a cycle's worth is how much durable capability and understanding it builds, which is exactly why multi-tenant hosting was rejected as the v3 flagship). This RFC takes that winning spine and cures the weakness by grafting **one** product capability that is genuinely safe to build mid-window.

## Locked decisions this RFC honors

This is a hardening-plus roadmap; it must not quietly reopen an accepted decision. Explicitly held:

1. **Providers frozen.** No new provider SDK. `claude-opus-4-8` and `claude-sonnet-5` are reached through the **existing Anthropic adapter** (ADR-0020); embeddings stay on OpenAI `text-embedding-3-large@1536` (ADR-0019), untouched. A judge-model or generation-model change is a model-id + threshold change behind the owned ports, nothing more.
2. **No orchestration framework.** Worker liveness uses Celery-native mechanisms only; PostgreSQL remains the source of truth for job/progress state (ADR-0005/0009/0014).
3. **Notes export stays one-way.** ADR-0026's export is a projection; this RFC proposes no import/round-trip and does not touch the notes domain.
4. **No new retrieval component.** The one product cycle reuses the shipped hybrid RRF retrieval and `reading_position` state (ADR-0006); it adds a *filter*, not an engine or a reranker.
5. **The dogfood gate is open and protected.** Cycles A–E touch only the test harness, backend eval, a read-only dashboard, and worker/DB ops — never a surface the dogfooding author studies during the window. The one reader-touching cycle (F) is **build-now, deploy-after-retrospective**. All dogfood-*gated* visual work — a contingent palette re-tune (RFC-004 flags it in its Assumptions table, triggered only if the gate exposes Source Serif 4 / Iron Gall fatigue) and the sensor-blind items (heatmap ramp hue, oxblood destructive color in situ, scrim strength, header-rule taste) — stays **out** and flows into a post-retrospective RFC-006 that the retrospective seeds.

## The roadmap in one paragraph

Make the ruler trustworthy, then read it: fix the offline suite so every later cycle's verification stands on network-free determinism (A); settle the decline-faithfulness convention as a recorded decision and re-derive the judge gate under Opus so the twice-deferred switch becomes a data-backed flip-or-stay (B); de-noise the single-observation generation verdict with a multi-run A/B scored by the settled judge (C); render the accumulating nightly eval history so the recalibrated gate is legible instead of a JSONL file nobody reads (D); give the workers a heartbeat and the backups a point-in-time floor so a stalled phase surfaces and the dogfood window's own study-log survives (E); and graft the single product capability that is safe to build now — position-scoped "spoiler-safe" retrieval — building it inside the window but holding its rollout until the study signal is banked (F). Every cycle reuses a shipped subsystem; this is a hardening roadmap with a product beachhead, not a platform expansion.

## Proposed roadmap

Ordering rationale: A is the foundation every later verification rests on, so it goes first. B precedes C so the generation de-noise is scored by the *settled* judge and never needs re-running (a sequencing error one panel framing made in the opposite order). D renders B/C's recalibrated thresholds, so it follows them. E is independent and **pullable forward** if worker pain bites during the window. F is the one reader-touching cycle: its build is dogfood-independent but its deploy waits, so it is sequenced last and its PR naturally lands near or after ~08-04. Sizes: S ≈ a few tasks, M ≈ a normal ship-cycle (the largest here).

### Cycle A — Offline-suite honesty (S) — *not dogfood-gated*

- Add a `conftest`-level provider pin so `backend/.env` real-provider values can no longer leak into the offline suite: the fixture forces the network-free `local` generation and embedding adapters regardless of ambient env, so the roughly-a-dozen env-dependent DB-gated tests pass with a bare `pytest` in local and CI.
- Deflake the pre-existing intermittent race in the `teach-panel.test.tsx` `TeachPanel resume` block (the `lists previous sessions … resumes full cited history` test, whose `Resume`-button click fires right after the `Previous sessions` render), applying the `findBy*` / await-gated patterns already used on sibling teach/reader/review deflakes.
- No product code touched — pure test-harness determinism.
- Depends on: nothing. Unblocks: trustworthy verification for every later cycle.

### Cycle B — Opus judge recalibration + the decline-faithfulness contract (M) — *not dogfood-gated*

- **First, settle the convention.** Resolve the decline-faithfulness clash the compliant way: exclude declined/empty answers from the faithfulness aggregate, letting the separately-measured not-found-discipline metric carry declines — rather than letting Opus's `0.0`-on-decline scores sink the nightly mean below the `0.90` floor. The precedent to mirror lives in the A/B *study* aggregate (`app.eval.ab._tier_aggregate`), where `mean_relevancy` already averages only answered lines while `mean_faithfulness` keeps declines as vacuous `1.0`; the nightly *gate* itself (`_assert_aggregates` in `app.eval.judge`) currently excludes declines for **neither** metric and only escapes the problem because the live tier is a single answered case — so ADR-0028 must add the faithfulness-decline exclusion to the gate, not assume it inherits the study aggregate's behavior. Record the semantics as **ADR-0028** (it changes a live gate convention).
- **Then re-seed baselines under Opus.** ≥3 live `claude-opus-4-8` judge runs over the committed replay snapshots; re-derive `FAITHFULNESS_MIN` / `RELEVANCY_MIN` with the calibration-runbook margins; commit the snapshots and the pinned threshold constants **together** so gate and baseline cannot drift.
- **Then flip-or-stay against the recalibrated thresholds** — and record the decision with its evidence. A data-backed "stay on `claude-haiku-4-5` with re-derived, documented thresholds" is an acceptable and complete outcome; the point is to make the choice decidable, not to force a flip (see Open Questions).
- Compliance: Opus via the existing Anthropic adapter (ADR-0020); no new SDK; embeddings untouched (ADR-0019).
- Depends on: Cycle A. Closes: the twice-deferred judge switch; the decline-faithfulness semantics.

### Cycle C — Generation-verdict de-noise (S–M) — *not dogfood-gated*

- Re-run the Sonnet-vs-Opus generation A/B over **≥3 seeded runs** across the golden + silver cases, scored by whatever judge Cycle B settled, aggregating **per-metric variance** so the verdict is no longer a single observation (today's STAY-on-Sonnet rests on a lone 0.005 silver-faithfulness gap).
- Hold the existing bar: move the default only if the de-noised result is strictly better on ≥2 of {faithfulness, relevancy, not-found-discipline} and worse on none; a tie is not better. Leave the generation model unchanged on ambiguity.
- Adopt budget-capped, resumable, checkpointed runs with a modeled cost estimate before each run — the concrete mitigation for the credit-exhaustion history (a prior full attempt died mid-judge).
- Depends on: Cycle B (the settled judge). Closes: the single-run generation verdict.

### Cycle D — Eval-results dashboard (S, compact & cuttable) — *not dogfood-gated*

- A read-only render of the accumulating nightly eval JSONL with the recalibrated Opus thresholds drawn as reference lines: per-run faithfulness / relevancy, citation-valid rate, gate pass/fail, and per-case drill-down.
- Closes the v2-era eval-legibility thread (JSONL accumulates today with nothing rendering it) and is the cheapest way to break the recurring "long backend-only streak delays end-to-end feedback" process lesson — it gives the RFC a visible deliverable that naturally consumes Cycle B/C's output.
- Legibility feature, not strict debt: the most naturally cuttable cycle if the RFC needs tightening (see Open Questions).
- Depends on: Cycle B (for the reference thresholds), Cycle C (for the confirmed generation default).

### Cycle E — Worker + recovery hardening (M) — *not dogfood-gated*

- **Worker liveness:** add the missing detection layer — Celery-native heartbeats / idle-timeout surfacing plus `task_reject_on_worker_lost` — so a stalled ingestion/corpus phase is detected and surfaced instead of hanging for a manual nudge. (The config in `app/worker/celery_app.py` already sets `acks_late`, `prefetch=1`, and soft/hard time-limits of 1500s/1800s; liveness/heartbeat and `task_reject_on_worker_lost` are the net-new pieces.) PostgreSQL stays source of truth for job/progress state (ADR-0014); no orchestration framework (ADR-0009).
- **Point-in-time recovery:** continuous WAL archiving to the offsite bucket on top of ADR-0024's nightly logical dump, with a CI-proven restore drill mirroring the existing one — framed as protecting the dogfood window's *own* evidence artifact (the `study_days` / streak log and accumulating notes) from mid-window loss.
- **pdf-worker slimming: re-probe and record only.** It is blocked upstream (a `torchvision` pin excludes the `+cpu` local torch build per ADR-0024); re-check whether the pin now admits `+cpu`, and if still blocked, record and stop. Not promised as a slim-image deliverable.
- Independent of the eval cycles; **pullable forward** if worker pain bites during the window. Depends on: nothing hard (Cycle A recommended first for suite cleanliness). Closes: the recurring worker-idle pain; the PITR follow-up.

### Cycle F — Position-scoped spoiler-safe retrieval (M) — *build now, deploy after the retrospective*

- Q&A, teaching, and citation retrieval that never surface content past the reader's `reading_position` — reusing the shipped hybrid RRF query and `reading_position` state via an anchor/position filter; **no new retrieval component** (ADR-0006). Anchor-filter semantics are settled up front against the shipped position model so the cycle does not force a mid-build ADR.
- Verified genuinely net-new: retrieval and teaching do **not** filter by reading position today. This is the one dogfood-independent product capability worth grafting onto an otherwise-hardening RFC, and it is competitively distinctive (unfinished-book spoiler safety).
- **BUILD is dogfood-independent; DEPLOY/rollout is HELD until after the ~2026-08-04 retrospective**, and the cycle is sequenced last, so its PR naturally lands near/after the window close. Merges deploy at author discretion so no rollout interrupts a live study day.
- Depends on: all prior cycles (sequencing), plus the shipped reader/position model. Closes: the RFC-004 "designed-for-but-deferred" spoiler-safe-retrieval thread.

## Sequencing against the dogfood gate

The window opened 2026-07-21; the retrospective is ~2026-08-04. Cycles A–E touch only the test harness, backend eval, a read-only dashboard, and worker/DB ops — **none is a surface the dogfooding author sees during the window** — so they run immediately and concurrently, protecting the study signal. Unlike the house accept-then-build pattern (RFC-004 was *Accepted* before its cycles shipped), Cycles A–E are authorized to begin now under Draft — they are ungated, high-consensus debt on surfaces the dogfooding author never sees; formal acceptance at ~2026-08-04 is a post-window confirmation that A–E stayed invisible plus the green light for F's deploy, not a precondition for starting A–E. F is the single reader-touching cycle: its build is dogfood-independent, but its **deploy is held** until after the retrospective, and it is sequenced last so its PR lands near/after the close. If the retrospective slips, A–F still complete — only F's rollout waits. All dogfood-*gated* visual items stay out entirely and seed RFC-006. This RFC targets **v0.5.0**; RFC-004 closes independently at its retrospective (v0.4.0).

## Open questions (recommended resolutions to confirm at cycle start)

| # | Question | Recommended resolution | Genuinely a user/operator call? |
|---|---|---|---|
| 1 | Decline-faithfulness direction for ADR-0028 | Exclude declines from the faithfulness aggregate (the A/B study aggregate already does this for relevancy; the nightly gate does it for neither, so ADR-0028 adds it to the gate). Not-found discipline carries declines as its own metric. Judge-independent and load-bearing for any future swap. | Confirm at Cycle B — it changes a live gate convention |
| 2 | Judge outcome expectation | Recalibration success = re-derived, documented thresholds **plus** a data-backed flip-or-stay decision; a documented "stay on Haiku" is complete. Do not pre-commit to a flip. | Name the acceptance criterion up front to avoid re-litigating the stripped switch |
| 3 | Live-eval budget ceiling for the window | Set a per-run dollar cap with checkpoint/resume before Cycle B/C run (a prior full attempt died on credit exhaustion). Suggest bounding the window's live-eval spend and estimating cost before each run. | **Yes — operator cost call**, set at Cycle B start |
| 4 | Eval dashboard (Cycle D) in or out | Keep as a compact cycle — cheapest way to render the recalibrated gate and break the backend-only streak. It is the most naturally cuttable rider if the RFC must tighten. | Optional trim |
| 5 | Auth hardening (password reset, email verification, rate limiting) | **Out** this window: largest net-new external dependency (needs a Learny-owned `EmailPort` + its own ADR), thinnest single-user payoff. Revisit when the public surface's abuse risk is urgent. | Confirm out |
| 6 | PITR depth in Cycle E | Full WAL/PITR with a CI-proven restore drill **now**, framed as protecting the dogfood window's own `study_days`/notes evidence — even though ADR-0024's nightly dumps exist and the RPO revisit-trigger hasn't formally fired. | Confirm depth |

## Assumptions

| Assumption | Confidence | Invalidated if |
|---|---|---|
| Excluding declines from the faithfulness aggregate restores an Opus-judge nightly mean above the `0.90` floor | High | Non-decline Opus scores are themselves lower than Haiku's — then re-derive the floor, don't force a flip (Cycle B outcome) |
| A `conftest` provider pin fully isolates the offline suite from `backend/.env` | High | Some adapters read provider env outside the settings object — widen the pin, still Cycle A |
| Celery-native heartbeats + time-limits detect the observed idle failure without an external supervisor | Medium | The idle mode is broker-side, not worker-side — then the fix is broker/visibility-timeout config, still within Cycle E |
| Position-scoped retrieval is a filter over shipped RRF, not a new ranking path | High | The position filter degrades recall enough to need re-ranking — reopen as an ADR amendment, not silently |
| Cycles A–E are invisible to the dogfooding author, so they cannot contaminate the study signal | High | A shared migration or dashboard route bleeds into a studied surface — hold that piece to F's deploy discipline |

## Operating cost envelope (delta over v3/v4)

| Item | Cost |
|---|---|
| New infrastructure | none (providers + retrieval frozen) |
| Live eval during Cycles B/C | ≥3 Opus judge re-seeds + a ≥3× generation A/B over golden+silver, checkpointed and budget-capped (Open Question 3) |
| WAL/PITR storage (Cycle E) | incremental object-storage for WAL segments on the existing offsite bucket |
| Provider usage during the dogfood window | existing keys, normal study volume; the invisible cycles add no user-facing calls |

## Out of scope (explicit)

A contingent reader palette re-tune (RFC-004 Assumptions table) and all sensor-blind "dogfood-eye" visuals (heatmap hue, oxblood-in-situ, scrim strength, header-rule taste) — **dogfood-gated, deferred to RFC-006**. Auth hardening, daily digest / notification rituals, marketing site, native mobile — RFC-004-scope deferrals unchanged. Second-brain deepening (paragraph-level note chunking, fuzzy re-anchoring, graph UI, notes-in-teaching default-on) — deferred beyond v3 pending real telemetry; its ADR-0026 upgrade trigger has not demonstrably fired at single-author scale. Vault import / round-trip sync — export stays one-way (ADR-0026); any reversal needs its own ADR. Ragas / broader retrieval-eval metrics — deferred (ADR-0016); a whole-RFC eval expansion was considered and rejected as re-mining the just-shipped PR #46 subsystem. FSRS optimizer and LLM card-critique passes — deferred (ADR-0021). Multi-provider/BYOK, dedicated vector DB or reranker, multi-tenant hosting — no decision recorded; out.

## Follow-up decision records to write when cycles start

- **ADR-0028** — decline-faithfulness aggregate semantics (Cycle B), the load-bearing convention change that unblocks any future judge swap. Write it *before* re-deriving baselines.
- ADR (only if the implementation deviates): the position-filter contract for spoiler-safe retrieval (Cycle F), if anchor-filter semantics depart from the shipped `reading_position` model.

## Outcome

_Draft. To be filled at acceptance — which waits on the RFC-004 dogfood retrospective (~2026-08-04), since that retrospective's findings seed the sibling RFC-006 and confirm that Cycles A–E stayed invisible to the study window._
