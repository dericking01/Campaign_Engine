from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CampaignBase(Base, TimestampMixin):
    """A logical imported customer population (e.g. 'National Base',
    'DOCSUB Prospects'). Named CampaignBase in code to avoid clashing with
    SQLAlchemy's own declarative Base; the table itself is `campaign.bases`."""

    __tablename__ = "bases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class BaseVersion(Base):
    """Immutable snapshot created each time an import commits into a base.
    Exactly one row per base has is_current = true (enforced by a partial
    unique index in the migration, not representable in the ORM mapping)."""

    __tablename__ = "base_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaign.bases.id"), nullable=False)
    source_import_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.imports.id")
    )
    member_count: Mapped[int | None] = mapped_column(BigInteger)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    committed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BaseMember(Base):
    """HASH-partitioned by base_version_id (32 partitions, created in the
    migration) - the promoted columns below cover current filtering needs;
    source_snapshot retains everything else legacy bases carry
    (SUB_TYPE/ARPU_SEGMENT/SMARTPHONE_USER/etc.) for future targeting/AI use
    without a schema migration. See docs/architecture.md for the partitioning
    rationale."""

    __tablename__ = "base_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    base_version_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_msisdn: Mapped[str] = mapped_column(String(12), nullable=False)
    territory: Mapped[str | None] = mapped_column(String)
    commercial_region: Mapped[str | None] = mapped_column(String)
    gender: Mapped[str | None] = mapped_column(String)
    age: Mapped[int | None] = mapped_column(Integer)
    arpu_segment: Mapped[str | None] = mapped_column(String)
    source_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
