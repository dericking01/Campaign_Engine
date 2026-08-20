"""Add campaign.campaign_zone_allocations - per-campaign zone quotas.

Was in the original ERD design ("zone_allocations - Per-zone percentage or
absolute target configuration") but not created in 0001. Needed now for
Phase 4's rotation engine: interpreted as a percentage of daily_target when
campaigns.zone_quota_mode='PERCENT', or an absolute per-zone count when
'ABSOLUTE'.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {SCHEMA}.campaign_zone_allocations (
            id BIGSERIAL PRIMARY KEY,
            campaign_id BIGINT NOT NULL REFERENCES {SCHEMA}.campaigns(id) ON DELETE CASCADE,
            zone_code TEXT NOT NULL REFERENCES {SCHEMA}.zone_configs(code),
            allocation_value NUMERIC NOT NULL CHECK (allocation_value >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (campaign_id, zone_code)
        );
    """)
    op.execute(
        f"CREATE INDEX ix_campaign_zone_allocations_campaign "
        f"ON {SCHEMA}.campaign_zone_allocations (campaign_id);"
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.campaign_zone_allocations;")
