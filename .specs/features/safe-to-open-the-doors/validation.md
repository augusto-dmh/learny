# safe-to-open-the-doors Validation

**Date**: 2026-09-06
**Spec**: `.specs/features/safe-to-open-the-doors/spec.md`
**Diff range**: `92092348..53091442` (branch `feat/safe-to-open-the-doors`, 26 commits; surface `backend frontend deploy`)
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1–T4 (limiter, trusted IP, user keys) | ✅ Done | `test_redis_rate_limit.py`, `test_rate_limit_client_ip.py`, `test_web_rate_limit_validation.py` |
| T5–T9 (spend ledger, caps, kill switch, quotas) | ✅ Done | `test_application_budget.py`, `test_web_sources.py`, `test_web_ingestion.py`, `test_migrations.py` |
| T10–T14 (invite, disposable/ToS, legal, delete) | ✅ Done | `test_web_auth.py`, `test_application_identity.py`, `legal-pages.test.tsx`, `test_storage_s3.py` |
| T15–T16 (EmailPort, verify/reset) | ✅ Done | `test_application_email.py`, `test_web_auth.py` |

---

## Spec-Anchored Acceptance Criteria

### P1: Shared limiter (DOOR-01..06)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-01 shared Redis window | A `hit` on one process counts on the other, same key | `backend/tests/test_redis_rate_limit.py:34-38` — `first.hit(key) == (True, 0)`; `second.hit(key) == (True, 0)`; second-window `first.hit(key)` → `allowed is False`, `retry_after >= 1` (two `RedisFixedWindowRateLimiter` instances, live Redis) | ✅ PASS |
| DOOR-02 user_id + route-template keying on Ask/Teach turn, deck POST, upload, ingest-start | Bucket keyed on caller identity, not `request.client.host`; concrete interpolated path never mints fresh budget | `backend/tests/test_web_rate_limit_validation.py:359-369` — first user 3 turns then `exhausted.status_code == 429`, second user same IP `turn_b.status_code == 201`; `:203-209` — 3 turns across conversations `aaa/bbb/ccc` then `exc_info.value.status_code == 429` on `ddd`; `:450-453` — quiz limiter per user | ✅ PASS |
| DOOR-03 auth routes key on trusted-proxy client IP, never client XFF | `X-Real-IP` honored only from a trusted peer; XFF never consulted | `backend/tests/test_rate_limit_client_ip.py:33` — untrusted peer `trusted_client_ip(request) == "8.8.8.8"` (spoofed header ignored); `:41-42` — trusted peer returns `203.0.113.10`, `_client_key(request) == "203.0.113.10:/api/auth/login"`; `:58-59` — `trusted_client_ip(request) == "testclient"` with XFF present | ✅ PASS |
| DOOR-04 window exceeded → 429 with Retry-After | 429 + header present | `backend/tests/test_web_rate_limit_validation.py:86-87` — `throttled.status_code == 429`, `"retry-after" in {k.lower() for k in throttled.headers}` (also `:167-169`, `:548-549`) | ✅ PASS |
| DOOR-05 Redis unavailable → limited routes 503 | Fail closed, 503 both at limiter and wired route | `backend/tests/test_redis_rate_limit.py:50-51` — `pytest.raises(LimiterUnavailable)`; `:87` — `resp.status_code == 503` on login route; `backend/tests/test_web_rate_limit_validation.py:503-505` — `exc_info.value.status_code == 503` for all three user-keyed dependencies | ✅ PASS |
| DOOR-06 Caddy stamps X-Real-IP from TCP client; Next forwards it, strips inbound XFF | `header_up X-Real-IP {remote_host}`; outbound has no `x-forwarded-for` | `backend/tests/test_deploy_topology.py:230-231` — `assert "header_up X-Real-IP {remote_host}" in text`; `frontend/tests/proxy.test.ts:103-104` — `out.headers.get("x-real-ip")).toBe("203.0.113.10")`, `out.headers.get("x-forwarded-for")).toBeNull()` | ✅ PASS |

