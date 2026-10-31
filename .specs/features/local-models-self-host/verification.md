# local-models-self-host verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: the branch is not a strict fast-forward of `origin/main` — `origin/main` holds 20 commits this branch does not (the harness-reset lane), so a two-dot `origin/main..HEAD` diff mixes main's newer work in as reversals. The feature's honest diff is the merge-base range `034c74a..HEAD`, exactly the 6 PR #84 commits (`b0d9b31` plan, `d6864b3` embeddings factory, `f917ac2` retrieval stamp guard, `2ced0be` generation profile, `9fa70db` ops doc, `7a5fc24` capture runner): 29 files, +2429/−47, all under `backend/`, `docs/` and `.specs/`. Neither `backend/app/worker` nor `backend/tests/test_image_pins.py` is touched.
**Round**: 1 - full (every check C1-C22 proved fresh at `7a5fc24`; nothing carried)
**Verifier**: independent sub-agent (author != verifier)

All 22 checks ran green at `7a5fc24` with located evidence, in three independent passes: the mechanical proof run (22 proof rows + 3 Build rows, all pass, exit 0), an independent verbose union run over all 9 proof files (49 passed, 1 skipped, 0 failed — the single skip is the `@pytest.mark.live` smoke no check selector selects), and the mutation run. All 3 injected faults were killed by their named tests at located assertions. Coverage recomputed from the merge-base diff: no Unproven holes. Lint, format and architecture boundaries are clean, and the completion gate exits 0.

## Scope of this round

`git diff --stat 034c74a..HEAD` code and test files:

- `backend/app/infrastructure/embeddings/openai.py` (+148): compat kind — `base_url`, `expected_dim` validation (`_validate_shape` :158-190), host-naming transport translation (:131-156)
- `backend/app/infrastructure/embeddings/__init__.py` (+29): factory's `openai-compatible` branch (:51-66)
- `backend/app/infrastructure/db/retrieval.py` (+21): the stamp filter on both semantic arms (book :76, book-in-notes-template :189, notes :232) and the `:embedding_model` bind (:355)
- `backend/app/application/retrieval.py` (+4): `RetrieveEvidence` forwards `embedding_model=self._embeddings.model` (:199)
- `backend/app/domain/ports.py` (+8): `RetrievalPort.search` gains required `embedding_model: str` (:709)
- `backend/app/infrastructure/db/metadata.py` (+34/−13): `SettingsDimVector` writes at the configured dim (:81-103)
- `backend/app/cli/embedding_status.py` (new, 201 lines), `backend/app/cli/capture_local_golden.py` (new, 345 lines)
- `backend/app/core/config.py` (+13): `embedding_base_url` (:217) and the provider comments
- `backend/.env.example`, `backend/.env.production.example`: the compat wiring with the self-host-only boundary
- `docs/ops/local-models.md` (new, 165 lines); `docs/adr/0019-…md` amendment section (:127+)
- tests: `test_local_generation_profile.py` (new), `test_embeddings_openai.py` (+157), `test_embeddings_factory.py` (+30), `test_retrieval_stamp_guard.py` (new), `test_cli_embedding_status.py` (new), `test_cli_capture_local_golden.py` (new), `test_ops_docs_local_models.py` (new), `test_reembed.py` (+77), plus the mechanical `embedding_model` threading through `tests/fakes.py`, `test_application_retrieval.py`, `test_retrieval.py`, `test_retrieval_notes.py`, `tests/eval_runner.py`

## Checks (proofs re-run at 7a5fc24)

Three independent runs, all green:

