"""Terms of Service acceptance stamp on users

Adds a nullable ``accepted_tos_at`` timestamp to ``users``: register stamps it
with the creation time when the account accepted the Terms of Service (DOOR-25),
so the recorded consent travels with the account. It is nullable because the
sample operator account is created through no form and accepts nothing.

Downgrade drops the column.

Revision ID: 0026_user_tos_stamp
Revises: 0025_invite_codes
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_user_tos_stamp"
down_revision: str | None = "0025_invite_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("accepted_tos_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "accepted_tos_at")
