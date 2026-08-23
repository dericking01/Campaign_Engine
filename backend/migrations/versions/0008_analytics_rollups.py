"""Analytics rollups - Phase 7.

One row per campaign_run_id, computed by app.analytics.rollup and cached
here rather than recomputed on every dashboard view (a terminal run's
numbers never change again). JSONB sections mirror the reusable primitive
functions that compute them (app.analytics.core_metrics/engagement/
conversion) - not one-off hardcoded report columns, per the requirements
doc's explicit "build reusable analytics primitives, not one-off reports"
instruction.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {SCHEMA}.analytics_rollups (
            campaign_run_id BIGINT PRIMARY KEY REFERENCES {SCHEMA}.campaign_runs(id) ON DELETE CASCADE,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            core_metrics JSONB NOT NULL,
            chat_engagement JSONB,
            provider_engagement JSONB,
            subscription_conversion JSONB
        );
    """)


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.analytics_rollups;")
