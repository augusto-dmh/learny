"""Learner-facing profile metadata — copy fields and the account-page catalog.

``GenerationProfileSettings`` carries two optional copy fields the operator
authors (``display_name`` / ``description``); ``learner_catalog`` derives from
the declared registry the catalog the learner may choose from. The contract
under test:

- Env JSON that omits the copy fields parses exactly as before (the fields are
  optional and default empty), and JSON that declares them parses them through.
- The catalog is exactly the declared registry, in registry order, with honest
  fallback copy (empty ``display_name`` → the id; ``description`` may be empty)
  and no operational field on it — never the adapter kind, the key env-var
  name, the base URL, or a price.
- An undeclared registry yields an empty catalog: the synthetic legacy seed
  never appears — by construction (the declared list is empty), not by id
  sniffing, so a deployment declaring a profile literally named ``default``
  still lists it.
"""

from __future__ import annotations

import json

from app.core.config import Settings
from app.infrastructure.providers import (
    GenerationProfileSettings,
    LearnerProfile,
    learner_catalog,
)

# The minimal profile declaration an operator's env carried before the copy
# fields existed — no ``display_name``, no ``description``.
_BARE_PROFILE_JSON = (
    '{"id": "primary", "kind": "local", "model": "local-extractive", "max_tokens": 1024, '
    '"price_input_usd_per_million_tokens": 3.0, "price_output_usd_per_million_tokens": 15.0, '
    '"price_cache_read_usd_per_million_tokens": 0.3, '
    '"price_cache_creation_usd_per_million_tokens": 3.75, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true}'
)


def _profile(**overrides: object) -> GenerationProfileSettings:
    bare = json.loads(_BARE_PROFILE_JSON)
    bare.update(overrides)  # type: ignore[union-attr]
    return GenerationProfileSettings(**bare)  # type: ignore[arg-type]


# --- The copy fields are optional: existing env JSON parses unchanged --------------


def test_env_json_without_copy_fields_parses_exactly_as_before() -> None:
    parsed = GenerationProfileSettings(**json.loads(_BARE_PROFILE_JSON))

    expected = GenerationProfileSettings(
        id="primary",
        kind="local",
        model="local-extractive",
        max_tokens=1024,
        price_input_usd_per_million_tokens=3.0,
        price_output_usd_per_million_tokens=15.0,
        price_cache_read_usd_per_million_tokens=0.3,
        price_cache_creation_usd_per_million_tokens=3.75,
        grounding="verified-spans",
        ask_enabled=True,
        teach_enabled=True,
    )
    # Absent fields equal explicitly-empty fields: one parse, byte for byte.
    assert parsed == expected
    assert parsed.display_name == ""
    assert parsed.description == ""


def test_declared_copy_fields_parse_through() -> None:
    parsed = GenerationProfileSettings(
        **json.loads(_BARE_PROFILE_JSON),
        display_name="Primary",
        description="The house standard; full citations.",
    )

    assert parsed.display_name == "Primary"
    assert parsed.description == "The house standard; full citations."


# --- The catalog: honest copy, nothing operational, seed never appears -------------


def test_an_undeclared_registry_yields_an_empty_catalog() -> None:
    # The default deployment declares nothing; its registry is the synthetic
    # legacy seed alone, and the seed is not a learner choice.
    assert learner_catalog(Settings(_env_file=None)) == ()


def test_a_declared_profile_named_default_still_appears() -> None:
    # Seed exclusion is by construction (nothing declared → nothing listed),
    # never id-sniffing: an operator who declares "default" lists "default".
    settings = Settings(_env_file=None, generation_profiles=[_profile(id="default")])

    assert [entry.id for entry in learner_catalog(settings)] == ["default"]


def test_the_catalog_is_the_declared_registry_in_order_with_fallback_copy() -> None:
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(),
            _profile(
                id="economy-glm",
                kind="openai-compatible",
                model="zai-org/glm-5.3-flash",
                base_url="https://api.fireworks.ai/inference/v1",
                api_key_env="LEARNY_FIREWORKS_API_KEY",
                grounding="prompt-cited",
                ask_enabled=False,
                teach_enabled=False,
                display_name="Economy",
                description="Cheaper answers; citations may be less precise.",
            ),
        ],
    )

    catalog = learner_catalog(settings)

    assert [entry.id for entry in catalog] == ["primary", "economy-glm"]
    # Empty copy falls back honestly: the id names the profile, the copy line
    # is empty (the UI hides it) — never invented.
    assert catalog[0].display_name == "primary"
    assert catalog[0].description == ""
    assert catalog[0].grounding == "verified-spans"
    assert (catalog[0].ask_enabled, catalog[0].teach_enabled) == (True, True)
    # Declared copy travels with the profile, eligibility as declared.
    assert catalog[1].display_name == "Economy"
    assert catalog[1].description == "Cheaper answers; citations may be less precise."
    assert catalog[1].grounding == "prompt-cited"
    assert (catalog[1].ask_enabled, catalog[1].teach_enabled) == (False, False)


def test_a_catalog_entry_carries_no_operational_field() -> None:
    settings = Settings(_env_file=None, generation_profiles=[_profile()])

    (entry,) = learner_catalog(settings)
    assert isinstance(entry, LearnerProfile)
    payload = entry.model_dump()

    assert set(payload) == {
        "id",
        "display_name",
        "description",
        "grounding",
        "ask_enabled",
        "teach_enabled",
    }
    # The declaration carried secrets-adjacent and cost fields; none leaks.
    serialized = json.dumps(payload)
    for leaked in ("api_key_env", "base_url", "price", "max_tokens", "kind", "effort"):
        assert leaked not in serialized
