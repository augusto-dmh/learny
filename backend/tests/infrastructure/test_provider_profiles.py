"""Generation profile registry — settings parsing, validation, legacy seed (ROUTE-01/05/06).

The registry is the single source of truth for generation selection when declared
(ROUTE-01's config half); a malformed one fails fast at composition with an
actionable message (ROUTE-05, spec §Edge Cases); an empty one synthesizes exactly
the profile today's single-provider settings describe, so the default deployment
behaves byte-for-byte as before (ROUTE-06 / AD-342).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.providers.profiles import (
    LEGACY_PROFILE_ID,
    GenerationProfileSettings,
    resolve_generation_profiles,
)

_PROFILE_JSON = {
    "id": "primary",
    "kind": "anthropic",
    "model": "claude-sonnet-5",
    "api_key_env": "LEARNY_TEST_PROFILE_KEY",
    "effort_ask": "medium",
    "effort_teach": "low",
    "max_tokens": 4096,
    "price_input_usd_per_million_tokens": 3.0,
    "price_output_usd_per_million_tokens": 15.0,
    "price_cache_read_usd_per_million_tokens": 0.3,
    "price_cache_creation_usd_per_million_tokens": 3.75,
    "grounding": "verified-spans",
    "ask_enabled": True,
    "teach_enabled": True,
}


def _settings_with_profiles(profiles: list[dict[str, Any]]) -> Settings:
    return Settings(
        _env_file=None,
        generation_profiles=[GenerationProfileSettings(**p) for p in profiles],
    )


# --- Settings fields (ROUTE-01 config half) --------------------------------------


def test_profile_registry_settings_default_to_undeclared(monkeypatch) -> None:
    # The default deployment declares nothing: an empty registry (the legacy seed
    # path) and an empty explain profile (→ the primary serves selection-Explain).
    monkeypatch.delenv("LEARNY_GENERATION_PROFILES", raising=False)
    settings = Settings(_env_file=None)

    assert settings.generation_profiles == []
    assert settings.generation_explain_profile == ""


def test_profile_registry_env_parses_a_json_list(monkeypatch) -> None:
    # LEARNY_GENERATION_PROFILES carries a JSON list that parses into typed
    # profiles — including the openai-compatible kind this cycle adds, declared
    # inactive (the economy profile ships Ask-ineligible, EVAL-03).
    declared = dict(
        _PROFILE_JSON,
        id="economy",
        kind="openai-compatible",
        ask_enabled=False,
        teach_enabled=False,
    )
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([declared]))

    settings = Settings(_env_file=None)

    assert [p.id for p in settings.generation_profiles] == ["economy"]
    economy = settings.generation_profiles[0]
    assert economy.kind == "openai-compatible"
    assert (economy.ask_enabled, economy.teach_enabled) == (False, False)


def test_profile_registry_env_rejects_an_unknown_kind(monkeypatch) -> None:
    # ROUTE-01's kind vocabulary is closed: a typo'd kind is a parse failure, not a
    # profile that silently matches no adapter branch.
    monkeypatch.setenv(
        "LEARNY_GENERATION_PROFILES", json.dumps([dict(_PROFILE_JSON, kind="gemini")])
    )

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "kind" in message
    for known in ("local", "anthropic", "openai-compatible"):
        assert known in message


# --- Composition-time validation branches (ROUTE-05) ------------------------------


def test_a_compat_kind_profile_builds_with_effort_values_it_cannot_express(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ECON-05 sensor: a profile whose adapter kind cannot express effort builds fine
    # with effort values set — declared degradation, never a validation error (the
    # adapter kind that ignores them at request time is the openai-compatible one).
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-test")
    profile = GenerationProfileSettings(
        id="economy",
        kind="openai-compatible",
        model="glm-5.3-flash",
        base_url="https://us.example-inference/v1",
        api_key_env="LEARNY_TEST_PROFILE_KEY",
        effort_ask="low",
        effort_teach="max",
        max_tokens=4096,
        price_input_usd_per_million_tokens=0.2,
        price_output_usd_per_million_tokens=0.75,
        price_cache_read_usd_per_million_tokens=0.02,
        price_cache_creation_usd_per_million_tokens=0.25,
        grounding="prompt-cited",
        ask_enabled=False,
        teach_enabled=False,
    )

    # The values ride along uninterpreted and the declared registry resolves.
    assert (profile.effort_ask, profile.effort_teach) == ("low", "max")
    resolved = resolve_generation_profiles(Settings(_env_file=None, generation_profiles=[profile]))
    assert [p.id for p in resolved] == ["economy"]


def test_declared_registry_resolves_in_declared_order(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-test")
    settings = _settings_with_profiles(
        [_PROFILE_JSON, dict(_PROFILE_JSON, id="fallback", kind="local", api_key_env="")]
    )

    resolved = resolve_generation_profiles(settings)

    assert [p.id for p in resolved] == ["primary", "fallback"]


def test_duplicate_profile_ids_fail_fast_naming_the_id() -> None:
    settings = _settings_with_profiles([_PROFILE_JSON, dict(_PROFILE_JSON)])

    with pytest.raises(ValueError) as excinfo:
        resolve_generation_profiles(settings)
    message = str(excinfo.value)
    assert "primary" in message
    assert "unique" in message


def test_an_empty_profile_id_fails_fast() -> None:
    settings = _settings_with_profiles([dict(_PROFILE_JSON, id="")])

    with pytest.raises(ValueError, match="empty id"):
        resolve_generation_profiles(settings)


def test_an_unknown_kind_at_composition_fails_fast_naming_the_kind() -> None:
    # model_construct bypasses parse-time validation, exercising the resolver's own
    # kind branch (defense at composition, independent of how the list was built).
    bogus = GenerationProfileSettings.model_construct(**{**_PROFILE_JSON, "kind": "gemini"})
    settings = Settings(_env_file=None, generation_profiles=[bogus])

    with pytest.raises(ValueError) as excinfo:
        resolve_generation_profiles(settings)
    message = str(excinfo.value)
    assert "gemini" in message and "primary" in message


def test_an_anthropic_profile_without_a_key_env_name_fails_fast() -> None:
    settings = _settings_with_profiles([dict(_PROFILE_JSON, api_key_env="")])

    with pytest.raises(ValueError, match="api_key_env"):
        resolve_generation_profiles(settings)


def test_a_profile_whose_key_env_var_is_unset_fails_fast_naming_both(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LEARNY_TEST_PROFILE_KEY", raising=False)
    settings = _settings_with_profiles([_PROFILE_JSON])

    with pytest.raises(ValueError) as excinfo:
        resolve_generation_profiles(settings)
    message = str(excinfo.value)
    assert "LEARNY_TEST_PROFILE_KEY" in message and "primary" in message


def test_a_keyed_profile_passes_validation(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-test")
    settings = _settings_with_profiles([_PROFILE_JSON])

    assert [p.id for p in resolve_generation_profiles(settings)] == ["primary"]


# --- Legacy seed equivalence (ROUTE-06 / AD-342) ----------------------------------


def test_empty_registry_synthesizes_one_profile_equal_to_todays_settings(
    monkeypatch,
) -> None:
    # Byte-for-byte equivalence: the synthesized profile carries exactly the values
    # today's factory would read — provider as kind, the model, the effort on both
    # modes, the max-token budget, the global price pair, and derived cache prices.
    monkeypatch.delenv("LEARNY_GENERATION_PROFILES", raising=False)
    monkeypatch.setenv("LEARNY_GENERATION_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("LEARNY_GENERATION_EFFORT", "medium")
    monkeypatch.setenv("LEARNY_GENERATION_MAX_TOKENS", "4096")
    monkeypatch.setenv("LEARNY_PRICE_INPUT_USD_PER_MILLION_TOKENS", "3.0")
    monkeypatch.setenv("LEARNY_PRICE_OUTPUT_USD_PER_MILLION_TOKENS", "15.0")
    settings = Settings(_env_file=None)

    resolved = resolve_generation_profiles(settings)

    assert len(resolved) == 1
    legacy = resolved[0]
    assert legacy.id == LEGACY_PROFILE_ID
    assert legacy.kind == "local"  # today's default provider
    assert legacy.model == "claude-sonnet-5"
    assert (legacy.effort_ask, legacy.effort_teach) == ("medium", "medium")
    assert legacy.max_tokens == 4096
    assert legacy.price_input_usd_per_million_tokens == 3.0
    assert legacy.price_output_usd_per_million_tokens == 15.0
    # Derived cache prices: read 0.1× and creation 1.25× the input price.
    assert legacy.price_cache_read_usd_per_million_tokens == pytest.approx(0.3)
    assert legacy.price_cache_creation_usd_per_million_tokens == pytest.approx(3.75)
    # Today's behavior: the single provider serves every grounded mode.
    assert legacy.ask_enabled and legacy.teach_enabled
    assert legacy.grounding == "verified-spans"


def test_legacy_anthropic_settings_seed_an_anthropic_profile(monkeypatch) -> None:
    monkeypatch.delenv("LEARNY_GENERATION_PROFILES", raising=False)
    settings = Settings(
        _env_file=None, generation_provider="anthropic", anthropic_api_key="sk-test"
    )

    resolved = resolve_generation_profiles(settings)

    assert len(resolved) == 1
    legacy = resolved[0]
    assert legacy.kind == "anthropic"
    assert legacy.api_key_env == "LEARNY_ANTHROPIC_API_KEY"
    assert legacy.grounding == "verified-spans"


def test_legacy_seed_rejects_todays_unknown_provider_with_todays_message(
    monkeypatch,
) -> None:
    # The factory has always refused an undeclared provider at composition; the
    # seed refuses with the same message, so nothing starts that would not have.
    monkeypatch.delenv("LEARNY_GENERATION_PROFILES", raising=False)
    settings = Settings(_env_file=None, generation_provider="openai")

    with pytest.raises(ValueError, match="unknown generation provider: openai"):
        resolve_generation_profiles(settings)


def test_legacy_anthropic_seed_without_a_key_fails_fast_with_todays_message(
    monkeypatch,
) -> None:
    # The factory's fail-fast discipline, preserved verbatim (ROUTE-05).
    monkeypatch.delenv("LEARNY_GENERATION_PROFILES", raising=False)
    settings = Settings(_env_file=None, generation_provider="anthropic", anthropic_api_key="")

    with pytest.raises(
        ValueError,
        match="LEARNY_ANTHROPIC_API_KEY is required when the generation provider is 'anthropic'",
    ):
        resolve_generation_profiles(settings)


# --- Learner-key binding: user-key-only profiles never join a house chain ----------
#
# A profile opts in to learner keys with ``user_key_provider``. One that names
# no ``api_key_env`` is user-key-only: the house has no key for it, so it must
# never appear in a house chain (default, selection-Explain, or a learner's
# preference chain) nor in the house catalog. A registry left with nothing the
# house can serve fails resolution; a non-local profile with neither a house key
# nor a binding still fails exactly as before.

_USER_KEY_ONLY = dict(
    _PROFILE_JSON,
    id="byok-claude",
    model="claude-byok",
    api_key_env="",
    user_key_provider="anthropic",
)
_HOUSE_LOCAL = dict(
    _PROFILE_JSON,
    id="house-local",
    kind="local",
    model="local-extractive",
    api_key_env="",
)


def _chain_ids(chain: object) -> list[str]:
    return [entry.profile.id for entry in chain._chain]  # type: ignore[attr-defined]


def test_user_key_only_profile_passes_validation_without_a_key_env() -> None:
    settings = _settings_with_profiles([_HOUSE_LOCAL, _USER_KEY_ONLY])

    resolved = resolve_generation_profiles(settings)

    assert [p.id for p in resolved] == ["house-local", "byok-claude"]
    assert resolved[1].user_key_provider == "anthropic"


def test_user_key_only_profile_never_joins_a_house_chain_or_the_catalog(monkeypatch) -> None:
    from app.infrastructure.answering import build_generation_chain, build_user_generation_chain
    from app.infrastructure.providers import learner_catalog

    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-test")
    keyed_house = dict(_PROFILE_JSON, id="house-claude")
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            GenerationProfileSettings(**p) for p in (_USER_KEY_ONLY, keyed_house, _HOUSE_LOCAL)
        ],
        # Even when the operator names it as the Explain profile.
        generation_explain_profile="byok-claude",
    )

    assert _chain_ids(build_generation_chain(settings)) == ["house-claude", "house-local"]
    assert _chain_ids(build_generation_chain(settings, explain=True)) == [
        "house-claude",
        "house-local",
    ]
    # A stored preference naming it cannot pull it into the learner's house chain.
    assert _chain_ids(build_user_generation_chain(settings, "byok-claude")) == [
        "house-claude",
        "house-local",
    ]
    assert [p.id for p in learner_catalog(settings)] == ["house-claude", "house-local"]


def test_user_key_only_registry_without_a_house_servable_profile_fails() -> None:
    settings = _settings_with_profiles(
        [_USER_KEY_ONLY, dict(_USER_KEY_ONLY, id="byok-gpt", user_key_provider="openai")]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_generation_profiles(settings)

    message = str(excinfo.value)
    assert "house" in message
    assert "user_key_provider" in message


def test_user_key_only_rule_still_rejects_a_profile_with_neither_key_source() -> None:
    # Neither a house key env nor a learner-key binding: today's failure, unchanged.
    settings = _settings_with_profiles([_HOUSE_LOCAL, dict(_PROFILE_JSON, api_key_env="")])

    with pytest.raises(ValueError, match="api_key_env"):
        resolve_generation_profiles(settings)


def test_user_key_only_binding_keeps_the_unset_key_env_rule_for_house_keyed_profiles(
    monkeypatch,
) -> None:
    # A profile that names a house key env still needs it set, binding or not.
    monkeypatch.delenv("LEARNY_TEST_PROFILE_KEY", raising=False)
    both = dict(_PROFILE_JSON, user_key_provider="anthropic")
    settings = _settings_with_profiles([_HOUSE_LOCAL, both])

    with pytest.raises(ValueError, match="LEARNY_TEST_PROFILE_KEY"):
        resolve_generation_profiles(settings)


def test_user_key_only_field_defaults_to_unbound_for_existing_registries(monkeypatch) -> None:
    # Every registry declared before the field existed parses unchanged.
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([_PROFILE_JSON]))

    settings = Settings(_env_file=None)

    assert settings.generation_profiles[0].user_key_provider is None


def test_user_key_only_binding_rejects_an_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        GenerationProfileSettings(**dict(_USER_KEY_ONLY, user_key_provider="mistral"))


def test_user_key_only_binding_on_a_local_profile_fails() -> None:
    settings = _settings_with_profiles([dict(_HOUSE_LOCAL, user_key_provider="anthropic")])

    with pytest.raises(ValueError, match="local"):
        resolve_generation_profiles(settings)
