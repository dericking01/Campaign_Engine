from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.config import ChannelConfig, ZoneConfig
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()

# The live-throughput window: recent enough to read as "right now" on a
# dashboard poll, wide enough that a handful of attempts doesn't make the
# rate look noisier than it is.
_RATE_WINDOW_SECONDS = 5


class ZoneConfigOut(BaseModel):
    id: int
    code: str
    label: str
    parent_zone_id: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class ChannelConfigOut(BaseModel):
    channel: str
    sender_id: str
    tps_allocation: int
    is_active: bool

    model_config = {"from_attributes": True}


@router.get(
    "/zones", response_model=list[ZoneConfigOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_zones(db: Session = Depends(get_db)) -> list[ZoneConfig]:
    return db.query(ZoneConfig).order_by(ZoneConfig.code).all()


@router.get(
    "/channels",
    response_model=list[ChannelConfigOut],
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def list_channels(db: Session = Depends(get_db)) -> list[ChannelConfig]:
    return db.query(ChannelConfig).order_by(ChannelConfig.channel).all()


@router.put("/channels/{channel}/tps", dependencies=[Depends(require_action(Action.SYSTEM_CONFIGURE))])
def update_channel_tps() -> dict:
    # Placeholder for Phase 5 (Kafka Execution/Dispatch) - the per-channel TPS
    # sub-allocation under the global 200 ceiling is designed to be editable
    # config, not a code change (see docs/decisions.md).
    return {"detail": "Not implemented yet - Phase 5 (Kafka Execution/Dispatch)."}


class UpdateChannelSenderIdRequest(BaseModel):
    sender_id: str


@router.put("/channels/{channel}/sender-id", response_model=ChannelConfigOut)
def update_channel_sender_id(
    channel: str,
    req: UpdateChannelSenderIdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.SYSTEM_CONFIGURE)),
) -> ChannelConfig:
    """Edits a channel's *default* sender ID (e.g. DOCTOR -> "AFYACALL",
    SMS/IVR -> "15723" out of the box - see migration 0006). Individual
    campaigns can still override this via campaigns.sender_id
    (app.services.dispatch_service.queue_run_messages); this is what a
    campaign falls back to when it doesn't."""
    config = db.get(ChannelConfig, channel)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")

    old_sender_id = config.sender_id
    config.sender_id = req.sender_id.strip()
    db.flush()

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="channel_config.update_sender_id",
        entity_type="channel_config",
        entity_id=channel,
        old_value={"sender_id": old_sender_id},
        new_value={"sender_id": config.sender_id},
    )
    db.commit()
    return config


class ChannelRateOut(BaseModel):
    channel: str
    tps_allocation: int
    current_tps: float


class RateLimitStatusOut(BaseModel):
    global_tps_limit: int
    global_current_tps: float
    channels: list[ChannelRateOut]


@router.get(
    "/rate-limit-status",
    response_model=RateLimitStatusOut,
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def rate_limit_status(db: Session = Depends(get_db)) -> RateLimitStatusOut:
    """Real current throughput, not a static "200 configured" label -
    counts actual dispatch attempts (campaign.message_attempts) in the
    last _RATE_WINDOW_SECONDS, per channel and combined, against the
    real configured ceilings (channel_configs.tps_allocation /
    settings.global_tps_limit) enforced by app.redis.ratelimit's GCRA
    limiter. Idle between campaigns reads 0/200, not an error - there's
    nothing dispatching right now, which is the correct real answer."""
    rows = db.execute(
        text("""
            SELECT m.channel, count(*) AS n
            FROM campaign.message_attempts ma
            JOIN campaign.messages m ON m.campaign_run_id = ma.campaign_run_id AND m.id = ma.message_id
            WHERE ma.attempted_at > now() - make_interval(secs => :window)
            GROUP BY m.channel
        """),
        {"window": _RATE_WINDOW_SECONDS},
    ).all()
    attempts_by_channel = {r.channel: r.n for r in rows}

    channel_configs = {c.channel: c.tps_allocation for c in db.query(ChannelConfig).all()}

    channels = [
        ChannelRateOut(
            channel=channel,
            tps_allocation=tps_allocation,
            current_tps=round(attempts_by_channel.get(channel, 0) / _RATE_WINDOW_SECONDS, 2),
        )
        for channel, tps_allocation in sorted(channel_configs.items())
    ]

    return RateLimitStatusOut(
        global_tps_limit=settings.global_tps_limit,
        global_current_tps=round(sum(attempts_by_channel.values()) / _RATE_WINDOW_SECONDS, 2),
        channels=channels,
    )
