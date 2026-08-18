"""Add imports.import_kind (BASE | DND).

Phase 3: DND import reuses the entire Phase 2 ingestion pipeline (same
parser, normalizer, staging table, worker, lock, retry endpoints) rather
than a parallel bespoke system - this column is what lets commit_import()
branch between "commit into a new base_version/base_members" and "commit
into a new dnd_lists/dnd_records version" at the end of an otherwise
identical stage->preview->approve->commit flow.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE {SCHEMA}.imports
        ADD COLUMN import_kind TEXT NOT NULL DEFAULT 'BASE'
            CHECK (import_kind IN ('BASE', 'DND'));
    """)
    op.execute(f"CREATE INDEX ix_imports_kind ON {SCHEMA}.imports (import_kind);")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_imports_kind;")
    op.execute(f"ALTER TABLE {SCHEMA}.imports DROP COLUMN IF EXISTS import_kind;")
