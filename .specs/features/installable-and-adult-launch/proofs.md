# installable-and-adult-launch proofs

**HEAD**: 3be2a16
**Tree**: clean
**Result**: 13 pass, 12 fail; mutations 3 killed, 0 not

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
| C9 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C10 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C11 | `cd frontend && npx vitest run tests/auth-screens.test.tsx -t "register shows a required age confirmation in bo` | 0 | 0 | **no test ran** |
| C12 | `cd frontend && npx vitest run tests/legal-pages.test.tsx -t "renders every legal page from the catalogs in bot` | 0 | 0 | **no test ran** |
| C12 | `cd frontend && npx vitest run tests/i18n-hardcoded.test.ts -t "hard-coded string sensor"` | 0 | 0 | **no test ran** |
| C13 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C14 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C15 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C16 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C17 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C18 | `cd backend && LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL="postgresql+psycopg://learny:learny@localhost:5438/` | count unknown | - | **fail** |
| C19 | `cd frontend && npx vitest run tests/landing-sample-ask.test.tsx -t "offers the sample ask and labels the answe` | 0 | 0 | **no test ran** |
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
