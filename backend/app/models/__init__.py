"""SQLAlchemy models mirroring the `campaign` schema.

Migration 0001 creates all tables via raw SQL (see migrations/versions) so
that partitioning, partial indexes, and check constraints are expressed
exactly as designed rather than through SQLAlchemy's more limited DDL
support. These models are the ORM-facing mirror used by the application
layer from Phase 2 onward, and must be kept in sync with that migration by
hand. Post-0001 schema changes should use Alembic autogenerate against these
models as normal.
"""

from app.models.analytics import AnalyticsRollup
from app.models.audience import AudienceMember, AudienceSnapshot
from app.models.audit import AuditLog
from app.models.auth import OtpCode, UserSession
from app.models.base import Base
from app.models.bases import BaseMember, BaseVersion, CampaignBase
from app.models.campaigns import (
    Campaign,
    CampaignRun,
    CampaignZoneAllocation,
    CooldownState,
    RotationState,
    Schedule,
)
from app.models.config import ChannelConfig, CustomerProduct, ZoneConfig
from app.models.dnd import DndList, DndRecord
from app.models.events import Event
from app.models.imports import Import, ImportProfile, ImportStagingRow
from app.models.messages import Message, MessageAttempt
from app.models.role import Role, RolePermission
from app.models.staff import StaffContact
from app.models.subscription import CustomerSubscriptionState
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "ZoneConfig",
    "ChannelConfig",
    "CustomerProduct",
    "ImportProfile",
    "Import",
    "ImportStagingRow",
    "CampaignBase",
    "BaseVersion",
    "BaseMember",
    "DndList",
    "DndRecord",
    "CustomerSubscriptionState",
    "Campaign",
    "CampaignRun",
    "CampaignZoneAllocation",
    "Schedule",
    "RotationState",
    "CooldownState",
    "AudienceSnapshot",
    "AudienceMember",
    "Message",
    "MessageAttempt",
    "Event",
    "AuditLog",
    "StaffContact",
    "Role",
    "RolePermission",
    "AnalyticsRollup",
    "OtpCode",
    "UserSession",
]