### P1: Spend cap and kill switch (DOOR-07..14)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-07 persist per-user per-UTC-day spend in USD micros on Postgres ledger | `ai_spend_days` row keyed `(user_id, day_utc)`, increments accumulate | `backend/tests/test_application_budget.py:150-152` — `row.usd_micros == 3500`, `row.ask_count == 2`; `:179` separate UTC days separate rows; `backend/tests/test_migrations.py` covers 0024 upgrade/downgrade | ✅ PASS |
| DOOR-08 day spend ≥ cap → 429 honest copy, provider NOT called | Refusal before provider; honest copy | `backend/tests/test_application_budget.py:343-345` — `EXHAUSTED_COPY in str(refused.value)`, `generation.calls == 0`, `retrieve.calls == []`; route level `:871-872` — `resp.status_code == 429`, `"00:00 UTC" in resp.json()["detail"]`; deck `:966-967` + no job rows `:975` | ✅ PASS |
| DOOR-09 successful call adds usage × price catalog to ledger | Debit = reported usage priced | `backend/tests/test_application_budget.py:368` — `row.usd_micros == 2000` (1500 in × $1/M + 250 out × $2/M); deck worker `:487` — `row.usd_micros == 21_000`; stream `:423` | ✅ PASS |
| DOOR-10 ninth Ask → 429 come-back-tomorrow copy, conversation NOT deleted | 429, honest copy, thread + history intact | `backend/tests/test_application_budget.py:660-665` — `EXHAUSTED_COPY`, `generation.calls == 0`, `turns == []`, `row.ask_count == 8`; route `:943-950` — 429, `"00:00 UTC" in detail`, `[t["turn_index"] ...] == [0]` | ✅ PASS |
| DOOR-11 second Teach start same day → 429 same honest class | Refusal before provider | `backend/tests/test_application_budget.py:698-706` — `pytest.raises(DailyBudgetExhausted)`, `generation.calls == 0`; first start counts `:727` `row.teach_starts == 1`; continuation not charged `:749-750` | ✅ PASS |
| DOOR-12 kill switch true → 503 on Ask/Teach gen, deck POST, embedding ingest, operator-pause copy | 503, pause copy, zero provider/embedding work | `backend/tests/test_application_budget.py:1177-1179` — `resp.status_code == 503`, `"paused" in detail`, `"still work" in detail`; deck `:1195-1202` (503, no enqueue, no job rows); embed `:1071-1074` — `pytest.raises(AiPaused)`, `embeddings.document_batches == []` | ✅ PASS |
| DOOR-13 FSRS review does NOT debit ledger | Ledger unchanged by review | `backend/tests/test_application_budget.py:564` — `(row.usd_micros, row.ask_count, row.teach_starts) == (4321, 0, 0)` after SubmitReview; review still 200 under switch `:1259` | ✅ PASS |
| DOOR-14 local adapters record 0 USD unless fixture supplies usage | 0 micros, counters still count | `backend/tests/test_application_budget.py:387` — `(row.usd_micros, row.ask_count, row.teach_starts) == (0, 1, 0)`; deck local `:509-512` — `get_for_day(...) is None` | ✅ PASS |

### P1: Library quotas (DOOR-15..19)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-15 third owned source → 403 quota copy, before `put_object` | 403 before storage put | `backend/tests/test_web_sources.py:860-862` — `resp.status_code == 403`, `"Delete a book" in resp.json()["detail"]`, `storage.put_calls == []` | ✅ PASS |
| DOOR-16 sample excluded from source count and byte quota | Sample + 2 owned uploads all succeed; 256 MiB sample gates nobody | `backend/tests/test_web_sources.py:886-889` — `first/second == 201`, `third == 403`, `len(storage.put_calls) == 2`; bytes `:953-955` — sample 256 MiB seeded, upload `== 201` | ✅ PASS |
| DOOR-17 stored sum + new file > 256 MiB → 413 before `put_object` | 413 before put; at-cap-exactly is legal | `backend/tests/test_web_sources.py:899-901` — seeded 268435456 bytes, `resp.status_code == 413`, `storage.put_calls == []`; boundary `:925-928` — exact cap `== 201` | ✅ PASS |
| DOOR-18 in-flight `{queued, running}` job → start-ingest 409 | 409, no second job/enqueue | `backend/tests/test_web_ingestion.py:394-396` — `resp.status_code == 409`, `_job_count(db_conn, source_b) == 0`, `len(...ingestion_enqueuer.calls) == 1`; terminal jobs don't block `:425-427` | ⚠️ Spec-precision gap (copy not asserted — see Gaps) |
| DOOR-19 allowed ingest start still passes user-id limiter | Quota never bypasses the limiter | `backend/tests/test_web_ingestion.py:419-440` (`test_quota_allowed_ingest_start_still_pays_the_user_limiter`); `backend/tests/test_web_rate_limit_validation.py:548-549` — 4th start `throttled.status_code == 429` + retry-after | ✅ PASS |