1. The mechanical proof run (its rows are `proofs.md`): the 14 offline proofs group into one pytest invocation over the 6 offline proof files, judged per-test from JUnit; the 9 DB-gated proofs each run as their own pytest process with `LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test` in the same command. Each DB row's `Ran 1` is read from pytest's own summary — a skipped DB test prints "1 skipped", which matches no count pattern and would read `count unknown`, so `Ran 1` means "1 passed". Build rows: `ruff check`, `ruff format --check`, `check_boundaries.py` — all pass.
2. An independent verbose union run over all 9 proof files with the DB env: **49 passed, 1 skipped, 0 failed** (13.8s). The one skip is `test_live_embeds_one_string` (`tests/test_embeddings_openai.py:149`, `@pytest.mark.live`, needs `LEARNY_OPENAI_API_KEY`) — no check's selector selects it. Every selector's tests show PASSED individually, C8's three parametrized shapes included.
3. The mutation run (below) re-ran all 28 rows green in the scratch worktree before injecting.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | declared compat profile serves a `[^n]`-cited ask turn through its `base_url`, real registry → `build_generation_chain`, fake transport | selector ran 1, PASSED | `backend/tests/test_local_generation_profile.py:137` `built_with == [{"api_key": "ollama", "base_url": _BASE_URL}]`; `:138` request names the model; `:141` `cited_chunk_ids == (evidence.chunk_id,)`; `openai` stubbed out of `sys.modules` (`:103`) so no socket exists | PASS |
| C2 | unreachable local runtime raises taxonomy `ProviderUnavailable`, never a raw SDK exception | selector ran 1, PASSED | `backend/tests/test_local_generation_profile.py:152` stub raises `APIConnectionError`; `:156` `pytest.raises(ProviderUnavailable)` through the same chain | PASS |
| C3 | ops doc carries every operator-profile anchor | selector ran 1, PASSED | `backend/tests/test_ops_docs_local_models.py:38-54` asserts all 14 anchors (endpoints :23-24, placeholder :52, prices 0 :37-40, `"grounding": "prompt-cited"` :41, eligibility :42-43, self-host boundary :83) against `docs/ops/local-models.md` | PASS |
| C4 | pt-BR evidence position stated with no quality claim | selector ran 1, PASSED | `backend/tests/test_ops_docs_local_models.py:60-63` `unproven for cited pt-BR answers`, `operator-gated`, `evals/local/`, `capture_local_golden` — at `docs/ops/local-models.md:141` | PASS |
| C5 | compat provider + base URL builds `OpenAIEmbeddingAdapter`, identity `{model}@{dim}`, built with that URL | selector ran 1, PASSED | `backend/tests/test_embeddings_factory.py:67` isinstance, `:68` `== "nomic-embed-text@768"`, `:69` `base_url == "http://localhost:11434/v1"`; factory branch `backend/app/infrastructure/embeddings/__init__.py:51-66` | PASS |
| C6 | compat without base URL raises naming both variables at composition, before SDK import | selector ran 1, PASSED | `backend/tests/test_embeddings_factory.py:79-80` both variable names in the message; raise site `backend/app/infrastructure/embeddings/__init__.py:52-54` (before any client construction); setting `backend/app/core/config.py:217` | PASS |
| C7 | compat sends no `dimensions` param and validates every response | selectors ran 1 + 1, PASSED | `backend/tests/test_embeddings_openai.py:228` `"dimensions" not in resource.calls[0]`; `:226` 768-wide vectors returned; `:231-236` clean 768 response passes validation (per-request validation lives at `openai.py:205-206`) | PASS |
| C8 | wrong count / non-numeric / wrong dimension each raise, one message naming model, dim, received | selector ran 3, PASSED | `backend/tests/test_embeddings_openai.py:255-263`: parametrized wrong-count/non-numeric/wrong-dim, `pytest.raises(ValueError, match=…)` with `"nomic-embed-text"` and `"768"` in every message; raise sites `openai.py:169-189` | PASS |
| C9 | unreachable embedding runtime raises `ProviderUnavailable` naming the host | selector ran 1, PASSED | `backend/tests/test_embeddings_openai.py:270` scripted `APIConnectionError`; `:272` `pytest.raises(ProviderUnavailable, match="localhost:11434")`; translation `openai.py:152-155` | PASS |
| C10 | `local` and `openai` untouched; offline provider pin holds | selectors ran 1 + 1 + 1, PASSED | `backend/tests/test_embeddings_factory.py:27` local → deterministic; `:43` openai → `text-embedding-3-large@1536`; `backend/tests/test_offline_provider_pin.py:51-53` all three default factories network-free | PASS |
| C11 | both env examples document the compat wiring with the amendment's words | selector ran 1, PASSED | `backend/tests/test_ops_docs_local_models.py:80-91`: reads the amendment itself (`:81-82` "Self-host local embeddings", "lexical-only until re-embedded" at `docs/adr/0019-…:152`), then asserts provider value, base URL, SELF-HOST ONLY, the boundary phrase and the runbook link in both env files (`backend/.env.example:53-65`, `backend/.env.production.example:103-114`) | PASS |
| C12 | foreign-stamped chunk returns no semantic evidence; lexical arm still finds it | selector ran 1, PASSED (DB) | `backend/tests/test_retrieval_stamp_guard.py:167` `target in after`; `:171` score drops; `:174` `after[target] <= 1.0/(_K+1)` — the pure-lexical RRF ceiling; filter at `backend/app/infrastructure/db/retrieval.py:76` | PASS |
| C13 | mixed mid-re-embed corpus fuses only current-stamped chunks | selector ran 1, PASSED (DB) | `backend/tests/test_retrieval_stamp_guard.py:200` `current_best > foreign_best`; `:202` `foreign_best <= 1.0/(_K+1)` — no foreign vector earns a semantic term | PASS |
| C14 | notes semantic arm applies the stamp rule against `notes.embedding_model` | selector ran 1, PASSED (DB) | `backend/tests/test_retrieval_stamp_guard.py:253` note stays findable lexically; `:256` score drops; `:257` weighted lexical ceiling; filter at `backend/app/infrastructure/db/retrieval.py:232` | PASS |
| C15 | wrong-length insert raises at the database; one identity per write | selector ran 1, PASSED (DB) | `backend/tests/test_retrieval_stamp_guard.py:266-277` a 768-vector UPDATE raises with the vector-typmod error; column `backend/app/infrastructure/db/metadata.py:81-103`; the stamping half: `set_embeddings` writes `embedding_model` beside every vector (`repositories.py:1071`), end-to-end at `test_reembed.py:330` | PASS |
| C16 | dim misalignment exits 1 printing the exact resize + reembed procedure; no automatic resize | selector ran 1, PASSED (DB) | `backend/tests/test_cli_embedding_status.py:127` `code == 1`; `:129-141` DROP INDEX, three clears, three ALTERs to vector(768), CREATE INDEX, per-source `reembed.document` and `notes.embed`; printed by `backend/app/cli/embedding_status.py:138-181` | PASS |
| C17 | per-source totals/current/stale/distinct stamps + identity and dim; exit 0 aligned | selector ran 1, PASSED (DB) | `backend/tests/test_cli_embedding_status.py:69-78` exit 0, identity, dimension, `total=N current=N-1 stale=1`, `state=mixed`, both stamps, `vector(1536) — ok`, no ALTER; report format `embedding_status.py:105-113` | PASS |
| C18 | end-to-end offline: identity A → flip to 768 → lexical-only → operator clear+resize → re-embed → semantic arm restored, one identity | selector ran 1, PASSED (DB) | `backend/tests/test_reembed.py:312-313` stale top score below before, at the lexical ceiling; `:320` AC 16's resize SQL runs as the middle step; `:324` zero stale; `:330` every row stamped `identity_b`; `:335` fused score above the ceiling again | PASS |
| C19 | capture records one JSONL line per case under `evals/local/`, door-4 fields, every `generation_model` = `--model` | selector ran 1, PASSED (DB) | `backend/tests/test_cli_capture_local_golden.py:154` exit 0; `:158` `len(records) == 16`; `:159` every `generation_model == _SCRIPTED_MODEL`; `:160` door-4 fields; `:161` base_url; `:166` `{"en": 12, "pt": 4}`; fields written at `backend/app/cli/capture_local_golden.py:294-311` | PASS |
| C20 | missing `--base-url` or `--model` exits 2 before any network or DB write | selector ran 1, PASSED | `backend/tests/test_cli_capture_local_golden.py:111-129`: `_uow` replaced by a tripwire first, then three `SystemExit` code-2 cases, `:129` nothing written; `argparse(required=True)` at `capture_local_golden.py:336-338` refuses before `_capture` | PASS |
| C21 | same runner proven offline against an in-process loopback fake server, no test-only branches | selector ran 1, PASSED (DB) | `backend/tests/test_cli_capture_local_golden.py:141-144` `HTTPServer(("127.0.0.1", 0))` with scripted OpenAI-shaped replies; `:148` the same `capture.main` an operator runs; the runner's only seams are `_uow` and `_output_dir` (production defaults at `capture_local_golden.py:70,75`), real ingestion/retrieval/generation otherwise | PASS |
| C22 | pt-BR capture recorded as operator-gated with the reason; ops doc carries the exact procedure | selector ran 1, PASSED | `backend/tests/test_ops_docs_local_models.py:70-74`: `--base-url http://localhost:11434/v1`, `--model`, `JSONL`, "no local runtime on the development machine", "never fakes" — at `docs/ops/local-models.md:148-162`; the same gate is recorded in checks.md's Handoff | PASS |

