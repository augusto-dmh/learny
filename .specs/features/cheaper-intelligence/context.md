# Cheaper Intelligence — Context (auto-decisions)

Decisions made under the ship-cycle auto-decision rule (no user prompts outside the merge gate).
Each records the option set with why-recommend AND why-not, the choice, and the rationale.
Owner input that pre-empted a decision is marked. Full reasoning chains: `docs/research/2026-09-07/`.

## D-1 — Run shape: single cycle (AD-334)

- **Options:**
  - *One cycle* (rails + router + adapter + first economy profile): why-recommend — the row
    ships complete, the prerequisite order is respected inside one branch, no cross-cycle
    coordination; why-not — the largest Verifier surface of any recent cycle, and a taxonomy
    slip forces re-verification of everything above it.
  - *Split G1/G2* (G1: taxonomy+pinning+pricing+Haiku moves; G2: adapter+Gemini/GLM profiles):
    why-recommend — small per-cycle Verifier surface (research's own note); why-not — the owner
    explicitly said single cycle, and G1 alone ships no economy tier (the row's headline).
- **Choice:** one cycle. **Source:** owner invocation 2026-09-07 ("single cycle, ADR-0020
  amendment first"). Mitigation for the size risk: six disciplined phases, full suite at every
  phase boundary, Verifier after all tasks.

## D-2 — Amendment vehicle: amend ADR-0020 in place (AD-335)

- **Options:**
  - *Amend ADR-0020 in place*: why-recommend — the roadmap row's own language ("ADR-0020
    amendment first"); the amendment extends tiers without dethroning the primary, which is
    exactly an amendment; why-not — in-place edits weaken the immutable-record property of ADRs.
  - *New ADR-0031 superseding ADR-0020*: why-recommend — clean immutability; why-not — no
    superseding precedent exists in `docs/adr/`, and the original decision (Claude primary,
    port-shaped integration, grounding backstop) is *reaffirmed*, not replaced — superseding
    would misrepresent it.
- **Choice:** amendment section inside `docs/adr/0020-*.md`, status line noting the amendment
  date, all twelve decision inputs answered (research §4).

## D-3 — First economy host: Fireworks-US GLM-5.3-Flash, shipped inactive (AD-336, AD-343)

- **Options:**
  - *Fireworks-US-hosted GLM-5.3-Flash*: why-recommend — the price floor (~$0.22/$0.75 with the
    US surcharge); US-hosted open weights satisfies the RFC exclusion ("no CN first-party
    inference over user books; a US-hosted fallback only"); OpenAI-compatible so one adapter
    kind covers it; why-not — Chinese-origin weights are a perception liability for some
    tenants, and GLM forces thinking (no effort knob).
  - *Gemini 3.8 Flash*: why-recommend — the only non-Chinese sub-$1 tier, OpenAI-compat;
    why-not — intro price doubles 2027-01-01, free tier trains on content, EU tenants need the
    paid tier, no batch endpoint guarantee; strictly more vendor risk for the same adapter work.
  - *Adapter only, no concrete profile*: why-recommend — smallest surface; why-not — the RFC
    names the fallback adapter as a Cycle G deliverable and §4 Q2 says add the adapter *with*
    the first concrete profile, not speculatively.
- **Choice:** Fireworks-US GLM-5.3-Flash profile declared in config with price pair + key env
  name, **inactive** (Ask-ineligible per EVAL-03, non-default). Activation is the post-merge
  eval-gated promotion process. Gemini/DeepSeek/MiniMax become config-only adds later.

## D-4 — Error taxonomy shape: Learny exceptions translated inside adapters (AD-337)

- **Options:**
  - *Learny-owned exception types translated inside each adapter*: why-recommend — zero port
    change (the port's "operational failure raises" contract stands, ADR-0007 intact);
    translation is per-SDK and testable with stubbed transport; why-not — exceptions as API is
    easy to misuse (callers can swallow them); mitigated by the application service's existing
    catch-and-map.
  - *Typed result objects (no raises)*: why-recommend — exhaustive handling; why-not — rewrites
    the port contract every adapter and the eval harness satisfy today; the streaming contract
    (deltas + one authoritative completion) is raise-shaped.
  - *Third-party exception hierarchy*: why-recommend — free; why-not — a provider leak across
    the port, exactly what ADR-0007 forbids.
- **Choice:** `Timeout / RateLimited / ProviderUnavailable / RequestRejected` as Learny types,
    translated per adapter. Retryability (research §2.2): Timeout + ProviderUnavailable are
    retryable across providers; RateLimited gets one same-provider backoff retry then cross;
    RequestRejected never retries blindly across providers (request shapes differ).

## D-5 — Router shape: a routing adapter implementing GenerationPort (AD-338)

- **Options:**
  - *`RoutingGenerationAdapter` implementing `GenerationPort`, built at the factory from a
    settings-declared registry*: why-recommend — the ADR-0007 shape verbatim ("fallback routing
    under Learny's control"); application services never learn it exists; no framework
    (ADR-0009); why-not — one more adapter to keep contract-tested (mitigated: the eval harness
    and offline suite already exercise the port surface).
  - *Routing in the application service*: why-recommend — no new adapter; why-not — every
    call site grows provider awareness, and the quiz/worker/eval paths would each re-implement
    the policy.
  - *Routing framework (LiteLLM/OpenRouter/Portkey)*: why-recommend — fast; why-not — banned on
    the request path by RFC-0007 exclusions and ADR-0009; user-supplied endpoints would become
    an exfiltration surface (rq14 §2).
- **Choice:** routing adapter + registry. Streaming rule: fail-over only before the first delta
  (SSE contract has no rewind); after commit, errors surface as today.

## D-6 — Effort representation: per-mode values on the profile (AD-339)

- **Options:**
  - *Per-mode effort values on each profile (ask/teach may differ), fed to the adapter
    constructor*: why-recommend — "lands as profile values" (research §4 Q4); one adapter per
    profile still; rq15's "diet Ask to low, keep Teach medium" is pure config; why-not — the
    constructor signature grows a pair where today it takes one value.
  - *Mode-keyed profiles (sonnet-ask@low, sonnet-teach@medium as separate profiles)*:
    why-recommend — zero constructor change; why-not — doubles registry entries for the same
    vendor/model/key, and price/rail attribution would split one logical provider into two
    profiles for no spend reason.
  - *Effort as a port argument*: why-recommend — per-call flexibility; why-not — research §1.3
    and §4 Q4 are explicit: the port never grows an effort argument (weak adapters would all
    have to fake it).
- **Choice:** per-mode values on the profile. Shipped defaults preserve `medium` on both modes;
  the Ask→`low` flip is the operator's judge-gated post-merge act (RFC: "effort=low on Ask,
  judge-gated").

## D-7 — Selection-Explain cheap routing via an explicit origin marker (AD-340)

- **Options:**
  - *Explicit origin field on the ask request, sent by the capture-popover Explain path*:
    why-recommend — the backend cannot otherwise distinguish the verb (the quote text is user
    content, not a routing signal); mirrors the existing `origin=tutor` pattern from
    teach-becomes-tutor; why-not — a small frontend+backend contract change.
  - *Content sniffing ("Just explain this.")*: why-recommend — no contract change; why-not —
    brittle, spoofable by ordinary user phrasing, and TUTOR_JUST_EXPLAIN_MESSAGE already has a
    different meaning in the tutor ladder.
  - *Separate /explain endpoint*: why-recommend — cleanest routing signal; why-not — a new
    surface to auth/rate-limit/document for what is an ask turn with different routing; the
    panel/streaming plumbing would be duplicated.
- **Choice:** origin marker on the ask payload. COST-04 fallback on transport errors goes to the
  Ask primary (Haiku and Sonnet are both grounded, so fallback preserves the trust contract).

## D-8 — Suggest/accept metering: USD only, no new caps (AD-341)

- **Options:**
  - *Debit USD (profile-priced) on suggest/accept provider calls, no integer caps*: why-recommend
    — closes the Cycle-F-flagged unmetered gap; the USD cap + kill switch already bound runaway
    spend; DOOR-08 deliberately named only ask/teach caps; why-not — uncapped *call counts* on
    suggest paths (mitigated: existing user-keyed rate limits already throttle the surfaces that
    trigger them).
  - *Also add integer daily caps for suggest calls*: why-recommend — symmetry with DOOR-08;
    why-not — invents product policy the RFC never named; cap UX (429 semantics, frontend
    handling) is a cycle of its own.
  - *Leave unmetered*: why-recommend — zero work; why-not — the RFC's ledger bullet says tokens
    and USD, honestly; a "cheaper intelligence" cycle that can't see a cost line fails its own
    audit.
- **Choice:** USD-only debit via the existing ledger record path.

## D-9 — Legacy provider settings: kept as the default registry seed (AD-342)

- **Options:**
  - *Keep `generation_provider`/`generation_model`/`generation_effort`; they seed the default
    registry when no explicit registry is declared*: why-recommend — .env.example, compose,
    deploy docs, and every developer checkout keep working; offline/local default unchanged;
    why-not — two configuration dialects coexist (mitigated: registry-declared deployments are
    the documented path; the seed path equals today's behavior byte-for-byte).
  - *Delete the legacy settings*: why-recommend — one dialect; why-not — breaks every deploy
    surface and the offline defaults in the same PR that adds routing; an unnecessary blast
    radius.
- **Choice:** keep as seed. ROUTE-06 pins the equivalence; the registry is the single source of
  truth when declared.

## D-10 — Price resolution: the router stamps the serving profile on the result (AD-344)

- **Options:**
  - *Router stamps the serving profile id (and price pair) onto the result it returns*:
    why-recommend — unambiguous even when two profiles name the same model; the debit site does
    one lookup; `GeneratedAnswer.model` already rides back across the port, so this extends an
    existing pattern; why-not — the result DTO grows a field the port was never promised
    (mitigated: optional, default None, adapter-agnostic).
  - *Debit site resolves model → profile by re-reading settings*: why-recommend — no DTO
    change; why-not — ambiguous when two profiles share a model, and settings may have changed
    between call and debit (worker redelivery) — exactly the misprice PRICE-04 forbids.
- **Choice:** stamp on the result; model-based lookup remains only as the PRICE-04 fallback with
  a warning. Mechanic pinned in design.md.
