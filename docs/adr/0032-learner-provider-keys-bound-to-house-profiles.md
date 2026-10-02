# ADR-032: Learner-Provided API Keys, Sealed At Rest And Bound To Curated House Profiles

- **Date**: 2026-10-02
- **Status**: Accepted (2026-10-02, owner approval at the implementing cycle's design gate; rides its merge gate)
- **Deciders**: Augusto, Claude
- **Tags**: security, ai-providers, generation, privacy, operations
- **Supersedes**: ADR-0020 amendment "End-User Choice Among House Profiles", point 7 (BYO API keys deferred until a paid tier)

## Context and Problem Statement

Every generation call in Learny runs on a key the operator owns: Ask and Tutor turns, the selection-Explain, card suggestions, note card refresh and quiz decks. The operator pays for all inference and caps each learner's day to stay solvent. A self-hoster with no house key gets only the deterministic extractive answers. ADR-0020's 2026-09 amendment let the learner choose among operator-curated house profiles (point 1). Its point 7 deferred bring-your-own keys to "a pricing-gated roadmap of their own", following the 2026-09-07 research verdict that BYOK was three or more cycles of crypto, key lifecycle, abuse and billing-fairness work whose value waited on a paid tier.

The 2026-09-30 research (`docs/research/2026-09-30/synthesis.md`, "BYOK should plug user keys into curated profiles"; `byok-and-business-models.md` Q1, Q3, Q7) reverses the sequencing argument. A free cohort that costs the operator inference does not survive at the 0.5-3 % free-to-paid conversion open-source SaaS reports. BYOK-first is how the surviving analogues avoided taking a feature away later (TypingMind, Raycast, Zed; Cursor's retreat drew backlash). With learners paying their own provider, the billing-fairness concern shrinks to cost display and a soft budget, and binding keys to curated profiles removes the raw-model-picker problem. The research therefore sizes BYOK as two cycles plus a security review. This cycle (`byok-secrets-and-chains`) is the first of the two. The second, `byok-hosted-policy`, adds the hosted allow-list, cost display, rate and spend policy, and the security review.

What must be decided: where a learner's key lives and how it is protected, which calls it may serve and which it may never serve, how the per-process adapter construction carries per-learner keys, how background workers obtain a key, and what happens to the house spend rails.

## Decision Drivers

- A key the learner pastes must never be readable from a database dump, a log, an error, an API response or a task queue.
- The key may only drive the operator's curated, eval-gated profiles. A user-chosen endpoint is the documented failure mode: Lobe Chat GHSA-p36r-qxgx-jq2v leaked the server's key through a user `base_url`, and Open WebUI CVE-2024-7959 was an SSRF through the same field.
- Provider terms. Anthropic permits customers to provision their own API keys for third-party tools "provided the resulting usage is billed to the key owner" and forbids collecting or intermediating Claude.ai credentials ([Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), fetched 2026-09-30). The OpenAI Services Agreement §3.3(g) forbids customers to "buy, sell, or transfer API keys from, to, or with a third party" ([OpenAI Services Agreement PDF](https://cdn.openai.com/osa/openai-services-agreement.pdf), document dated 2025-11-19, re-verified 2026-10-02). Whether a learner entrusting a key to someone else's hosted instance is such a transfer is untested. It is not an issue on a self-host, where the learner is the operator. The Gemini API terms carry no BYOK clause and train on unpaid-tier content ([Gemini API Terms](https://ai.google.dev/gemini-api/terms)).
- Learny's answer assembly, citation verification and deck batches run server-side and in Celery workers, so the key must be usable without a browser session.
- No new provider SDK (ADR-0019, ADR-0020) and no gateway in the composition root (ADR-0009, ADR-0020 amendment point 12).
- Self-host first. Most of the value lands on instances whose operator and learners are the same people.

## Considered Options

1. **Server-side envelope encryption, keys bound to curated profiles.** ⭐ This is the LibreChat `user_provided` / Google Cloud KMS pattern.
2. Browser-only key storage with direct browser-to-provider calls (TypingMind; Open WebUI "Direct Connections").
3. Pass-through: the browser holds the key and sends it per request, and the server never persists it (Cursor; Lobe Chat client-DB mode).
4. Keep deferring BYOK until a paid tier (ADR-0020 amendment point 7 as written).

## Decision Outcome

Option 1, with these rules:

1. **Sealed at rest.** Each key is encrypted with AES-256-GCM under a fresh 32-byte data key (DEK) and a random 96-bit nonce on every write. The DEK is wrapped with AES-256-GCM by a key-encryption key (KEK) that the operator supplies in `LEARNY_SECRETS_KEK` (base64 of 32 bytes). Both layers bind the associated data `learny/provider-credential/v1/<user_id>/<provider>`, so a sealed value cannot be moved to another learner's or another provider's row. A row (`user_provider_credentials`, one per learner and provider, cascading with the account) stores ciphertext, nonces, the wrapped DEK, the KEK id, a fingerprint and the last four characters. It never stores the plaintext or an unwrapped DEK. The library is `cryptography`, a crypto primitive and not a provider SDK.
2. **Rotation without re-encryption.** `LEARNY_SECRETS_KEK_PREVIOUS` lists retired KEKs that may still unwrap. `python -m app.cli.rotate_secrets_kek` re-wraps every DEK under the current KEK and leaves the ciphertext untouched. A row under a KEK nobody configured is reported, and generation treats it as absent.
3. **Off by default.** The feature is on only when a KEK is configured **and** at least one declared profile binds a provider. Without both, the account surface is absent and the write routes answer 404.
4. **Keys bind to curated profiles only.** A registry profile opts in with `user_key_provider` (`anthropic`, `openai` or `gemini`). The learner supplies the key and nothing else: no model, no `base_url`, no provider kind. A profile may be user-key-only (no house key), and such a profile never joins a house chain. Ask's citation guarantee and the eval gate stay attached to the profile, exactly as for house serving. Subscription or OAuth logins (Claude.ai, ChatGPT) are never accepted.
5. **What a key serves.** A learner's key serves their own Ask and Tutor turns and their selection-Explain through the profiles bound to its provider. Their Anthropic key also serves card suggestions, note card refresh and quiz decks, using the operator's `quiz_model`. This widens ADR-0020 amendment point 3 for learners with a key: the Explain and deck paths were house-routed as a house cost lever, which a learner-paid call no longer is. One learner's calls never use another learner's key.
6. **Routing.** User-keyed entries lead the learner's chain, and the router keeps every ADR-0020 fail-over rule among them. A failure never falls over from a learner's key to a house key: a broken learner key surfaces as the honest generation failure, and the operator never pays silently for it. A mode that no bound profile is eligible for is served by the house chain as before.
7. **Per-learner adapter cache.** Built adapters are cached per process in a bounded LRU with a TTL, keyed on `(provider, profile id, model, key fingerprint)`. The per-profile `lru_cache` serving the house chains is unchanged. The cache is reached only through a fingerprint read from a live row, so a replaced or deleted key is never served again.
8. **Workers get ids, never keys.** Celery payloads carry source, job, note and credential row ids. A worker decrypts at task start. A deck batch pins the credential row it was submitted under, and a poll whose pinned row is gone fails the deck terminally rather than collecting with another key.
9. **Spend rails.** A call served under a learner's key debits 0 USD to the house ledger, because the house did not pay. The kill switch, the pre-flight assertion, the per-call `ask`/`teach_start` counters and the user-keyed rate limits all apply unchanged. Embeddings stay operator-level (ADR-0019): no per-user embedding keys.
10. **Never leaked.** Key values are masked by shape in every log record (message, arguments, extras, exception text) under both the API and the worker logging configuration. The key routes never echo a submitted value, including in validation errors. A canary end-to-end test with a negative control proves the channels stay clean.
11. **Hosted instances stay off until `byok-hosted-policy` ships.** On a hosted public instance the operator leaves `LEARNY_SECRETS_KEK` unset (the production environment example says so) until that row lands. It brings the provider allow-list, per-answer cost display and soft budget, the BYOK spend-cap and rate policy, the Gemini unpaid-tier and provider-terms disclosure (including the OpenAI §3.3(g) question above), and a security review. Until then BYOK is a self-host feature. The code cannot tell a public host from a private VPS, so this is an operator rule recorded here, not a runtime guard.

### Positive Consequences

- A self-hoster with no house key gets Claude-grade cited answers on their own key, and a learner on a self-host stops costing the operator inference.
- The research's three blockers close: crypto at rest, per-learner adapter construction, and keys kept out of worker payloads.
- The curated-profile binding keeps every eval, grounding and citation rule in force: a learner chooses whose account pays, never what model runs.

### Negative Consequences

- The KEK becomes a secret the operator must back up. Losing it makes every stored key unrecoverable, and learners must re-enter them. Backups of the database alone do not expose keys, by design.
- A key that leaks from process memory (a core dump or debugger) is still a plaintext key. Envelope encryption protects data at rest, not a compromised running process.
- A learner with only an OpenAI or Gemini key still gets house-served decks and card suggestions, because no non-Anthropic quiz adapter exists.
- A stream already in flight when its key is deleted runs to completion. Deletion takes effect at the next request.

## Pros and Cons of the Options

### Server-side envelope encryption, bound to curated profiles ✅ Chosen

- Good, because it works for worker-driven deck batches and server-side citation assembly.
- Good, because per-secret DEKs make KEK rotation a re-wrap, and associated data binds each secret to its owner.
- Bad, because the server holds decryptable keys, and the operator's KEK custody is now load-bearing.

### Browser-only storage

- Good, because the key never reaches the server.
- Bad, because Learny's pipeline (retrieval, citation verification, Celery decks) runs server-side and cannot reach the provider from the browser. localStorage is also exposed to any XSS.

### Pass-through per request

- Good, because nothing is persisted.
- Bad, because background workers have no browser to receive the key from, so decks cannot use it. The browser still holds the key in script-reachable storage.

### Keep deferring until a paid tier

- Good, because there is no crypto or key-lifecycle surface to maintain.
- Bad, because the free cohort keeps costing the operator inference, and introducing BYOK later as a paid-tier downgrade repeats Cursor's retreat (research Q4, Q7).

## References

- BYOK research synthesis (2026-09-30): `../research/2026-09-30/synthesis.md`
- BYOK and business models (2026-09-30): `../research/2026-09-30/byok-and-business-models.md`
- Provider adapter architecture (2026-09-07), §3.3 Flavor B: `../research/2026-09-07/provider-adapter-architecture.md`
- [ADR-0020: Use Anthropic Claude for generation](0020-use-anthropic-claude-for-generation.md) and its amendments
- [ADR-0019: OpenAI embeddings with per-chunk model versioning](0019-use-openai-embeddings-with-per-chunk-model-versioning.md)
- [Google Cloud KMS: envelope encryption](https://docs.cloud.google.com/kms/docs/envelope-encryption)