## Coverage (recomputed from `034c74a..HEAD`)

Every member re-derived from the diff and its proof; no Unproven holes.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| `LEARNY_EMBEDDING_PROVIDER` values (3) | `embeddings/__init__.py:28-66` (three branches) | `local` C10 · `openai` C10 · `openai-compatible` C5 | - |
| unexpected embedding shapes (3) | `openai.py:169-189` (three raise sites) | wrong count C8 · non-numeric C8 · wrong dimension C8 (one parametrized test over all 3, `[wrong-count]`/`[non-numeric]`/`[wrong-dim]`) | - |
| `embedding_status` exits (2) | `embedding_status.py:194-201` (one exit contract) | `0` aligned C17 · `1` misaligned C16 | - |
| `capture_local_golden` exits (2) | `capture_local_golden.py:326-341` | `0` recorded C19 · `2` usage refusal C20 | - |
| retrieval arms under the stamp guard (4) | `retrieval.py` — stamp filter on the two semantic arms only (:76/:189 book, :232 notes); the lexical arms (:88-93, :245-249) carry no stamp predicate | book semantic C12 · book lexical C12 (unfiltered, foreign chunk still found :167) · notes semantic C14 · notes lexical C12/C14 (unfiltered, note still found :253) | - |
| golden capture cases (16) | `capture_local_golden.py:129-170` iterates the canonical lists (`cases.yaml` holds 12 `case_id`s; 3 `PORTUGUESE_CASES` + `PORTUGUESE_UNSUPPORTED_QUESTION`) | C19: 16 lines, `{"en": 12, "pt": 4}`, every line field- and model-asserted; no case-skipping path exists in the runner | - |
| door 1 provider contract (3) | factory :51-66 + adapter request/response path | requires base URL C6 · never sends `dimensions` C7 · response validated per request C7 (per-request `_validate_shape`, `openai.py:205-206`) | - |
| door 2 retrieval-port contract (3) | `ports.py:709`, `application/retrieval.py:199`, `retrieval.py` filters | book arm C12 · notes arm C14 · mixed state fuses current only C13 | - |
| door 3 adapter construction (3) | `OpenAIEmbeddingAdapter.__init__` exclusivity (`openai.py:89-94`), also directly tested at `test_embeddings_openai.py:202-208` | `dimensions=None` omits the param C7 · `expected_dim` validates C8 · transport failure names host C9 | - |
| door 4 capture artifact (3) | runner seams are exactly `_uow`/`_output_dir` | one line per case + door-4 fields C19 · usage refusal before any write C20 · same runner against a loopback fake C21 | - |
| door 5 ADR amendment (2) | `docs/adr/0019-…md:127` amendment; runbook + env examples | ops doc anchors quote the boundary C3 · env examples carry the amendment's words C11 (the test reads the amendment itself and compares) | - |

