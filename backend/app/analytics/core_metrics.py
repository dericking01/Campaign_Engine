"""Core campaign-run metrics - requirements doc §31's "Core metrics" list,
computed as one reusable primitive rather than a one-off report. All
set-based SQL against campaign.messages/audience_members/base_members -
never a per-row Python loop, matching every other analytics-shaped query
in this codebase (see app.audience.eligibility for the same principle).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

TERMINAL_STATUSES = ("SENT", "DEAD", "FAILED_UNCONFIRMED", "CANCELLED")
NON_TERMINAL_STATUSES = ("CREATED", "QUEUED", "SUBMITTING", "RETRYING")


def compute_core_metrics(db: Session, campaign_run_id: int) -> dict:
    run = db.execute(
        text("""
            SELECT r.status, r.started_at, r.completed_at, r.run_date,
                   c.id AS campaign_id, c.name AS campaign_name
            FROM campaign.campaign_runs r JOIN campaign.campaigns c ON c.id = r.campaign_id
            WHERE r.id = :id
        """),
        {"id": campaign_run_id},
    ).one()

    total_audience = db.execute(
        text("SELECT count(*) FROM campaign.audience_members WHERE campaign_run_id = :id AND eligible"),
        {"id": campaign_run_id},
    ).scalar_one()

    status_counts_rows = db.execute(
        text("""
            SELECT status, count(*) AS n, count(DISTINCT customer_msisdn) AS unique_n
            FROM campaign.messages WHERE campaign_run_id = :id GROUP BY status
        """),
        {"id": campaign_run_id},
    ).all()
    status_counts = {r.status: r.n for r in status_counts_rows}
    unique_customers = db.execute(
        text("SELECT count(DISTINCT customer_msisdn) FROM campaign.messages WHERE campaign_run_id = :id"),
        {"id": campaign_run_id},
    ).scalar_one()

    sent = status_counts.get("SENT", 0)
    dead = status_counts.get("DEAD", 0)
    failed_unconfirmed = status_counts.get("FAILED_UNCONFIRMED", 0)
    terminal_attempted = sent + dead + failed_unconfirmed
    success_rate = (sent / terminal_attempted) if terminal_attempted else None

    duration_seconds = None
    actual_tps = None
    if run.started_at:
        end = run.completed_at
        if end is None:
            end = db.execute(text("SELECT now()")).scalar_one()
        duration_seconds = (end - run.started_at).total_seconds()
        if duration_seconds > 0:
            actual_tps = round(sent / duration_seconds, 3)

    zone_breakdown = db.execute(
        text("""
            SELECT am.zone, m.status, count(*) AS n
            FROM campaign.audience_members am
            JOIN campaign.messages m
                ON m.campaign_run_id = am.campaign_run_id AND m.customer_msisdn = am.customer_msisdn
            WHERE am.campaign_run_id = :id AND am.eligible
            GROUP BY am.zone, m.status
        """),
        {"id": campaign_run_id},
    ).all()
    zones: dict[str, dict[str, int]] = {}
    for r in zone_breakdown:
        zones.setdefault(r.zone, {})[r.status] = r.n

    channel_breakdown = db.execute(
        text("""
            SELECT channel, status, count(*) AS n FROM campaign.messages
            WHERE campaign_run_id = :id GROUP BY channel, status
        """),
        {"id": campaign_run_id},
    ).all()
    channels: dict[str, dict[str, int]] = {}
    for r in channel_breakdown:
        channels.setdefault(r.channel, {})[r.status] = r.n

    demographics = _compute_demographic_breakdown(db, campaign_run_id)

    return {
        "campaign_id": run.campaign_id,
        "campaign_name": run.campaign_name,
        "run_status": run.status,
        "run_date": run.run_date.isoformat(),
        "total_audience": total_audience,
        "unique_customers_messaged": unique_customers,
        "status_counts": status_counts,
        "success_rate": success_rate,
        "duration_seconds": duration_seconds,
        "actual_tps": actual_tps,
        "zone_breakdown": zones,
        "channel_breakdown": channels,
        "demographic_breakdown": demographics,
    }


def _compute_demographic_breakdown(db: Session, campaign_run_id: int) -> dict | None:
    base_version_id = db.execute(
        text("""
            SELECT s.base_version_id FROM campaign.campaign_runs r
            JOIN campaign.audience_snapshots s ON s.id = r.audience_snapshot_id
            WHERE r.id = :id
        """),
        {"id": campaign_run_id},
    ).scalar_one_or_none()
    if base_version_id is None:
        return None

    rows = db.execute(
        text("""
            SELECT bm.gender, bm.arpu_segment, m.status, count(*) AS n
            FROM campaign.audience_members am
            JOIN campaign.messages m
                ON m.campaign_run_id = am.campaign_run_id AND m.customer_msisdn = am.customer_msisdn
            JOIN campaign.base_members bm
                ON bm.base_version_id = :bvid AND bm.customer_msisdn = am.customer_msisdn
            WHERE am.campaign_run_id = :id AND am.eligible
            GROUP BY bm.gender, bm.arpu_segment, m.status
        """),
        {"id": campaign_run_id, "bvid": base_version_id},
    ).all()

    by_gender: dict[str, dict[str, int]] = {}
    by_arpu_segment: dict[str, dict[str, int]] = {}
    for r in rows:
        gender = r.gender or "UNKNOWN"
        arpu = r.arpu_segment or "UNKNOWN"
        by_gender.setdefault(gender, {})[r.status] = by_gender.get(gender, {}).get(r.status, 0) + r.n
        by_arpu_segment.setdefault(arpu, {})[r.status] = by_arpu_segment.get(arpu, {}).get(r.status, 0) + r.n

    return {"by_gender": by_gender, "by_arpu_segment": by_arpu_segment}
