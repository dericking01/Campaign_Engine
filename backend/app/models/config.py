from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ZoneConfig(Base, TimestampMixin):
    """Configurable zones (legacy data shows both TERRITORY and the coarser
    COMMERCIAL_REGION granularity - parent_zone_id lets a zone optionally roll
    up into a broader one without hardcoding a fixed zone list in code."""

    __tablename__ = "zone_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    parent_zone_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.zone_configs.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ChannelConfig(Base, TimestampMixin):
    """One row per logical channel (SMS/IVR/DOCTOR). sender_id and
    tps_allocation are config, not hardcoded strings/constants in dispatch
    code - fixes the legacy inconsistency where drmaster.php used a different
    `from` sender id than smsmaster.php/ivrmaster.php."""

    __tablename__ = "channel_configs"

    channel: Mapped[str] = mapped_column(String, primary_key=True)
    sender_id: Mapped[str] = mapped_column(String, nullable=False)
    tps_allocation: Mapped[int] = mapped_column(Integer, nullable=False)
    default_retry_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class CustomerProduct(Base):
    """Lookup of AfyaCall products a customer may be subscribed to. Extensible
    without a migration - see CustomerSubscriptionState for why this is
    per-product rather than one flat 'is_subscribed' boolean."""

    __tablename__ = "customer_products"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