## Faults injected

Scratch worktree: `git worktree add --detach <temp>/verif-lm/wt-ver HEAD` at `7a5fc24`, with its OWN venv (`uv sync --extra dev`) — deliberately not the shared real `.venv`, because an in-scratch `uv run` would otherwise rewrite the shared venv's editable install to point at the temp tree. Scratch import resolution verified before injecting: `app`, `app.infrastructure.db.retrieval`, `app.infrastructure.embeddings.openai`, `app.cli.capture_local_golden` all reported scratch `__file__` paths (pytest's `pythonpath = ["."]` from the scratch pyproject puts the scratch backend first). Injections ran through the skill's `mutate.py` via `check_proofs --mutations` against the scratch root: each distinct proof first ran green unmutated (baseline), then the fault was injected in place, the proof run, and the file restored byte-for-byte (the script verifies this; scratch `git status` clean between faults, journal removed). Each fault was additionally re-applied and reverted by hand to capture the exact failing assertion quoted below. The real tree's `git status --porcelain` was empty of code changes before and after; the scratch worktree is removed.

| Mutation | Location | Killed |
| --- | --- | --- |
| F1: the book semantic arm accepts any stamped vector (`embedding_model = :embedding_model` → `IS NOT NULL`) | `backend/app/infrastructure/db/retrieval.py:76` | yes: `test_foreign_stamp_skips_semantic_keeps_lexical` fails at `tests/test_retrieval_stamp_guard.py:171` (`assert 0.03278688524590164 < 0.03278688524590164` — the foreign-stamped chunk keeps its full fused score); baseline green |
| F2: the compat adapter accepts a wrong-dimension vector (`if len(vector) != expected:` → `if len(vector) < 0:`) | `backend/app/infrastructure/embeddings/openai.py:183` | yes: `test_unexpected_shape_raises_naming_model_and_dim[wrong-dim]` fails at `tests/test_embeddings_openai.py:258` (`DID NOT RAISE <class 'ValueError'>`); the other two shapes still raise, so discrimination is exact; baseline green |
| F3: the capture writes a `generation_model` that is not the `--model` argument | `backend/app/cli/capture_local_golden.py:305` | yes: `test_records_one_line_per_case` fails at `tests/test_cli_capture_local_golden.py:159` (`assert False` — `all(record["generation_model"] == _SCRIPTED_MODEL)`); baseline green |

