from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.bases import CampaignBase
from app.models.campaigns import Campaign, CampaignZoneAllocation
from app.models.dnd import DndList
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

VALID_CHANNELS = {"SMS", "IVR", "DOCTOR"}
VALID_QUOTA_MODES = {"PERCENT", "ABSOLUTE"}


class CampaignOut(BaseModel):
    id: int
    name: str
    channels: list[str]
    status: str
    priority: int
    sender_id: str | None
    include_staff_notifications: bool

    model_config = {"from_attributes": True}


class ZoneAllocationIn(BaseModel):
    zone_code: str
    allocation_value: float


class CreateCampaignRequest(BaseModel):
    name: str
    description: str | None = None
    channels: list[str]
    base_id: int
    zone_allocations: list[ZoneAllocationIn]
    zone_quota_mode: str = "PERCENT"
    daily_target: int | None = None
    product_exclusion_codes: list[str] = []
    dnd_list_id: int | None = None
    cooldown_days: int = 7
    cooldown_category: str | None = None
    message_template: str | None = None
    priority: int = 100
    sender_id: str | None = None
    include_staff_notifications: bool = False

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one channel is required")
        invalid = set(v) - VALID_CHANNELS
        if invalid:
            raise ValueError(f"Invalid channel(s): {invalid}. Must be one of {VALID_CHANNELS}")
        return v

    @field_validator("zone_quota_mode")
    @classmethod
    def validate_quota_mode(cls, v: str) -> str:
        if v not in VALID_QUOTA_MODES:
            raise ValueError(f"zone_quota_mode must be one of {VALID_QUOTA_MODES}")
        return v


@router.get(
    "", response_model=list[CampaignOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_campaigns(db: Session = Depends(get_db)) -> list[Campaign]:
    return db.query(Campaign).order_by(Campaign.created_at.desc()).all()


@router.get(
    "/{campaign_id}",
    response_model=CampaignOut,
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    req: CreateCampaignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_CREATE)),
) -> Campaign:
    """Creates a fully-configured campaign in one call (status=CONFIGURED
    directly) - a simplification from the documented DRAFT->CONFIGURED
    two-step lifecycle, since there's no partial-save UX yet. DRAFT remains
    a valid status for future incremental-save support.
    """
    base = db.get(CampaignBase, req.base_id)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "base not found")
    current_version = db.execute(
        text("SELECT 1 FROM campaign.base_versions WHERE base_id = :id AND is_current"),
        {"id": req.base_id},
    ).first()
    if current_version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "base has no committed current version yet")

    if req.dnd_list_id is not None and db.get(DndList, req.dnd_list_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dnd list not found")

    if not req.zone_allocations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one zone allocation is required")

    known_zones = {
        row[0]
        for row in db.execute(
            text("SELECT code FROM campaign.zone_configs WHERE code = ANY(:codes)"),
            {"codes": [a.zone_code for a in req.zone_allocations]},
        ).all()
    }
    unknown = {a.zone_code for a in req.zone_allocations} - known_zones
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown zone code(s): {unknown}")

    if req.zone_quota_mode == "PERCENT":
        if not req.daily_target or req.daily_target <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "daily_target is required (and > 0) when zone_quota_mode is PERCENT"
            )
        total_pct = sum(a.allocation_value for a in req.zone_allocations)
        if total_pct > 100.0001:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Zone allocation percentages sum to {total_pct}, exceeding 100")

    campaign = Campaign(
        name=req.name,
        description=req.description,
        channels=req.channels,
        base_id=req.base_id,
        product_exclusion_codes=req.product_exclusion_codes,
        dnd_list_id=req.dnd_list_id,
        cooldown_days=req.cooldown_days,
        cooldown_category=req.cooldown_category,
        zone_quota_mode=req.zone_quota_mode,
        daily_target=req.daily_target,
        status="CONFIGURED",
        owner_id=current_user.id,
        message_template=req.message_template,
        priority=req.priority,
        sender_id=req.sender_id,
        include_staff_notifications=req.include_staff_notifications,
    )
    db.add(campaign)
    db.flush()

    for alloc in req.zone_allocations:
        db.add(
            CampaignZoneAllocation(
                campaign_id=campaign.id, zone_code=alloc.zone_code, allocation_value=alloc.allocation_value
            )
        )

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="campaign.create",
        entity_type="campaign",
        entity_id=str(campaign.id),
        new_value={
            "name": campaign.name,
            "channels": campaign.channels,
            "base_id": campaign.base_id,
            "sender_id": campaign.sender_id,
            "include_staff_notifications": campaign.include_staff_notifications,
        },
    )
    db.commit()
    return campaign
