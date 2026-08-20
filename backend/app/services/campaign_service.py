"""Campaign creation and audience-generation orchestration - Phase 4.

generate_audience() is the resumable entry point invoked by
worker-audience: iterates the campaign's configured zone allocations,
skipping any zone that already has rows for this campaign_run_id (see
app.rotation.engine's module docstring for why that's a valid and
sufficient resumability check), rotating each remaining zone under the
campaign:lock:rotation:{base_id} distributed lock so two workers can never
race on the same base's rotation_state.
"""

import math
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.bases import BaseVersion
from app.models.campaigns import Campaign, CampaignRun, CampaignZoneAllocation
from app.redis.locks import LockNotAcquired, distributed_lock
from app.rotation.engine import rotate_zone, zone_already_processed

logger = get_logger(component="campaign_service")


def _current_base_version_id(db: Session, base_id: int) -> int:
    version = db.execute(
        text("SELECT id FROM campaign.base_versions WHERE base_id = :base_id AND is_current"),
        {"base_id": base_id},
    ).first()
    if version is None:
        raise ValueError(f"base {base_id} has no current committed version")
    return version.id


def _resolve_zone_quotas(campaign: Campaign, allocations: list[CampaignZoneAllocation]) -> dict[str, int]:
    """PERCENT mode: allocation_value is a percentage of daily_target,
    rounded down except the last zone (by code, for determinism) absorbs
    the rounding remainder so quotas sum to exactly daily_target rather
    than drifting under it. ABSOLUTE mode: allocation_value is already the
    per-zone row count."""
    if campaign.zone_quota_mode == "ABSOLUTE":
        return {a.zone_code: int(a.allocation_value) for a in allocations}

    if not campaign.daily_target:
        raise ValueError("daily_target is required when zone_quota_mode is PERCENT")

    ordered = sorted(allocations, key=lambda a: a.zone_code)
    quotas: dict[str, int] = {}
    running_total = 0
    for i, alloc in enumerate(ordered):
        if i == len(ordered) - 1:
            quotas[alloc.zone_code] = campaign.daily_target - running_total
        else:
            share = math.floor(campaign.daily_target * float(alloc.allocation_value) / 100)
            quotas[alloc.zone_code] = share
            running_total += share
    return quotas


def create_run_and_request_audience(db: Session, campaign_id: int, run_date: date) -> CampaignRun:
    """Creates the campaign_run row and writes the outbox event that
    triggers worker-audience - the API-side half of the flow, mirroring
    how imports request staging."""
    from app.services.outbox import write_event

    campaign_run = CampaignRun(campaign_id=campaign_id, run_date=run_date, status="PENDING")
    db.add(campaign_run)
    db.flush()

    write_event(
        db,
        aggregate_type="campaign_run",
        aggregate_id=str(campaign_run.id),
        event_type="audience.generate_requested",
        payload={"campaign_run_id": campaign_run.id},
        kafka_topic="campaign.audience.events",
        kafka_key=str(campaign_run.id),
    )
    db.commit()
    return campaign_run


def generate_audience(db: Session, campaign_run_id: int) -> None:
    run = db.get(CampaignRun, campaign_run_id)
    if run is None:
        raise ValueError(f"campaign_run {campaign_run_id} not found")
    if run.status not in ("PENDING", "AUDIENCE_GENERATING"):
        logger.info("audience.skip_already_processed", campaign_run_id=campaign_run_id, status=run.status)
        return

    campaign = db.get(Campaign, run.campaign_id)
    if campaign is None:
        raise ValueError(f"campaign {run.campaign_id} not found")

    db.execute(
        text("UPDATE campaign.campaign_runs SET status = 'AUDIENCE_GENERATING', updated_at = now() WHERE id = :id"),
        {"id": campaign_run_id},
    )
    db.commit()

    base_version_id = _current_base_version_id(db, campaign.base_id)

    allocations = (
        db.query(CampaignZoneAllocation).filter(CampaignZoneAllocation.campaign_id == campaign.id).all()
    )
    quotas = _resolve_zone_quotas(campaign, allocations)

    total_selected = 0
    for zone, quota in quotas.items():
        if zone_already_processed(db, campaign_run_id, zone):
            logger.info("audience.zone_already_done", campaign_run_id=campaign_run_id, zone=zone)
            continue
        try:
            with distributed_lock(f"campaign:lock:rotation:{campaign.base_id}", ttl_seconds=600):
                result = rotate_zone(
                    db,
                    campaign_run_id=campaign_run_id,
                    base_id=campaign.base_id,
                    base_version_id=base_version_id,
                    zone=zone,
                    quota=quota,
                    excluded_product_codes=campaign.product_exclusion_codes,
                    cooldown_category=campaign.cooldown_category,
                )
                db.commit()
                total_selected += result.selected
        except LockNotAcquired:
            db.rollback()
            logger.info("audience.rotation_locked_elsewhere", base_id=campaign.base_id, zone=zone)
            raise

    snapshot_exists = db.execute(
        text("SELECT 1 FROM campaign.audience_snapshots WHERE campaign_run_id = :id"),
        {"id": campaign_run_id},
    ).first()
    if snapshot_exists is None:
        totals = db.execute(
            text("""
                SELECT count(*) AS total, count(*) FILTER (WHERE eligible) AS eligible
                FROM campaign.audience_members WHERE campaign_run_id = :id
            """),
            {"id": campaign_run_id},
        ).one()
        db.execute(
            text("""
                INSERT INTO campaign.audience_snapshots
                    (campaign_run_id, base_version_id, dnd_list_id, generated_at,
                     total_candidates, total_eligible, exclusion_breakdown)
                VALUES (:run_id, :base_version_id, :dnd_list_id, :generated_at, :total, :eligible, :breakdown)
            """),
            {
                "run_id": campaign_run_id,
                "base_version_id": base_version_id,
                "dnd_list_id": campaign.dnd_list_id,
                "generated_at": datetime.now(timezone.utc),
                "total": totals.total,
                "eligible": totals.eligible,
                "breakdown": "{}",
            },
        )

    db.execute(
        text("""
            UPDATE campaign.campaign_runs SET
                status = 'READY',
                audience_snapshot_id = (SELECT id FROM campaign.audience_snapshots WHERE campaign_run_id = :id),
                updated_at = now()
            WHERE id = :id
        """),
        {"id": campaign_run_id},
    )
    db.commit()
    logger.info("audience.generated", campaign_run_id=campaign_run_id, total_selected=total_selected)
