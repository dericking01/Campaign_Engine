"""Add imports.committed_dnd_list_id - the DND-import counterpart to
committed_base_version_id, populated when a DND-kind import commits.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE {SCHEMA}.imports
        ADD COLUMN committed_dnd_list_id BIGINT REFERENCES {SCHEMA}.dnd_lists(id);
    """)


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.imports DROP COLUMN IF EXISTS committed_dnd_list_id;")
