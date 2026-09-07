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
