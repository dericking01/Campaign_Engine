"""The rotation engine: turns a campaign's configured zone quotas into an
actual, persisted audience for one campaign_run. Replaces the legacy
extract_msisdns.php pattern (an operator hand-editing a $start/$limit line
constant each day) with a resumable, crash-safe database transaction per
zone.

Design note - simplified from the original two-step sketch in
docs/architecture.md §5 (compute a base-wide eligibility snapshot once,
then slice it across runs): here eligibility is recomputed directly from
base_members + DND/subscription/cooldown on every call, scoped to one zone
at a time. This trades a bit of redundant computation (the anti-join runs
once per zone instead of once per base) for a much simpler mental model,
and is still fast in practice - the full-base version of this same
anti-join was verified live at 18.5s for a 16.9M-row base (see
docs/decisions.md); one zone's slice of that is proportionally cheaper.

Resumability: each zone's slice is exactly one transaction (rank+slice,
INSERT into audience_members, advance rotation_state). A crash before
COMMIT leaves nothing behind - Postgres rolls the whole thing back - so a
retry naturally resumes from the last *committed* rotation_state.
last_offset. Idempotency across a full retry of the run is handled one
level up (app.services.campaign_service): a zone already having rows in
audience_members for this campaign_run_id is skipped, since a zone's
insert only ever happens as part of that same atomic transaction as its
rotation_state advance - there is no possible partial state to clean up.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger(component="rotation_engine")


@dataclass(frozen=True, slots=True)
class ZoneRotationResult:
    zone: str
    selected: int
    total_eligible_in_zone: int
    last_offset: int
    cycle_number: int
    wrapped: bool


def zone_already_processed(db: Session, campaign_run_id: int, zone: str) -> bool:
    count = db.execute(
        text("""
            SELECT count(*) FROM campaign.audience_members
            WHERE campaign_run_id = :run_id AND zone = :zone
        """),
        {"run_id": campaign_run_id, "zone": zone},
    ).scalar_one()
    return count > 0


def rotate_zone(
    db: Session,
    *,
    campaign_run_id: int,
    base_id: int,
    base_version_id: int,
    zone: str,
    quota: int,
    excluded_product_codes: list[str],
    cooldown_category: str | None,
) -> ZoneRotationResult:
    """Selects the next `quota`-sized, not-yet-used slice of this zone's
    eligible pool into audience_members for campaign_run_id, and advances
    rotation_state - all in the caller's current transaction (commit is the
    caller's responsibility, matching every other service function in this
    codebase, so this composes cleanly with the distributed lock in
    app.services.campaign_service).
    """
    row = db.execute(
        text("""
            INSERT INTO campaign.rotation_state (base_id, zone, last_offset, cycle_number)
            VALUES (:base_id, :zone, 0, 1)
            ON CONFLICT (base_id, zone) DO NOTHING
            RETURNING last_offset, cycle_number
        """),
        {"base_id": base_id, "zone": zone},
    ).first()
    if row is None:
        row = db.execute(
            text("""
                SELECT last_offset, cycle_number FROM campaign.rotation_state
                WHERE base_id = :base_id AND zone = :zone
                FOR UPDATE
            """),
            {"base_id": base_id, "zone": zone},
        ).one()
    last_offset, cycle_number = row.last_offset, row.cycle_number

    eligible_cte = """
        WITH eligible AS (
            SELECT bm.customer_msisdn
            FROM campaign.base_members bm
            LEFT JOIN campaign.dnd_records dnd
                   ON dnd.customer_msisdn = bm.customer_msisdn AND dnd.is_active
            LEFT JOIN (
                SELECT DISTINCT customer_msisdn FROM campaign.customer_subscription_state
                WHERE is_subscribed AND product_code = ANY(:excluded_product_codes)
            ) sub ON sub.customer_msisdn = bm.customer_msisdn
            LEFT JOIN campaign.cooldown_state cd
                   ON cd.customer_msisdn = bm.customer_msisdn
                  AND cd.campaign_category = :cooldown_category
                  AND cd.cooldown_until > now()
            WHERE bm.base_version_id = :base_version_id
              AND bm.territory = :zone
              AND dnd.customer_msisdn IS NULL
              AND sub.customer_msisdn IS NULL
              AND cd.customer_msisdn IS NULL
        ),
        ranked AS (
            SELECT customer_msisdn, row_number() OVER (ORDER BY customer_msisdn) AS rn
            FROM eligible
        )
    """
    params = {
        "base_version_id": base_version_id,
        "zone": zone,
        "excluded_product_codes": excluded_product_codes,
        "cooldown_category": cooldown_category,
    }

    total_eligible = db.execute(
        text(f"{eligible_cte} SELECT count(*) FROM ranked"), params
    ).scalar_one()

    wrapped = False
    effective_offset = last_offset
    if effective_offset >= total_eligible:
        # This zone's pool was fully consumed by a prior cycle - wrap and
        # start the new cycle's slice from the top.
        effective_offset = 0
        cycle_number += 1
        wrapped = True

    inserted = db.execute(
        text(f"""
            {eligible_cte}
            INSERT INTO campaign.audience_members (campaign_run_id, customer_msisdn, zone, eligible)
            SELECT :campaign_run_id, customer_msisdn, :zone, true
            FROM ranked
            WHERE rn > :offset AND rn <= :offset + :quota
            ON CONFLICT (campaign_run_id, customer_msisdn) DO NOTHING
        """),
        {**params, "campaign_run_id": campaign_run_id, "offset": effective_offset, "quota": quota},
    ).rowcount

    new_offset = min(effective_offset + quota, total_eligible)
    db.execute(
        text("""
            UPDATE campaign.rotation_state
            SET last_offset = :offset, cycle_number = :cycle,
                total_eligible_at_cycle_start = :total, updated_at = now()
            WHERE base_id = :base_id AND zone = :zone
        """),
        {
            "offset": new_offset,
            "cycle": cycle_number,
            "total": total_eligible,
            "base_id": base_id,
            "zone": zone,
        },
    )

    logger.info(
        "rotation.zone_rotated",
        campaign_run_id=campaign_run_id,
        zone=zone,
        selected=inserted,
        total_eligible_in_zone=total_eligible,
        new_offset=new_offset,
        cycle_number=cycle_number,
        wrapped=wrapped,
    )

    return ZoneRotationResult(
        zone=zone,
        selected=inserted,
        total_eligible_in_zone=total_eligible,
        last_offset=new_offset,
        cycle_number=cycle_number,
        wrapped=wrapped,
    )
