# installable-and-adult-launch proofs

**HEAD**: 23435f5
**Tree**: clean
**Result**: 26 pass, 0 fail; mutations 5 killed, 0 not

| Check | Proof | Ran | Passed | Result |
| --- | --- | --- | --- | --- |
| C1 | `cd frontend && npx vitest run tests/pwa-install.test.tsx -t "manifest declares the installable shape and the d` | 1 | 1 | pass |
| C2 | `cd frontend && npx vitest run tests/pwa-install.test.tsx -t "registers the service worker module at /sw.js"` | 1 | 1 | pass |
| C3 | `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "caches chapter and structure reads in the` | 1 | 1 | pass |
| C3 | `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "names one reader cache per user id"` | 1 | 1 | pass |
| C4 | `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "serves the cached chapter when the networ` | 1 | 1 | pass |
| C5 | `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "never caches writes, other api reads, or ` | 1 | 1 | pass |
| C6 | `cd frontend && npx vitest run tests/offline-cache-policy.test.ts -t "purges every other learner's reader cache` | 1 | 1 | pass |
| C7 | `cd frontend && npx vitest run tests/data-saver.test.tsx -t "hides book figures and shows the notice while data` | 1 | 1 | pass |
| C8 | `cd frontend && npx vitest run tests/data-saver.test.tsx -t "persists the toggle and applies it immediately, an` | 1 | 1 | pass |
| C9 | `cd backend && uv run pytest tests/test_web_auth_age.py -k "refuses_register_without_the_age_attestation"` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_web_auth_age.py -k "registers_with_the_attestation_as_before"` | 1 | 1 | pass |
| C11 | `cd frontend && npx vitest run tests/auth-screens.test.tsx -t "register requires the 18-or-older confirmation i` | 1 | 1 | pass |
| C12 | `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "carries the LGPD rights list, the transfer note, ` | 1 | 1 | pass |
| C12 | `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "render the pt-BR catalogs: headings, the rights l` | 1 | 1 | pass |
| C12 | `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "the source tree is clean"` | 1 | 1 | pass |
| C13 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "guest_askes_the_sample_grounded_without_an_accoun` | 2 | 2 | pass |
| C14 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "refuses_an_empty_or_oversized_question_before_any` | 1 | 1 | pass |
| C15 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "rate_limits_guest_asks_per_client_ip"` | 1 | 1 | pass |
| C16 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "refuses_honestly_when_the_sample_budget_is_gone"` | 1 | 1 | pass |
| C17 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "answers_the_honest_outcomes_for_a_missing_sample_` | 1 | 1 | pass |
| C18 | `cd backend && uv run pytest tests/test_web_sample_ask.py -k "debits_the_sample_ledger_only_after_success"` | 1 | 1 | pass |
| C19 | `cd frontend && npx vitest run tests/landing-sample-ask.test.tsx -t "offers the sample ask and labels the answe` | 1 | 1 | pass |
| Build | `cd backend && uv run ruff check . && uv run ruff format --check .` | - | - | pass |
| Build | `cd frontend && npx tsc --noEmit` | - | - | pass |
| Build | `cd frontend && npx vitest run tests/i18n-copy.test.ts` | - | - | pass |
| Build | `python backend/scripts/check_commits.py origin/main..HEAD` | - | - | pass |

## Mutations

| Mutation | Location | Killed |
| --- | --- | --- |
| user-change purge: foreign reader caches are kept instead of deleted | `frontend\public\sw.js:112` | yes |
| unknown user: chapter reads are cached under an unattributed cache before any user id arrives | `frontend\public\sw.js:70` | yes |
| cache scope: every source read (media, notes) becomes cacheable, not just chapter and structure | `frontend\public\sw.js:48` | yes |
| attestation gate: a register without the 18+ confirmation goes through | `backend\app\application\identity.py:181` | yes |
| sample budget: an exhausted sample day no longer refuses before generation | `backend\app\application\sample_ask.py:97` | yes |
