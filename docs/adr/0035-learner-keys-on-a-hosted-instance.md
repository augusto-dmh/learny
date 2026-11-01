# ADR-035: Learner Keys On A Hosted Instance

- **Date**: 2026-10-31
- **Status**: Accepted (2026-10-31, owner approval at the implementing cycle's dispatch; batch A's backend gates ride PR review)
- **Deciders**: Augusto, Claude
- **Tags**: security, ai-providers, privacy, hosted-operations, i18n
- **Supersedes**: [ADR-0033](0033-learner-provider-keys-bound-to-house-profiles.md) point 11 — "Hosted instances stay off until `byok-hosted-policy` ships" — whose operator rule this ADR replaces with a mechanism

## Context and Problem Statement

ADR-0033 shipped learner provider keys as a self-host feature and pointed 11
deferred the hosted case: on a hosted public instance the operator leaves the
key-encryption key unset until a policy exists. That rule is a sentence in an
ADR — nothing in the code can tell a hosted instance from a private VPS, so
the only enforcement was an operator remembering a paragraph. Meanwhile the
2026-09-30 research recorded the concrete gaps a hosted learner-key offer
must close: which providers may be offered at all, what a learner is told
about their key and their content before they paste it, what a single answer
costs and on whose key, and what stops one book being pumped through one key.

What must be decided: how a hosted instance is declared (the code cannot
infer it), which providers a hosted instance may accept keys for, what the
learner's own rails are when their own money pays, what the learner is told,
and what happens to the house spend rails when the learner pays.

## Decision Drivers

- The code cannot tell a public host from a private VPS (ADR-0033 point 11's
  own conclusion). A runtime heuristic would misclassify someone; a declared
  flag cannot.
- Provider terms differ and change on their own schedule: Anthropic permits
  keys billed to the key owner; OpenAI's Services Agreement forbids key
  transfer to or with a third party, and whether entrusting a key to a hosted
  third party engages that clause is untested; Google's Gemini API trains on
  unpaid-tier content (`docs/research/2026-09-30/byok-and-business-models.md`,
  Q3, Q6 — fetched 2026-09-30).
- User-supplied endpoints are the documented failure mode (Lobe Chat
  GHSA-p36r-qxgx-jq2v, Open WebUI CVE-2024-7959): a learner-supplied
  `base_url` is both an SSRF vector and a key-exfiltration channel. There is
  no version of a hosted offer that includes one.
- A learner whose own key serves a call is spending their own money. A cap
  meant to protect the operator's wallet must not stop them — but every rail
  that is a rate or abuse rail must.
