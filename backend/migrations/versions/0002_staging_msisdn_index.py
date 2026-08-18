"""Index import_staging_rows(import_id, normalized_msisdn) for duplicate detection.

mark_duplicate_msisdns (app.repositories.import_repository) runs a
window-function UPDATE partitioned by normalized_msisdn per import - this
index keeps that a single index scan instead of a sequential scan at
17M-row scale.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX ix_import_staging_rows_import_msisdn "
        f"ON {SCHEMA}.import_staging_rows (import_id, normalized_msisdn) "
        f"WHERE validation_status = 'VALID';"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_import_staging_rows_import_msisdn;")
