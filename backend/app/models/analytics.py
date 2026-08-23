from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalyticsRollup(Base):
    """Cached per-campaign_run analytics - see app.analytics.rollup.
    Computed once when a run naturally completes (app.workers.
    message_events_worker detects every message reaching a terminal
    status) or on-demand via the API for a still-RUNNING/CANCELLED run."""

    __tablename__ = "analytics_rollups"

    campaign_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.campaign_runs.id", ondelete="CASCADE"), primary_key=True
    )
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    core_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chat_engagement: Mapped[dict | None] = mapped_column(JSONB)
    provider_engagement: Mapped[dict | None] = mapped_column(JSONB)
    subscription_conversion: Mapped[dict | None] = mapped_column(JSONB)
