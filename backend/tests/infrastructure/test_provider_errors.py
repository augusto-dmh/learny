"""Provider error taxonomy gate (unit, stdlib-only).

Derived from the taxonomy acceptance criteria: the package exports the five
Learny-owned classes; the four concrete classes sit directly under the
``ProviderError`` base (and under nothing else — no class implies another's
retryability); a raised instance carries its message as ``str`` for the server
log; each concrete class's docstring states its retryability contract (Timeout
and ProviderUnavailable retryable across providers, RateLimited one same-provider
backoff retry then cross, RequestRejected never retried blindly across
providers); and the package imports the standard library only, so the
architecture fitness gate can never see a provider SDK cross it.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import sys

import pytest

from app.infrastructure.providers import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

_CONCRETE = (Timeout, RateLimited, ProviderUnavailable, RequestRejected)


# --- Type hierarchy --------------------------------------------------------------


@pytest.mark.parametrize("cls", _CONCRETE, ids=lambda c: c.__name__)
def test_each_concrete_error_subclasses_the_provider_base(cls: type) -> None:
    assert issubclass(cls, ProviderError)


def test_the_base_is_an_exception_not_a_vendor_shape() -> None:
    assert issubclass(ProviderError, Exception)


def test_concrete_classes_imply_no_others_retryability() -> None:
    # A router deciding on classes must never see one class satisfy another:
    # no concrete class may subclass a sibling.
    for cls in _CONCRETE:
        for sibling in _CONCRETE:
            if sibling is cls:
                continue
            assert not issubclass(cls, sibling)


def test_all_five_classes_are_exported_from_the_package() -> None:
    package = importlib.import_module("app.infrastructure.providers")
    for name in (
        "ProviderError",
        "Timeout",
        "RateLimited",
        "ProviderUnavailable",
        "RequestRejected",
    ):
        assert hasattr(package, name)


# --- str payloads (server-log culture: the message is the carrier) ---------------


@pytest.mark.parametrize("cls", _CONCRETE, ids=lambda c: c.__name__)
def test_a_raised_error_carries_its_message_as_str(cls: type) -> None:
    with pytest.raises(ProviderError) as excinfo:
        raise cls("provider did not answer")
    assert str(excinfo.value) == "provider did not answer"


# --- The retryability contract is stated on the class ----------------------------


@pytest.mark.parametrize(
    ("cls", "phrases"),
    [
        (Timeout, ("Retryable across providers",)),
        (ProviderUnavailable, ("Retryable across providers",)),
        (RateLimited, ("One same-provider backoff retry", "cross")),
        (RequestRejected, ("Never retried blindly across providers",)),
    ],
    ids=lambda c: c.__name__ if isinstance(c, type) else "",
)
def test_each_docstring_states_its_retryability_contract(
    cls: type, phrases: tuple[str, ...]
) -> None:
    docstring = cls.__doc__ or ""
    for phrase in phrases:
        assert phrase in docstring


# --- Stdlib-only import discipline (fitness-gate sensor) -------------------------


def test_the_package_imports_the_standard_library_only() -> None:
    package_dir = pathlib.Path(
        importlib.import_module("app.infrastructure.providers").__file__
    ).parent
    imported: set[str] = set()
    for source in package_dir.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    # Absolute ``app.*`` imports are the repo convention and the standard library
    # is free; anything third-party (a provider SDK above all) is the violation
    # this sensor exists for. The one sanctioned non-stdlib exception is
    # ``pydantic``: the profile registry's settings model lives here by design
    # (cheaper-intelligence, design §2) and is config, never a provider SDK.
    assert imported <= {"__future__", "app", "pydantic"} | set(sys.stdlib_module_names)
