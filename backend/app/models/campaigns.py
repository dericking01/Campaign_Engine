from datetime import date, datetime

from sqlalchemy import ARRAY, BigInteger, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default="{}")
    base_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaign.bases.id"), nullable=False)
    product_exclusion_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    dnd_list_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.dnd_lists.id"))
    cooldown_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="7")
    cooldown_category: Mapped[str | None] = mapped_column(String)
    zone_quota_mode: Mapped[str] = mapped_column(String, nullable=False, server_default="PERCENT")
    daily_target: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="DRAFT")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.users.id"))
    message_template: Mapped[str | None] = mapped_column(String)
    execution_window: Mapped[dict | None] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    sender_id: Mapped[str | None] = mapped_column(String)
    """Overrides every dispatched channel's sender ID for this campaign
    when set; falls back to channel_configs.sender_id per-channel when
    null (see app.services.dispatch_service.queue_run_messages)."""
    include_staff_notifications: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    """When true, every active app.models.staff.StaffContact is snapshotted
    into this run's messages alongside the real audience, for compliance
    (staff must receive every campaign message a running campaign sends)."""


class CampaignZoneAllocation(Base):
    """Per-campaign zone quota - a percentage of daily_target when
    campaigns.zone_quota_mode='PERCENT', or an absolute per-zone count when
    'ABSOLUTE'. Resolved to concrete row counts by the rotation engine
    (app.rotation.engine) at audience-generation time."""

    __tablename__ = "campaign_zone_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.campaigns.id", ondelete="CASCADE"), nullable=False
    )
    zone_code: Mapped[str] = mapped_column(String, ForeignKey("campaign.zone_configs.code"), nullable=False)
    allocation_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CampaignRun(Base, TimestampMixin):
    __tablename__ = "campaign_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.campaigns.id"), nullable=False
    )
    run_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="PENDING")
    audience_snapshot_id: Mapped[int | None] = mapped_column(BigInteger)
    scheduled_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    paused_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    stats: Mapped[dict | None] = mapped_column(JSONB)


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.campaigns.id"), nullable=False
    )
    schedule_type: Mapped[str] = mapped_column(String, nullable=False)
    cron_expr: Mapped[str | None] = mapped_column(String)
    run_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")


class RotationState(Base):
    """The authoritative resumable rotation cursor (see docs/architecture.md
    §5) - Redis only guards concurrent access to this, never substitutes
    for it. Replaces the legacy extract_msisdns.php pattern of an operator
    hand-editing a start-line constant each day."""

    __tablename__ = "rotation_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaign.bases.id"), nullable=False)
    zone: Mapped[str] = mapped_column(String, nullable=False)
    last_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    total_eligible_at_cycle_start: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CooldownState(Base):
    __tablename__ = "cooldown_state"

    customer_msisdn: Mapped[str] = mapped_column(String(12), primary_key=True)
    campaign_category: Mapped[str] = mapped_column(String, primary_key=True)
    cooldown_until: Mapped[datetime] = mapped_column(nullable=False)
