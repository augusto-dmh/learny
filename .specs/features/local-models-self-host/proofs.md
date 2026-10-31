# local-models-self-host proofs

**HEAD**: 7a5fc24
**Tree**: clean
**Result**: 28 pass, 0 fail; mutations 3 killed, 0 not

| Check | Proof | Ran | Passed | Result |
| --- | --- | --- | --- | --- |
| C1 | `cd backend && uv run pytest tests/test_local_generation_profile.py -k "serves_ask_turn_through_declared_base_u` | 1 | 1 | pass |
| C2 | `cd backend && uv run pytest tests/test_local_generation_profile.py -k "unreachable_runtime_raises_provider_una` | 1 | 1 | pass |
| C3 | `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "operator_profile_anchors"` | 1 | 1 | pass |
| C4 | `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "pt_br_evidence_position"` | 1 | 1 | pass |
| C5 | `cd backend && uv run pytest tests/test_embeddings_factory.py -k "compat_provider_builds_openai_adapter"` | 1 | 1 | pass |
| C6 | `cd backend && uv run pytest tests/test_embeddings_factory.py -k "compat_provider_without_base_url"` | 1 | 1 | pass |
| C7 | `cd backend && uv run pytest tests/test_embeddings_openai.py -k "compat_omits_dimensions_parameter"` | 1 | 1 | pass |
| C7 | `cd backend && uv run pytest tests/test_embeddings_openai.py -k "compat_validates_response_shape"` | 1 | 1 | pass |
| C8 | `cd backend && uv run pytest tests/test_embeddings_openai.py -k "unexpected_shape_raises_naming_model_and_dim"` | 3 | 3 | pass |
| C9 | `cd backend && uv run pytest tests/test_embeddings_openai.py -k "transport_failure_names_host"` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_embeddings_factory.py -k "local_provider_builds_deterministic_adapter"` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_embeddings_factory.py -k "test_openai_provider_builds_openai_adapter_fr` | 1 | 1 | pass |
| C10 | `cd backend && uv run pytest tests/test_offline_provider_pin.py::test_default_factories_are_deterministic` | 1 | 1 | pass |
| C11 | `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "env_examples_document_compat_wiring"` | 1 | 1 | pass |
| C12 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C13 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C14 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C15 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C16 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C17 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C18 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C19 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C20 | `cd backend && uv run pytest tests/test_cli_capture_local_golden.py -k "missing_args_exit_two_before_network_or` | 1 | 1 | pass |
| C21 | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run py` | 1 | - | pass |
| C22 | `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "capture_procedure_and_operator_gate"` | 1 | 1 | pass |
| Build | `cd backend && uv run ruff check app tests` | - | - | pass |
| Build | `cd backend && uv run ruff format --check app tests` | - | - | pass |
| Build | `python backend/scripts/check_boundaries.py` | - | - | pass |

## Mutations

| Mutation | Location | Killed |
| --- | --- | --- |
| F1: the book semantic arm accepts any stamped vector (a foreign stamp is no longer skipped) | `backend\app\infrastructure\db\retrieval.py:76` | yes |
| F2: the compat adapter accepts a wrong-dimension vector (no per-vector length check) | `backend\app\infrastructure\embeddings\openai.py:183` | yes |
| F3: the capture writes a generation_model that is not the --model argument | `backend\app\cli\capture_local_golden.py:305` | yes |