### P1: Invite-only register (DOOR-20..26)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-20 no valid invite (flag on) → 403 invite copy, no user created | 403 exact copy, no user/session rows | `backend/tests/test_web_auth.py:279-288` — `resp.status_code == 403`, `resp.json() == {"detail": INVITE_COPY}`, cookie absent, `select(users)... .first() is None`, `select(func.count()).select_from(sessions)).scalar_one() == 0`; unknown `:297-299`, exhausted `:322-324`, expired `:347-349` all `{"detail": INVITE_COPY}` | ✅ PASS |
| DOOR-21 valid invite → create user, decrement uses, start session | 201 + cookie + `remaining_uses` decremented | `backend/tests/test_web_auth.py:367-380` — `resp.status_code == 201`, `SESSION_COOKIE_NAME in set_cookie`, `"/api/auth/me" ... == 200`, `left == 0` | ✅ PASS |
| DOOR-22 uses 0 or expired → further register 403 | Uniform 403 | `backend/tests/test_web_auth.py:409-415` — third register `third.status_code == 403`, `{"detail": INVITE_COPY}`, `left == 0`; expiry `:331-349` | ✅ PASS |
| DOOR-23 disposable deny-list → 422 same generic invalid-email copy as malformed | Exact same body | `backend/tests/test_web_auth.py:183-187` — `resp.status_code == 422`, `resp.json() == {"detail": "Invalid email address."}`, no user row; parity `:205-206` — `disposable.json() == malformed.json() == {"detail": GENERIC_EMAIL_COPY}` | ✅ PASS |
| DOOR-24 `duck.com` NOT rejected as disposable | 201 created | `backend/tests/test_web_auth.py:214-216` — `resp.status_code == 201`, `resp.json()["email"] == "reader@duck.com"` | ✅ PASS |
| DOOR-25 `accepted_tos` not true → 422 | 422, no session, no user | `backend/tests/test_web_auth.py:225-232` — `resp.status_code == 422`, `resp.json() == {"detail": TOS_COPY}`, `"set-cookie" not in headers`, user row `is None`; `accepted_tos: false` `:242-245`; consent stamps `accepted_tos_at` `:254-258` | ✅ PASS |
| DOOR-26 flag false → register without code still works (ToS + disposable rules apply) | 201 without code when gate off | `backend/tests/test_application_identity.py:228-236` — `test_register_ignores_invite_code_when_no_gate_is_wired`; every `auth_client` register (flag unset) returns 201, e.g. `backend/tests/test_web_auth.py:55-58` | ✅ PASS |