- A hosted learner must be able to bound their own monthly spend, and no
  operator billing integration exists to enforce it for them (that is the
  `paid-hosted-tier` row's territory).
- The interface's i18n contract (ADR-0034): every learner-facing sentence —
  badges, disclosure, refusal copy — comes from the catalogs in every
  supported locale, never from a backend English `detail`.

## Considered Options

1. **A declared hosted state with a two-flag gate, the three-provider
   allow-list, and learner-owned rails.** ⭐ Chosen.
2. A runtime heuristic that classifies the deployment (hostname, TLS, public
   IP probe) — rejected: misclassifies private VPS deployments and public
   hosts alike, and ADR-0033 point 11 already concluded this.
3. Defer hosted keys until a billing/tier integration exists — rejected: the
   research's conversion arithmetic makes "free on the operator's wallet"
   untenable either way; learner keys close the spend gap now, and the tier
   integration remains its own row.

## Decision Outcome

Option 1, with these rules:

1. **The hosted declaration and the opt-in are two flags.**
   `LEARNY_HOSTED_INSTANCE` (bool, default false) declares the instance
   hosted; `LEARNY_HOSTED_BYOK_ENABLED` (bool, default false) is the opt-in
   that turns learner keys on after the security-review checklist
   (`docs/ops/hosted-byok-security-review.md`) is complete. The gate lives in
   `learner_key_access`, the one gate both the API and the worker resolve key
   access through: hosted and not opted in reads as feature-off everywhere —
   no credential row is read, the list answers `enabled: false`, every write
   answers 404. A self-host ignores the second flag entirely: availability
   stays KEK + bound profile, whatever it says.
2. **Three providers, canonical hosts, no learner endpoint.** A hosted (or
   any) instance offers keys for `anthropic`, `openai` or `gemini` and
   nothing else, and every profile binding a provider sends its keys to that
   provider's canonical HTTPS host or native kind — the registry fails
   startup naming any binding that would send them elsewhere. A key `PUT`
   body's other fields are ignored: no learner-supplied `base_url`, model or
   provider kind exists anywhere in the feature, and the adapter a turn
   builds is constructed from the bound profile's operator-declared host and
   nothing from the request.
3. **The house USD cap exempts a learner-keyed call; nothing else does.**
   `DailyBudget.assert_generation` skips only the daily-USD-cap comparison
   when the caller's own key covers the mode — their own money cannot be
   spent past a cap meant to protect the operator's wallet. The kill switch,
   the per-day `ask`/`teach_start` counters and the route rate limits run
   unchanged for every payer, and a mode the learner's key does not cover is
   governed by the full house assertion as ever. A learner-keyed call debits
   0 USD to the house ledger (ADR-0033 point 9, unchanged).
4. **The learner's own rails: a per-book ceiling and a soft monthly budget.**
   `ByokPolicy` asserts, pre-flight, before any provider call:
   `LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP` bounds the month-to-date
   adapter-reported prompt tokens per (learner, source, calendar month) of
   user-keyed calls — default 4,000,000, `0` disables — refusing with 429
   `byok_corpus_limit`; and the learner's own monthly budget, which they set
   or clear in Account, pauses their user-keyed generation at
   429 `byok_budget` when the month's estimated cost reaches it. Neither
   refusal falls over to a house key. Both ledgers are upsert-incremented
   from the call's actual reported usage — turns and card suggestions at
   record time, deck passes at the worker's settle beside the house 0-USD
   debit — and raising or clearing the budget serves the next request with
   no operator action. That is what makes the budget soft.
5. **The learner sees what each answer cost.** A turn whose adapter reported
   usage carries the token counts and — user-keyed only — its estimated cost
   in USD micros, priced by the same catalog resolution a house call uses
   (one price list, two views). The estimate rides the buffered response, the
   stream's terminal `data-answer-usage` part and the restored history; the
   Chat surface renders one usage line, cost labeled as on the learner's own
   key, in every supported locale. A house-served turn shows tokens and no
   cost: house spend is the operator's number, and pricing it would imply the
   learner was billed.
6. **The learner is told, before pasting, what happens to their content.**
   Each offered provider row carries a privacy badge from the catalogs,
   static per provider and dated here: Google Gemini's warns that content
   under an unpaid-tier key may be used to improve Google's products;
   Anthropic's and OpenAI's state that API content is not used to train
   their models. On an instance declaring `LEARNY_HOSTED_INSTANCE`, the keys
   section adds the hosted disclosure: the key is stored encrypted on this
   server — not the learner's computer — calls still run under the learner's
   own provider agreement, and no custom endpoint exists. A self-host keeps
   today's disclosure only.
7. **The copy lives in the catalogs; the codes carry the distinction.** The
   two new refusals carry a machine code beside the backend's English
   `detail` (`byok_budget`, `byok_corpus_limit`); the frontend maps the codes
   to catalog copy in every supported locale and never renders the `detail`.
   Badge and disclosure copy is static in the catalogs, sourced from the
   2026-09-30 terms research, and must never require a network call; this ADR
   is its date stamp.
8. **Go-live is a checklist, not a flag flip.** An operator who wants the
   hosted offer completes `docs/ops/hosted-byok-security-review.md`: KEK
   generation and backup, the flag declaration, the provider-terms review
   (including the unresolved OpenAI key-transfer question, which can end in
   "not offered"), the rate and ceiling defaults, and the explicit go/no-go
   line. The environment examples document both flags and the ceiling, and
   the production example replaces ADR-0033 point 11's "leave the KEK unset"
   instruction with this checklist-gated opt-in.

### Positive Consequences

- A hosted operator can offer learner keys with the policy enforced by the
  code instead of remembered from an ADR paragraph, and the declaration is
  honest: the disclosure keys off the same flag the gate reads.
- The operator's wallet is structurally protected: learner-keyed calls do not
  touch the house USD cap, deck passes stay pinned to the payer's credential
  row, and the relay/extraction vector is bounded per book per month.
- The hosted learner gets the same honesty a self-host learner had, plus the
  two facts specific to hosting: where their key lives, and what their
  provider may do with their content.

### Negative Consequences

- The checklist is still an operator step: an operator who flips
  `LEARNY_HOSTED_BYOK_ENABLED` without it has bypassed a documented gate, not
  a technical one. The two-flag split exists so the shortcut is at least
  visible in the environment.
- The OpenAI key-transfer question stays unresolved; a hosted instance that
  offers OpenAI keys does so on the operator's own review of the live terms.
- The badges are static copy with a recorded date; a provider changing its
  terms does not update them, and the checklist's provider-terms review is
  what re-verifies them.
- The ceiling and budget ledgers add one write per user-keyed call (upserted
  beside the existing daily-ledger debit), and the per-answer usage columns
  add four nullable columns to `conversation_turns`.

## References

- BYOK and business models (2026-09-30): `../research/2026-09-30/byok-and-business-models.md` — Q2 (base_url CVEs), Q3 (provider terms), Q6 (Gemini unpaid-tier training), Q7 C5–C9
- [ADR-0033: Learner-provided API keys, sealed at rest and bound to curated house profiles](0033-learner-provider-keys-bound-to-house-profiles.md) — the machinery this policy gates; point 11 superseded by this ADR
- Hosted BYOK security review checklist: `../ops/hosted-byok-security-review.md`
- [ADR-0034: UI internationalization](0034-ui-internationalization.md) — the catalog contract the badges, disclosure and refusal copy ride on
