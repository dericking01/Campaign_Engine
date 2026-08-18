from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomerSubscriptionState(Base):
    """Campaign-side projection of `subscription.subscribers`, keyed per
    product rather than one flat boolean - the legacy matched_msisdns.py
    script's ad hoc intersection of separate DOCSUB/CHATBOT exclusion files
    is real evidence that 'subscribed to any product' means checking
    membership across multiple distinct product signals. Synced via batch
    COPY+ON CONFLICT today (never per-row remote queries, unlike the legacy
    not_in_base.py pattern); same shape works unchanged if a
    campaign.subscription-events Kafka consumer is added later (source
    just becomes KAFKA_EVENT)."""

    __tablename__ = "customer_subscription_state"

    customer_msisdn: Mapped[str] = mapped_column(String(12), primary_key=True)
    product_code: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.customer_products.code"), primary_key=True
    )
    is_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    source: Mapped[str] = mapped_column(String, nullable=False)
    synced_at: Mapped[datetime]
