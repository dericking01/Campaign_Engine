"""Configurable sender ID per campaign, and a staff notification list.

Operator-supplied correction: the DR (Doctor) product's real sender ID is
"AFYACALL" (matching the legacy drmaster.php script), not "15723" like
SMS/IVR - the 0001 seed data had this wrong for DOCTOR. Fixed here as a
data migration, and campaigns.sender_id/messages.sender_id are added so
this is GUI-editable per campaign (falling back to channel_configs.sender_id
when unset) rather than only settable in code.

staff_contacts is a simple compliance roster (name + msisdn), intentionally
with NO foreign-key relationship to messages: campaigns.
include_staff_notifications, when true, snapshots the *currently active*
staff list into that run's messages at queue time - same as how
audience_members already stores customer_msisdn as plain data rather than
an FK to a customers table. This means staff_contacts rows can be safely
hard-deleted later without touching historical message records.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"
MSISDN_CHECK = "msisdn ~ '^255[0-9]{9}$'"


def upgrade() -> None:
    op.execute(f"UPDATE {SCHEMA}.channel_configs SET sender_id = 'AFYACALL' WHERE channel = 'DOCTOR';")

    op.execute(f"ALTER TABLE {SCHEMA}.campaigns ADD COLUMN sender_id TEXT;")
    op.execute(
        f"ALTER TABLE {SCHEMA}.campaigns ADD COLUMN include_staff_notifications BOOLEAN NOT NULL DEFAULT false;"
    )
    op.execute(f"ALTER TABLE {SCHEMA}.messages ADD COLUMN sender_id TEXT;")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.staff_contacts (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            msisdn VARCHAR(12) NOT NULL CHECK ({MSISDN_CHECK}),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (msisdn)
        );
    """)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.staff_contacts;")
    op.execute(f"ALTER TABLE {SCHEMA}.messages DROP COLUMN IF EXISTS sender_id;")
    op.execute(f"ALTER TABLE {SCHEMA}.campaigns DROP COLUMN IF EXISTS include_staff_notifications;")
    op.execute(f"ALTER TABLE {SCHEMA}.campaigns DROP COLUMN IF EXISTS sender_id;")
    op.execute(f"UPDATE {SCHEMA}.channel_configs SET sender_id = '15723' WHERE channel = 'DOCTOR';")