## Environment notes

- The unstaged `checks.md` modification is one bookkeeping line only (the `## Handoff` "Dispatched:" entry, recording the verifier dispatch). No check, proof command, coverage or sweep text changed. This verifier did not edit `checks.md`.
- The tlc-spec-lean skill is NOT vendored in this branch's tree (origin/main vendored it after this branch forked). `check_proofs.py`, `mutate.py` and `validate_verification.py` ran from the user-level install `C:/Users/augus/.claude/skills/tlc-spec-lean/scripts/`.
- Windows tooling artifact, disclosed: `check_proofs.py`'s `run_alone` executes non-grouped proofs with `shell=True`, which on Windows means cmd.exe — and cmd.exe cannot run the DB-gated proof lines' POSIX `LEARNY_TEST_DATABASE_URL=… uv run pytest` prefix (this is exactly why the stale, pre-existing `proofs.md` from the interrupted run showed those 9 rows as "fail / count unknown"). A temp driver outside the repo (`%TEMP%/verif-lm/driver.py`) re-pointed ONLY that shell to Git Bash (`C:/Program Files/Git/usr/bin/bash.exe`), the shell this environment prescribes; grouping, selector matching, judging, row writing and exit codes are the script's own. With it, all 22 rows ran as written and the fresh real-tree run exited 0.
- Known environment failures did not appear and were never counted: neither proof set includes `test_worker_task_duration.py` or `test_image_pins.py` (both untouched by this feature's diff; the image-pin fix is on origin/main, and the harness lane's env is separate).
- Sibling lanes ran throughout (5 lane DBs up), so wall clocks are inflated; the union run still finished in 13.8s.
- The Docker bounce predates this session: `lane-loc-db` (5437) and `lane-loc-redis` were up for the whole verification with data intact; no connection error occurred and no re-run was needed.
- Scratch runs used their own venv and no `backend/.env` exists in the worktree (settings all defaults), so scratch and real runs read identical configuration; the DB-gated proofs in the scratch ran against the same `learny_test` database, serialized after the real-tree runs to avoid concurrent Alembic schema setup and the C18 column resize.

## Observations (non-blocking, outside any check's wording)

- The capture's `git_sha` field is stamped from the cwd resolved off `_output_dir` (`capture_local_golden.py:173-185`); under the test's `tmp_path` patch it records `"unknown"`. The door-4 contract (and C19) asserts the field's presence, not its value; a real operator run from `backend/` resolves the repo and stamps the sha. Cosmetic.
- C15's "every embed write stamps one identity per write" half is proven at the write path (`repositories.py:1055-1076`: one executemany setting `embedding` and `embedding_model` together) and end-to-end in C18 (`test_reembed.py:330`), not inside C15's own test — which proves the column's typmod refusal. checks.md's Swept row already attributes the halves this way.
- F2's kill is exact but narrow: it disarms only the per-vector length branch; the count and non-numeric branches keep their own raise sites and their own parametrized cases. A regression in those two branches is caught by the same named test's other two cases.
- `mutate.py`'s interruption journal lives in the shared `.git` dir while a mutation is in flight (worktree git-dir resolution); it is removed on completion and the run's byte-for-byte restore check passed. An interrupted mutation run should be closed with `mutate.py --recover` pointed at the worktree.

## Findings

None - every check C1-C22 has a green, actually-run proof with located evidence; all three injected faults were killed by their named tests at located assertions; coverage recomputes with no Unproven holes; lint, format and boundaries are clean; the completion gate exits 0.

## Gate

- Fresh proof run at `7a5fc24` (real tree, DB env): **22/22 proof rows pass + 3/3 Build rows pass**, `check_proofs.py` exit 0.
- Independent union run over all 9 proof files: **49 passed, 1 skipped (`@pytest.mark.live` smoke, unselected by any check), 0 failed**; every selector's tests individually PASSED.
- Faults: **3 injected, 3 killed** (F1, F2, F3), each re-applied once more to capture the located failing assertion.
- `cd backend && uv run ruff check app tests`: exit 0 ("All checks passed!").
- `cd backend && uv run ruff format --check app tests`: exit 0 ("325 files already formatted").
- `python backend/scripts/check_boundaries.py`: exit 0 ("architecture boundaries clean").
- `python .claude/skills/…/validate_verification.py --root <worktree> --strict local-models-self-host`: exit 0 (0 errors, 0 warnings) — script resolved from the user-level skill install; see Environment notes.