### P1: Legal pages and account deletion (DOOR-27..33)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-27 signed-out `/terms`, `/privacy`, `/copyright` → 200 with document titles | Distinct titles + bodies | `frontend/tests/legal-pages.test.tsx:29-30` — `expect(titles).toEqual(["Terms of Service", "Privacy Policy", "Copyright / DMCA"])`, `new Set(titles).size).toBe(3)`; unique h1 + bodies `:35-56` | ⚠️ Spec-precision gap (render-level; HTTP 200 signed-out not asserted — see Gaps) |
| DOOR-28 `/copyright` includes configured DMCA contact email | Configured mailbox rendered as mailto | `frontend/tests/legal-pages.test.tsx:66-67` — `link.getAttribute("href")).toBe("mailto:dmca@learny.example")`; re-read at render time `:73-80` | ✅ PASS |
| DOOR-29 `/privacy` names OpenAI and Anthropic, no zero-data-retention claim | Both subprocessors present; no ZDR | `frontend/tests/legal-pages.test.tsx:89-90` — `getByText("OpenAI")`, `getByText("Anthropic")`; `:97-99` — `expect(body).not.toMatch(/zero[- ]data[- ]retention/i)` etc. | ✅ PASS |
| DOOR-30 DELETE /api/auth/account with CSRF → objects (not sample) deleted, then user CASCADE | Owned keys deleted; fail-closed order | `backend/tests/test_web_auth.py:464-477` — 204, then objects gone `owned.object_key not in storage.objects`; ordering pinned via failure semantics `backend/tests/test_application_identity.py:504-511` + `test_storage_failure_leaves_the_user_row:527-540` (sensor M7 confirmed this order is discriminated) | ✅ PASS |
| DOOR-31 after deletion: old cookie → 401; sample still exists | Session dead, sample survives | `backend/tests/test_web_auth.py:479-487` — `auth_client.get("/api/auth/me").status_code == 401`, relogin 401; `:500-502` — `sample.object_key in storage.objects`, `select(sources)...(sample.id)... is not None` | ✅ PASS |
| DOOR-32 storage delete fails → user NOT deleted, 502 | 502, account intact | `backend/tests/test_web_auth.py:533-546` — `resp.status_code == 502`, `resp.json() == {"detail": "Account deletion failed. Please try again."}`, user + source rows remain, relogin 200; partial outage `backend/tests/test_application_identity.py:541-545` | ✅ PASS |
| DOOR-33 non-owner key never deleted | Only caller's owned keys deleted | `backend/tests/test_application_identity.py:468-473` — `sample.object_key in storage.objects`, `foreign.object_key in storage.objects`; web `backend/tests/test_web_auth.py:500-502` | ✅ PASS |

