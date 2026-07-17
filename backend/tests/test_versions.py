"""
Test version consistency across backend and frontend packages.

Ensures that backend/pyproject.toml and frontend/package.json both declare version 0.2.0
and are in sync, preventing accidental version drift (DEP-20).
"""

import json
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_version_is_0_2_0():
    """Backend version in pyproject.toml equals 0.2.0."""
    pyproject_path = _REPO_ROOT / "backend" / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == "0.2.0"


def test_frontend_version_is_0_2_0():
    """Frontend version in package.json equals 0.2.0."""
    package_path = _REPO_ROOT / "frontend" / "package.json"
    with open(package_path) as f:
        data = json.load(f)
    assert data["version"] == "0.2.0"


def test_backend_and_frontend_versions_match():
    """Backend and frontend versions agree."""
    pyproject_path = _REPO_ROOT / "backend" / "pyproject.toml"
    package_path = _REPO_ROOT / "frontend" / "package.json"

    with open(pyproject_path, "rb") as f:
        backend_version = tomllib.load(f)["project"]["version"]

    with open(package_path) as f:
        frontend_version = json.load(f)["version"]

    assert backend_version == frontend_version
