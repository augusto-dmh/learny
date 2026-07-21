"""Vault-export router — download your notes and highlights as an Obsidian vault (NL-16).

Thin FastAPI adapter over the framework-free ``ExportVault`` service: a signed-in user
GETs their whole second brain as a deterministic ``Learny/`` vault zip. Like the Anki
export (AD-146), this is a plain authenticated GET — no CSRF, no job, no S3 — and the
web layer packs the bytes with the pure ``build_vault`` builder (the service stays free
of ``zipfile``).

Contract:
- ``GET /api/export/vault`` → 200 ``application/zip`` attachment ``learny-vault.zip``;
  auth only. No session → 401. A caller with no notes/highlights still gets a valid
  skeleton zip.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.application.vault import ExportVault
from app.domain.entities import User
from app.infrastructure.export.obsidian import build_vault
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_export_vault,
)

router = APIRouter(tags=["export"])


@router.get("/api/export/vault")
def export_vault(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ExportVault, Depends(get_export_vault)],
) -> Response:
    """Stream the caller's notes + highlights as an Obsidian-vault zip (200; 401).

    ``ExportVault`` gathers only the caller's own data (both reads are ``user_id``-scoped,
    NL-20); ``build_vault`` projects it to a deterministic ``Learny/`` folder (NL-19). The
    bytes are returned as an ``application/zip`` attachment named ``learny-vault.zip``.
    """
    notes, highlights_by_source = service(user=user)
    data = build_vault(notes, highlights_by_source)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="learny-vault.zip"'},
    )
