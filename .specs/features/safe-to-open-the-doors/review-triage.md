# safe-to-open-the-doors — Review Triage (PR #68)

Reviewer: fresh-context pr-review subagent. 15 inline comments (10 findings + 5 highlights), 2 PR-level scaffolding comments. Every finding checked against the code as it exists. Comments are deleted after triage; this file is the surviving record.

## Findings

| # | Source (inline id) | Location | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | 3945730180 (security) | `backend/app/infrastructure/email/log.py:21` | REAL | fix | Confirmed: `body=%s` logs the full message body and verify/reset bodies embed the raw single-use token; the log adapter is the production default while `LEARNY_SMTP_HOST` is unset (the prod example ships it commented). Puts a live reset capability into log sinks — contradicts the cycle's own no-token-in-logs intent. Fix: redact the body in the log adapter; assert the redaction in the adapter test. |
| 2 | 3945730230 (security) | `backend/app/infrastructure/email/smtp.py:32` | REAL | fix | Confirmed: plaintext, unauthenticated `smtplib.SMTP`; no settings knobs for TLS/credentials. Reset mail over an unauthenticated plaintext hop is readable/forgeable in transit and most real relays require both. Fix: `smtp_use_tls` (default true), `smtp_username`/`smtp_password` settings; `starttls` + `login` in the adapter; patched-client tests; document in the prod example. |
| 3 | 3945730277 (security) | `backend/app/core/config.py:77` + `.env.production.example` | REAL | fix | Confirmed: the default trusts all RFC1918 and the production example never narrows it, so in a hosted stack any private-range peer that can reach the API can rotate `X-Real-IP` and mint fresh auth budgets. Fix: give the production example (and the prod compose wiring it pins) a narrowed trusted-proxy list with guidance, plus a topology-level assertion. |
| 4 | 3945730316 (security) | `backend/app/application/identity.py:62` | REAL | fix | Confirmed: the media object key template `sources/{uid}/{sid}/media/{sha}.webp` is duplicated at `application/sources.py:173`, `application/corpus.py:253`, and rebuilt from a markdown regex in `DeleteAccount` — erasure completeness silently depends on three copies staying in sync. Fix: one shared media-key builder used by all three sites, plus an end-to-end test (seeded markdown + stored media object → delete account → object gone). |
| 5 | 3945740569 (tests) | `backend/tests/test_redis_rate_limit.py:26` | REAL | fix | Confirmed: no skip gate; without a local Redis the module errors instead of skipping, unlike the repo's existing env-gated skips. Fix: module-level `skipif` probe, keeping the no-server fail-closed test outside the gate. |
| 6 | 3945740598 (tests) | `backend/tests/test_application_email.py:108` | REAL | fix | Companion to #1: once the adapter suppresses the body, the test must pin it (`token not in record message`); today the test documents the leak without noticing it. |
| 7 | 3945743685 (architecture) | `backend/app/worker/tasks.py:676` | REAL | fix | Confirmed: `_record_deck_spend` commits in one transaction, `_finalize_deck` in another; a redelivery between them debits the learner's day twice. The recorded "fail-closed class" note covers over-charging direction, not double-charging one generation. Fix: idempotency marker on the quiz job row consumed by a conditional update so debit+finalize run once per outcome. |
| 8 | 3945743732 (architecture) | `backend/app/infrastructure/web/redis_rate_limit.py:57` | REAL | fix | Confirmed: `EXPIRE` only fires on `count == 1`; a process death between INCR and EXPIRE leaves a TTL-less key that answers 429 forever (unbounded lockout; only manual `DEL` clears). Fix: single atomic Lua script (INCR, EXPIRE on first, TTL check with self-heal) + a live-Redis test that seeds a TTL-less key and proves recovery. |
| 9 | 3945751360 (performance) | `backend/app/infrastructure/web/rate_limit.py:122` | REAL | won't-fix | True that the CIDR list is re-parsed per request, but the reviewer themselves rank it nice-to-have; caching it couples a second cache to the `get_settings` clear-discipline across dozens of fixtures — a stale-trust-list risk in tests traded for microseconds on a sync threadpool route. Revisit if profiling ever shows it. |
| 10 | 3945751378 (performance) | `backend/app/application/identity.py:492` | REAL | won't-fix | Real observation (deletion materializes section markdown to extract digests), but it is a rare, user-initiated, one-shot operation whose input is bounded by this PR's own 2-source/256 MiB quotas. SQL-side digest extraction is a later optimization, not a rail. |

## Highlights (no action)

- 3945730345 — security: hash-at-rest, purpose-bound, atomically consumed email tokens.
- 3945740513 — tests: register-under-SMTP-failure pins the full honest-outcome set.
- 3945743644 — architecture: provider usage crosses the port as a Learny-owned DTO.
- 3945747874 — regression: every fixture ripple of the cross-cutting changes was chased.
- 3945751417 — performance: the rails add O(1) work to the hot paths.

## PR-level comments

- `learny-review:requirements` and `learny-review:summary` — scaffolding; deleted after triage per the standing ship instruction (this file is the record).

## Fix commits (Stage 5)

- `dbbcc24f` — fix 1+6: log adapter emits `body=<suppressed>`; adapter test pins token absence.
- `02dde9a9` — fix 2: SMTP STARTTLS + login with new `smtp_use_tls`/`smtp_username`/`smtp_password` settings; documented in the prod example.
- `20c6a5d0` — fix 8: atomic Lua window script with TTL<0 self-heal; live test proves recovery from a TTL-less key.
- `890a4b05` — fix 3: prod compose pins `LEARNY_TRUSTED_PROXY_HOSTS` to the fixed stack subnet (10.28.0.0/16), compose-prod test pins the equality.
- `4df46792` — fix 7: migration `0028_quiz_deck_spend_marker` + conditional-update `claim_spend`; debit+finalize in one transaction.
- `09e80efe` — fix 4: single `media_object_key` builder (in `application/media.py`, avoiding an import cycle) used by upload, corpus, and deletion.
- `478600d2` — fix 5: live-Redis suite skipif-gated; no-server tests moved to always-run `test_rate_limit_fail_closed.py`.
- `2476fcb2` — discovered during gate runs: three web spend-cap tests seeded a frozen UTC day and silently stopped firing at UTC midnight; now seed the live day.
- `5cfc10a9` — format/import-order touch-ups on the fix files.
