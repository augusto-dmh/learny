# installable-and-adult-launch review triage — independent post-merge round

Review mode: **full independent review** (author != reviewer), 2026-10-31, over the merged tree at HEAD `357f18d`. Ran the six pr-review lenses (Security; Requirements & DoD; Test Coverage; Architecture & Patterns; Regression; Performance) over both merged PR diffs — `c5e7680..6ee308c` (PR #87: PWA/offline/data-saver) and `6ee308c..9c2905b` (PR #88: attestation/legal/guest Ask). Per the dispatch: no GitHub comments were posted (both PRs are merged); findings live here. Scope note: this pass ran as one reviewer rather than six parallel subagents; every diff file was opened and judged.

**Verdict: no Critical, no Security-severity, no Performance, no Regression findings. 3 Low, 2 Suggestion, 1 Observation. None blocks the launch; the coordinator dispatches fixes.**

Well-done aspects (per the skill's positive-highlight rule): the guest cap ordering is defense-in-depth done right — the limiter dependency fires before the boundary validation (refused 422s deliberately spend visitor budget, anti-abuse), the budget is asserted before any retrieval, and the debit lands only after the port returned (`backend/app/application/sample_ask.py:97-133`); the data-saver strip happens in the sanitize pass with an empty allowlist (`frontend/app/components/chapter-markdown.tsx:28-30`), so a metered learner never even opens a media request instead of hiding images after fetching them; `X-Forwarded-For` is never consulted anywhere (`rate_limit.py:157-168`), so the classic header-chain spoof mints nothing; and the per-user cache purge is verified down to the exact deleted-name list (`offline-cache-policy.test.ts:209-227`).

## Findings

### 1. Low (security/abuse posture — pre-existing default, newly exposed surface)

- **Where:** `backend/app/core/config.py:112` (`trusted_proxy_hosts` default `"127.0.0.1,::1,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"`) + `backend/app/infrastructure/web/rate_limit.py:157-168` (`trusted_client_ip`) + `rate_limit.py:287-290` (`rate_limit_sample_ask`).
- **What:** any peer connecting from an RFC1918 address is treated as a trusted proxy, so its `X-Real-IP` header is honored for the limiter key. The guest sample ask is the first *anonymous* surface keyed on this: a direct-connect client from a private-network vantage (container network, LAN, VPC without strict egress rules) can rotate `X-Real-IP` to mint fresh per-IP buckets and consume the sample's whole daily budget/ask cap (`guest_sample_daily_budget_usd=0.5`, `guest_sample_daily_ask_cap=50`), denying the feature to other visitors. Cost stays capped by the sample budget — this is a feature-availability DoS, not a cost leak. The default predates this PR (verified: `trusted_client_ip` is untouched by both diffs), but PR #88 is what makes it reachable without an account.
- **Recommended action:** for production, set `LEARNY_TRUSTED_PROXY_HOSTS` to only the real proxy CIDR and document it beside the sample-ask settings; consider warning at startup when the default private-range set is active with `environment=production`.

### 2. Low (reproducibility of the declared mutations)

- **Where:** `.specs/features/installable-and-adult-launch/mutations.json` (entries 1–3 `frontend/public/sw.js`, entry 5 `backend/app/application/sample_ask.py` use `\n`; entry 4 uses `\r\n`) against LF git blobs checked out CRLF under `core.autocrlf=true`; `mutate.py` does no line-ending normalization.
- **What:** on a fresh checkout (verified in a detached scratch worktree at `357f18d`), 4 of the 5 declared `old` strings match 0 occurrences and mutate.py refuses the entry — a re-run of the declared mutations from a clean clone cannot reproduce the recorded "5 killed" without adapting the spec to the checkout's bytes. This round did exactly that (same semantic mutations, `\r\n`-adapted, each verified to occur exactly once) and killed all 7. The author's run was made against a then-current mixed-LF/CRLF on-disk state, which is why it passed then and would not now.
- **Recommended action:** normalize these files' line endings in-repo (`.gitattributes`, e.g. `*.py text eol=lf` / `*.js text eol=lf`) or regenerate `mutations.json` from the checked-out bytes; note the constraint in checks.md's mutation header.

### 3. Low (robustness, self-healing) — service-worker attribution on a failed auth probe

- **Where:** `frontend/app/components/service-worker-registrar.tsx:48-51` (the `catch` around `fetchAuthState`).
- **What:** if the auth probe fails exactly when the signed-in user changes (transient network error during logout/login), the registrar posts nothing and the worker keeps its previous attribution; until the next page load or `learny:auth-changed` broadcast, chapter reads could be cached under the previous learner's cache name. Impact is bounded: only 2xx responses are ever cached (`sw.js:84`), a logged-out visitor's chapter reads are 401s and store nothing, and the next successful page load re-posts and purges — so this is a transient mis-attribution window, not a persistence leak. The same code path is correct on the happy path, which the tests cover.
- **Recommended action:** optionally retry the probe once (short backoff) before giving up; or leave as-is with a comment acknowledging the window. Not launch-blocking.

### 4. Suggestion (information disclosure, deliberate-or-not)

- **Where:** `backend/app/infrastructure/web/sample_ask.py:63` (`model: str | None`) in the anonymous response.
- **What:** the guest answer body carries the serving model identity (e.g. profile id/model name) to anyone on the internet; the authenticated surface shows the same field to its own caller, but this makes it public. Deployment-infrastructure disclosure value is minimal, but it is also unused by the landing UI (`guest-sample-ask.tsx` never reads `result.model`).
- **Recommended action:** either drop `model` from the guest response shape or record it as deliberate in the route docstring.

### 5. Suggestion (spec hygiene)

- **Where:** `.specs/features/installable-and-adult-launch/checks.md:10` says `Mutations: 3`; the committed `mutations.json` declares 5 and both recorded rounds verified 5 (this round 7).
- **Recommended action:** update the count to match the declared set.

### 6. Observation (docs wording, no behavior impact)

- **Where:** `backend/tests/test_web_auth_age.py:33-35` says the attestation is "checked before anything else"; `backend/app/application/identity.py:178-182` checks `accepted_tos` first, then the attestation. Every test case sends `accepted_tos: true`, so the asserted age copy is what the code answers; only the docstring overstates the ordering.

## Lens-by-lens summary (what was judged, not just what was found)

- **Security:** guest endpoint surface walked end to end — origin gate (`csrf.py` `enforce_origin`, active by default via `csrf_trusted_origins` non-empty default), per-IP limiter keyed on trusted-proxy IP + route with `Retry-After`, question ceiling validated at the boundary before the service, `SampleUnavailable → 503` / `AnswerGenerationFailed → 502` / `ValidationError → 422` mappings confirmed in `error_handlers.py:139,181`. No user input reaches a source id (the service resolves the sample itself, `sample_ask.py:92-95`); the guest retrieval composition omits the activation recorder so no row is written for a visitor (`dependencies.py`, guest section); no PII or question text is logged (`sample_ask.py:107,139,144` log only outcome booleans). Cache-key collisions across users are impossible by construction (cache *names* are per user id, `sw.js:31-33`); a message can only come from a same-origin client; `activate` wipes unattributed caches. The attestation bypass class is closed at the boundary default (`web/auth.py:90` `age_attested: bool = False`) *and* the application gate (`identity.py:181`), both mutation-verified. Finding 1 is the one abuse-surface note.
- **Requirements & DoD:** every C1–C19 claim matches implemented behavior (each also proven mechanically — see `verification.md` independent round). LGPD copy vs code: the terms' 18+ claim (`legal.terms.accountBody`) matches the enforced gate; "AI subprocessors" names OpenAI (embeddings) and Anthropic (retrieved passages + questions), which is what the live path actually does; the rights list tracks LGPD Art. 18 items and the ANPD route and international-transfer notes are present; catalog key sets are identical across en/pt-BR (48 legal keys, zero parity diff) and the hard-coded-string sensor's legal exemption is gone (`i18n-hardcoded.test.ts:17-18`). The landing refusal copy matches the actual refusal statuses (`exhausted` only on 429, `notFound` on `found:false`).
- **Test coverage:** the new suites assert behavior, not shape — `test_web_sample_ask.py` pins language-to-port, no-persistence, debit-only-after-success with the exact micros math (6000 µs at the default catalog), budget-before-retrieval on both USD and ask count; `test_web_auth_age.py` counts users/credentials/sessions/invites before-and-after; `offline-cache-policy.test.ts` asserts exact deleted-cache lists and honest failure; `landing-sample-ask.test.tsx` pins the POST body shape and both locales' copy.
- **Architecture & patterns:** layering clean — `application/sample_ask.py` imports only application/domain/ports; the web router stays thin; composition lives in `dependencies.py` (`build_guest_budget`, `get_guest_sample_ask`); `check_boundaries.py` passes. The dedicated sample limiter instance correctly avoids borrowing the auth limiter's window shape (`rate_limit.py:98-115`, wired in `main.py:107-115`).
- **Regression:** the Streamdown remount key is constant on the non-data-saver path (`key={dataSaver ? "saver" : "figures"}`), so normal rendering never churns; the image allowlist stays confined to `chapter-markdown.tsx` — the Ask/Teach `MessageResponse` (`frontend/components/ai-elements/message.tsx:326-332`) keeps Streamdown's default harden and imports nothing from the chapter allowlist. The `register()` signature change has exactly one caller, updated in the same PR (`AuthForm.tsx:47`). Auth-changed broadcasts cover register, login, and logout (`lib/auth.ts:99,118,153`).
- **Performance:** per-request embedding-adapter construction on the guest path mirrors the authenticated path (parity, not a regression); the Redis limiter shares one pooled client and fails closed 503 when down; SW cache growth is capped at 30 entries with oldest-first eviction; the guest budget cap bounds worst-case spend per day.

## Hardening round (dispatched post-merge fixes; 2026-11-01)

Each finding was re-judged against the merged code before any change; verdicts and the shape actually shipped are recorded here. Fixes land on `fix/installable-hardening` off `origin/main` (`357f18d`) as their own reviewed PR, with the spec records committed first so this round travels with them.

### Finding 1 — Low, security/abuse: REAL, fixed

- **Re-judgement:** confirmed. `backend/app/core/config.py:112` defaults `trusted_proxy_hosts` to all three RFC1918 ranges; `rate_limit.py:140-168` honors `X-Real-IP` from any peer matching that list; `rate_limit_sample_ask` (`rate_limit.py:277-290`) keys the guest limiter on exactly that value. The hosted stack itself is already narrow — `docker-compose.prod.yml:77` pins `10.28.0.0/16` and `test_compose_prod.py:180-215` locks the pair — so the residual exposure is any API boot that reaches real users without that overlay (a self-host on a LAN, a bare `environment=production` process): a direct-connect private peer can rotate `X-Real-IP` and mint fresh per-IP buckets against the sample's daily budget.
- **Action shipped:** the production default is tightened — with `LEARNY_ENVIRONMENT=production` and the variable unset, the effective trust list falls back to loopback + the TestClient host only; local development keeps today's RFC1918 default unchanged. A startup warning fires when a hosted declaration (`hosted_instance=true`) trusts any entry covering a whole RFC1918 range, naming the variable and the offending entries. The prod compose overlay (already documented beside the rate-limit wiring) is the documented override path. Both claims are pinned by tests: a direct private-IP client without trusted-proxy status cannot rotate identity under the production default, and a genuinely proxied request still rate-limits by the real client IP behind a narrow overlay.

### Finding 2 — Low, reproducibility: REAL, fixed

- **Re-judgement:** confirmed. No `.gitattributes` exists and every text blob in the index is already LF, so under `core.autocrlf=true` a fresh checkout materializes CRLF while the committed `mutations.json` mixes LF `old` strings (entries 1–3, 5) with one CRLF entry (4) — `mutate.py` matches raw bytes, so exactly one entry can match per checkout flavor and 4/5 refuse. Either checkout breaks the declared set; the recorded rounds ran against an on-disk byte state a clean clone cannot reproduce.
- **Action shipped:** a repo-wide `.gitattributes` with `* text=auto eol=lf`. Judged repo-wide (not scoped) after checking the blast radius: the normalization is checkout policy only — every text blob is LF already, so the commit adds no content diff; there are no `.bat`/`.cmd`/`.ps1` files that need CRLF; the six `.sh` scripts only benefit (LF is what they require); the frontend sensors parse with the TypeScript compiler API and vitest is line-ending-insensitive; CI already runs LF on Linux. `mutations.json` entry 4 is regenerated to LF so the declared set matches the post-normalization bytes, and the previously-refusing set is proven to apply and die in a fresh worktree simulation.

### Finding 3 — Low, robustness: REAL, fixed (fail-honest purge)

- **Re-judgement:** confirmed, and the swallow is strictly less conservative than the neighboring path: `fetchAuthState` maps *any* non-200 — including a 5xx — to signed-out, which posts `userId: null` and purges the reader caches; only a network-level reject (fetch rejects) lands in the swallowed `catch`. A failed probe should answer the same honest signed-out state instead of a different one.
- **Action shipped:** on probe failure the registrar posts the signed-out message (the worker deletes every reader cache — caches repopulate on the next read) and logs once (first failure per page load). The trade-off is recorded deliberately: an offline reload purges correctly-attributed caches and offline reading degrades until connectivity returns — accepted because the component's own contract is private-data safety before convenience, and a transient mis-attribution window (one learner's reads cached under another's cache name until the next successful probe) is worse than repopulating. The switch-failure path is pinned by test.

### Finding 4 — Suggestion, disclosure: REAL, fixed

- **Re-judgement:** confirmed. `SampleAskResponse.model` (`web/sample_ask.py:63`) reaches anonymous callers and nothing consumes it: the landing component never reads `result.model`, and the route's declared response body is `{found, answer, citations, sample}` — `model` is not part of the declared contract.
- **Action shipped:** the field is dropped from the public response; `GuestAnswer.model`'s only consumer was that response mapping, so the dataclass field goes too rather than turning write-only. The frontend result type and its test fixture lose the key as well.

### Finding 5 — Suggestion, spec hygiene: REAL, fixed

- **Re-judgement:** confirmed. `checks.md` says `Mutations: 3`; the committed `mutations.json` declares 5 (the three service-worker rules plus the attestation gate and the sample budget assert) and both recorded rounds verified the declared 5.
- **Action shipped:** the count is amended to 5 in this same spec-records commit.

### Finding 6 — Observation: acknowledged, not acted on

Docs-wording only (a test docstring overstating check order); no behavior claim is wrong, and the dispatch scoped this round to findings 1–5.
