from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AudienceSnapshot(Base):
    """The frozen, auditable header for a campaign run's selected audience -
    answers 'exactly which customers were selected and why' even if source
    data changes during a long-running execution."""

    __tablename__ = "audience_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.campaign_runs.id"), unique=True, nullable=False
    )
    base_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.base_versions.id")
    )
    dnd_list_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.dnd_lists.id"))
    generated_at: Mapped[datetime | None]
    total_candidates: Mapped[int | None] = mapped_column(BigInteger)
    total_eligible: Mapped[int | None] = mapped_column(BigInteger)
    exclusion_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AudienceMember(Base):
    """HASH-partitioned by campaign_run_id (32 partitions). Records both
    included AND excluded candidates with a reason, so 'why was customer X
    excluded' is always answerable (requirements doc §16)."""

    __tablename__ = "audience_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_msisdn: Mapped[str] = mapped_column(String(12), nullable=False)
    zone: Mapped[str | None] = mapped_column(String)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String)
    source_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