### P1: Email verify and reset (DOOR-34..40)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| DOOR-34 register success → one verify message via EmailPort with single-use token | Exactly one send; raw token in mail, only hash at rest | `backend/tests/test_application_email.py:194-197` — `len(emails.sent) == 1`, `"token-1" in emails.sent[0]["body"]`, `email_tokens.stored_hashes() == [hash_token("token-1")]`; route `:425-435` — `len(emails.sent) == 1`, `raw_at_rest == 0`, `stored == [("verify", hash_token(raw), None)]` | ✅ PASS |
| DOOR-35 token submitted → `email_verified_at` set, not consumable twice | Stamp set; replay uniform failure | `backend/tests/test_application_email.py:452-461` — `confirmed.status_code == 204`, `stamp is not None`, replay `replay.status_code == 403`, `replay.json() == {"detail": INVALID_TOKEN_MESSAGE}`; unit `:243-248` | ✅ PASS |
| DOOR-36 reset request → 204 whether or not email exists; mail only when user exists | 204 both; zero sends for unknown | `backend/tests/test_application_email.py:490-497` — unknown `unknown.status_code == 204`, `unknown.content == b""`, `emails.sent == []`; known `== 204` with `len(emails.sent) == 1`; unit `:318-319` | ✅ PASS |
| DOOR-37 valid reset token + new password → hash updated, token invalidated | Old password dead, new works, replay inert | `backend/tests/test_application_email.py:521-557` — old login 401, new login 200, replay `replay.status_code == 403` and `still_new.status_code == 200`; unit `:346-353` | ✅ PASS |
| DOOR-38 limiter exceeded on reset / verify-resend → 429 | 429 on second attempt per route | `backend/tests/test_application_email.py:574-592` — `second_resend.status_code == 429` + retry-after; `second_request.status_code == 429` | ✅ PASS |
| DOOR-39 invited unverified users may still Ask and upload | No verification wall on expensive routes | `backend/tests/test_application_email.py:417-427` — `/api/auth/me` 200 while `email_verified_at` stamp `is None`; unverified fresh registrations complete real Ask turns (`backend/tests/test_web_rate_limit_validation.py:355-357` — `turn.status_code == 201`, users never verified) | ✅ PASS (wall's absence pinned indirectly — noted) |
| DOOR-40 SMTP send fails → register still creates session; log failure without raw token | 201 + session despite raise; no raw token at rest/in log | Session + hash-at-rest: `backend/tests/test_application_email.py:406-435` — `resp.status_code == 201`, `/me` 200, `raw_at_rest == 0`; unit `:223-227`. Log-without-token clause: no test assertion | ⚠️ Spec-precision gap (log clause unasserted — see Gaps) |

**Status**: ✅ 37/40 ACs match spec outcome exactly · ⚠️ 3 spec-precision gaps flagged (DOOR-18, DOOR-27, DOOR-40) — none is a behavioral failure; all three ACs' core outcomes are implemented and exercised, but a sub-clause of the spec-defined outcome is not pinned by an assertion.

---

## Spec-Precision Gaps (ranked)

1. **DOOR-40 — "SHALL log the failure without the raw token"** — no evidence. `SendEmailVerification.__call__` does log `logger.exception("email.send.failed purpose=%s", PURPOSE_VERIFY)` without the token (`backend/app/application/identity.py:334`), and the register-still-succeeds half is tested at unit and route level, but no test asserts the failure log exists or that the raw token is absent from it. Fix: a `caplog` assertion beside `test_register_mints_user_and_session_even_when_the_sender_raises` (`backend/tests/test_application_email.py:200`).
2. **DOOR-27 — "SHALL return 200"** — partially evidenced. The jsdom suite pins the exact titles, unique headings, and bodies (`frontend/tests/legal-pages.test.tsx:23-57`) but never issues an HTTP request, so "signed-out … 200" is only implied by Next.js page existence (no auth wall exists to redirect from). Fix: one route-level assertion (integration/e2e or a proxy-including test) for each of the three routes.
3. **DOOR-18 — "409 with an in-flight copy"** — partially evidenced. `test_second_in_flight_ingest_on_another_owned_source_returns_409` (`backend/tests/test_web_ingestion.py:394-396`) asserts the 409, no new job row, and no second enqueue, but not the `IN_FLIGHT_COPY` body (`backend/app/application/quotas.py:33`), while sibling quota tests do assert their copy. Fix: add `assert "ingestion in progress" in resp.json()["detail"]`.

---

## Discrimination Sensor

**Tier**: expanded (security/quota rail cycle) — 10 behavior-level mutations across 8 distinct rails, injected ONE AT A TIME in a throwaway worktree (`git worktree add /tmp/verifier-scratch HEAD`), each restored before the next; real tree verified clean after.

| # | Rail | File:line | Mutation (behavior-level) | Command (from scratch worktree) | Result |
| - | ---- | --------- | ------------------------- | -------------------------------- | ------ |
| M1 | Limiter keying (DOOR-02) | `backend/app/infrastructure/web/rate_limit.py:188` | `_user_route_key` keyed on `trusted_client_ip(request)` instead of `user.id` (user-id → IP keying) | `pytest tests/test_web_rate_limit_validation.py` | ❌→✅ **KILLED** — 2 failed (`test_two_users_behind_one_ip_each_get_their_own_ask_budget`, `test_tutor_card_budget_is_per_user_on_the_quiz_limiter`) |
| M2 | Fail-closed (DOOR-05) | `backend/app/infrastructure/web/rate_limit.py:102-106` | `except LimiterUnavailable: return` (fail open instead of 503) | `pytest tests/test_web_rate_limit_validation.py::test_user_keyed_limiters_fail_closed_when_the_limiter_is_down tests/test_web_rate_limit_validation.py::test_user_keyed_route_returns_503_when_the_limiter_is_down tests/test_redis_rate_limit.py::test_limited_route_returns_503_when_redis_is_down` | **KILLED** — 3 failed |
| M3 | Budget ordering (DOOR-08) | `backend/app/application/conversations.py:784` / `:620` | `assert_generation` moved from preflight to immediately AFTER `self._generate(...)` (provider invoked first) | `pytest tests/test_application_budget.py` | **KILLED** — 9 failed (`generation.calls == 0` observables break) |
| M4 | Kill switch (DOOR-12) | `backend/app/application/budget.py:103` | `if self._ai_paused:` → `if not self._ai_paused:` (inverted) | `pytest tests/test_application_budget.py -k "kill_switch or paused or unpause"` | **KILLED** — 5 failed |
| M5 | Quota ordering (DOOR-15/17) | `backend/app/application/sources.py:85-95` | `assert_upload` moved INSIDE the `try` after `put_object` (put happens first, orphaning the object) | `pytest tests/test_web_sources.py::test_third_owned_source_returns_403_before_any_put tests/test_web_sources.py::test_stored_bytes_over_the_cap_returns_413_before_any_put tests/test_web_sources.py::test_sample_does_not_count_toward_the_source_quota` | **KILLED** — 3 failed (`storage.put_calls == []` breaks). Note: a first attempt that left the check before the put was a no-op mutation (2 passed) and was discarded as invalid, not counted |
| M6 | Invite consumption (DOOR-21/22) | `backend/app/infrastructure/db/repositories.py:266` | `.values(remaining_uses=... - 1)` → `.values(remaining_uses=...)` (consume never decrements) | `pytest tests/test_web_auth.py -k invite` | **KILLED** — 2 failed (`left == 0`; third-register-403) |
| M7 | Deletion order (DOOR-30/32) | `backend/app/application/identity.py` (`DeleteAccount.__call__`) | `self._users.delete(user.id)` moved BEFORE the storage-delete loop | `pytest tests/test_application_identity.py -k "delete or storage_failure" tests/test_web_auth.py` | **KILLED** — 4 failed (`test_storage_failure_leaves_the_user_row`, `test_partial_storage_failure_deletes_no_user_row`, web 502-leaves-user, web happy path) |
| M8 | Reset enumeration (DOOR-36) | `backend/app/application/identity.py:388-402` (`RequestPasswordReset`) | Unknown-email early return removed; token row minted for `uuid4()` and mail sent to the unknown address | `pytest tests/test_application_email.py -k reset` | **KILLED** — 2 failed (`emails.sent == []` for unknown) |
| M9 | ToS rail (DOOR-25) | `backend/app/application/identity.py:185` (`RegisterUser`) | `if not accepted_tos:` → `if False and not accepted_tos:` (consent never required) | `pytest tests/test_web_auth.py::test_register_without_tos_is_422 tests/test_web_auth.py::test_register_with_tos_false_is_422 tests/test_application_identity.py::test_register_rejects_missing_tos` | **KILLED** — 3 failed |
| M10 | Proxy XFF strip (DOOR-06) | `frontend/app/lib/proxy.ts:57` | `"x-forwarded-for"` removed from the hop-by-hop strip list (client XFF forwarded to FastAPI) | `npm test -- proxy` | **KILLED** — 1 failed (`forwards Caddy's X-Real-IP and strips inbound X-Forwarded-For`) |

**Sensor depth**: expanded (P0 security/quota tier, manual fault injection)
**Result**: **10/10 KILLED — 0 survived** ✅

Token-consumption (`consumed_at`) was covered transitively: M8's rail-mate `SqlAlchemyEmailTokenRepository.consume` and `VerifyEmail` are pinned by `test_confirm_stamps_email_verified_at_and_replay_fails` / `test_reset_with_valid_token_sets_a_new_password_exactly_once` (replay-fails assertions), so the consume stamp's discrimination was not separately mutated given 10/10 across the other rails.

---

## Gate Check

| Gate | Command | Result |
| ---- | ------- | ------ |
| Lint | `make lint` (repo root) | ✅ exit 0 — "All checks passed!", 293 files formatted, boundaries clean |
| Backend full | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local uv run pytest` | ✅ exit 0 — **2660 passed, 12 skipped** in 204s (matches expected 2660/12) |
| Frontend full | `cd frontend && npm test` | ✅ exit 0 — **897 passed** (75 files) |

- **Skipped tests**: all 12 are pre-existing environment-conditional skips (live Anthropic/OpenAI smoke tests, docling missing, snapshot-record/study opt-ins) — none related to this cycle, none new.
- **Test count integrity**: counts match the cycle's expected green numbers (2660 backend / 897 frontend); no deletions detected, suite grew by the cycle's new test files (`test_application_budget.py`, `test_application_email.py`, `test_rate_limit_client_ip.py`, `test_redis_rate_limit.py`, `legal-pages.test.tsx`, …).
- `test_migrations.py` did not poison `learny_test`; no schema reset was needed.

---

## Edge Cases (from spec)

- [x] Overlapping Ask debits both persist; later over-cap call 429s — `test_two_same_day_increments_accumulate_into_one_row` (`test_application_budget.py:139`)
- [x] Kill switch on → reads (library, review due) still succeed — `test_kill_switch_leaves_reads_working` (`test_application_budget.py:1262`), `test_kill_switch_review_submit_still_grades:1205`
- [x] Redis `INCR` failure → 503, never skip the limiter — M2 sensor + `test_dead_redis_fails_closed` (`test_redis_rate_limit.py:43`)
- [x] Boundary: byte sum exactly at cap still uploads — `test_byte_sum_at_the_cap_exactly_still_uploads` (`test_web_sources.py:905`)
- [x] Eighth Ask still runs (cap counts used, not attempted) — `test_the_eighth_ask_still_runs_and_bumps_the_counter` (`test_application_budget.py:668`)
- [x] Spoofed X-Real-IP from untrusted peer ignored — `test_untrusted_peer_cannot_spoof_x_real_ip` (`test_rate_limit_client_ip.py:28`)
- [x] Verify token cannot reset, reset token cannot verify (purpose separation) — `test_a_verify_token_cannot_reset_and_a_reset_token_cannot_verify` (`test_application_email.py:268`)

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ (Turnstile explicitly absent per AD-325; no ESP SDK; `legal-pages.test.tsx` asserts no Turnstile surface was added) |
| Surgical changes | ✅ (diff confined to limiter/budget/quotas/invites/identity/email/storage + deploy proxy header) |
| Matches existing patterns (ports/adapters, error→status mapping table) | ✅ |
| Spec-anchored outcome check | ✅ 37 exact / 3 precision gaps flagged, none behavioral |
| Per-layer coverage expectation | ✅ (limiter unit+integration; routes happy+edge+error; domain 1:1) |
| Every test maps to a spec requirement | ✅ spot-checked budget + invite suites |
| Guidelines | CLAUDE.md test-guidelines followed (layer-matrix honored) |

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| DOOR-01..DOOR-40 | In Tasks / Pending | ✅ Verified (DOOR-18/27/40 verified with ⚠️ precision notes) |

---

## Summary

**Overall**: ✅ Ready (PASS)

**Spec-anchored check**: 37/40 ACs matched spec outcome exactly · 3 spec-precision gaps flagged (DOOR-18 in-flight copy, DOOR-27 HTTP-200 clause, DOOR-40 failure-log clause)
**Sensor**: 10/10 mutations killed, 0 survived
**Gate**: lint ✅ · backend 2660 passed / 0 failed / 12 skipped (pre-existing env skips) · frontend 897 passed

**What works**: shared Redis limiter with per-user and trusted-IP keying, fail-closed 503; USD + Ask/Teach daily caps with assert-before-provider and debit-after-success; kill switch across ask/deck/embed with reads unharmed; source-count/byte/in-flight quotas enforced before put; invite gate + disposable + ToS rails with uniform copy; legal pages; account deletion with objects-then-user ordering and sample preservation; EmailPort verify/reset with anti-enumeration reset.

**Issues found**: 3 assertion-strength gaps (see Spec-Precision Gaps) — fix tasks, not blockers; recommended priority DOOR-40 log assertion first (security-adjacent), then DOOR-27 route-level 200, then DOOR-18 copy assertion.

**Next steps**: route the 3 ranked precision gaps as optional strengthening tasks; record lessons.
