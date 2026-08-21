"""Message queuing, dispatch, and run lifecycle orchestration - Phase 5.

Mirrors the split established in app.services.campaign_service: the API
only validates and writes an outbox event (fast, synchronous); the actual
work (materializing potentially millions of `messages` rows and publishing
one dispatch command per message) runs out-of-process in worker-scheduler,
which calls queue_run_messages() below.

Resumability: materializing is `INSERT ... ON CONFLICT DO NOTHING`
(safe to re-run), and publishing is "re-select everything still QUEUED and
publish it" (also safe to re-run - a message only leaves QUEUED once a
dispatcher's CAS claims it as SUBMITTING, so a message already claimed by
the time a redelivery/resume re-runs the publish loop simply won't be
selected again). The same _publish_queued_messages() helper backs both the
initial queue and campaign-runs/{id}/resume, since "republish everything
still QUEUED" is exactly what resuming a paused run needs too.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.gateways import kannel
from app.kafka.producer import publish_batch
from app.models.campaigns import Campaign, CampaignRun
from app.redis.ratelimit import acquire_blocking
from app.services.audit import write_audit_log
from app.services.outbox import write_event

logger = get_logger(component="dispatch_service")

PUBLISH_BATCH_SIZE = 2000
DEFAULT_MAX_ATTEMPTS = 5
RUNNABLE_STATUSES = {"READY", "SCHEDULED"}
CANCELLABLE_MESSAGE_STATUSES = ("CREATED", "QUEUED", "RETRYING")


def _dispatch_topic(channel: str) -> str:
    return f"campaign.dispatch.{channel.lower()}"


def request_run_start(db: Session, campaign_run_id: int, actor_id: int | None = None) -> CampaignRun:
    run = db.get(CampaignRun, campaign_run_id)
    if run is None:
        raise ValueError(f"campaign_run {campaign_run_id} not found")
    if run.status not in RUNNABLE_STATUSES:
        raise ValueError(f"campaign_run {campaign_run_id} is '{run.status}', not ready to start")

    write_event(
        db,
        aggregate_type="campaign_run",
        aggregate_id=str(campaign_run_id),
        event_type="run.start_requested",
        payload={"campaign_run_id": campaign_run_id},
        kafka_topic="campaign.audience.events",
        kafka_key=str(campaign_run_id),
    )
    write_audit_log(
        db, actor_id=actor_id, action="campaign_run.start", entity_type="campaign_run", entity_id=str(campaign_run_id)
    )
    db.commit()
    return run


def _publish_queued_messages(db: Session, campaign_run_id: int) -> int:
    total = 0
    last_id = 0
    while True:
        rows = db.execute(
            text("""
                SELECT id, customer_msisdn, channel, message_body, sender_id FROM campaign.messages
                WHERE campaign_run_id = :run_id AND status = 'QUEUED' AND id > :last_id
                ORDER BY id
                LIMIT :limit
            """),
            {"run_id": campaign_run_id, "last_id": last_id, "limit": PUBLISH_BATCH_SIZE},
        ).all()
        if not rows:
            break

        records = [
            (
                _dispatch_topic(r.channel),
                r.customer_msisdn,
                {
                    "message_id": r.id,
                    "campaign_run_id": campaign_run_id,
                    "customer_msisdn": r.customer_msisdn,
                    "channel": r.channel,
                    "text": r.message_body,
                    "sender_id": r.sender_id,
                },
            )
            for r in rows
        ]
        publish_batch(records)
        total += len(rows)
        last_id = rows[-1].id

    return total


def queue_run_messages(db: Session, campaign_run_id: int) -> int:
    """Materializes messages for a READY/SCHEDULED run and publishes them
    to their channel dispatch topics. Safe to re-run (see module
    docstring) - the entry point invoked by worker-scheduler on
    'run.start_requested'."""
    run = db.get(CampaignRun, campaign_run_id)
    if run is None:
        raise ValueError(f"campaign_run {campaign_run_id} not found")
    if run.status == "RUNNING":
        logger.info("dispatch.run_already_running", campaign_run_id=campaign_run_id)
        return _publish_queued_messages(db, campaign_run_id)
    if run.status not in RUNNABLE_STATUSES:
        logger.info("dispatch.skip_not_runnable", campaign_run_id=campaign_run_id, status=run.status)
        return 0

    campaign = db.get(Campaign, run.campaign_id)
    if campaign is None:
        raise ValueError(f"campaign {run.campaign_id} not found")

    # sender_id resolution: campaigns.sender_id overrides every channel's
    # default when set; otherwise each row falls back to that channel's own
    # channel_configs.sender_id (e.g. DOCTOR -> "AFYACALL", SMS/IVR ->
    # "15723" - see migration 0006). Resolved once here, at materialize
    # time, and carried on the row itself so the dispatch/retry hot path
    # never needs to look it up again.
    db.execute(
        text("""
            INSERT INTO campaign.messages
                (campaign_run_id, customer_msisdn, channel, status, message_body, sender_id)
            SELECT :run_id, am.customer_msisdn, ch.channel, 'CREATED', :message_body,
                   COALESCE(:sender_id_override, cc.sender_id)
            FROM campaign.audience_members am
            CROSS JOIN unnest(:channels) AS ch(channel)
            JOIN campaign.channel_configs cc ON cc.channel = ch.channel
            WHERE am.campaign_run_id = :run_id AND am.eligible
            ON CONFLICT (campaign_run_id, customer_msisdn, channel) DO NOTHING
        """),
        {
            "run_id": campaign_run_id,
            "message_body": campaign.message_template,
            "channels": campaign.channels,
            "sender_id_override": campaign.sender_id,
        },
    )

    if campaign.include_staff_notifications:
        # Compliance requirement: every active staff_contacts row receives
        # every message a running campaign sends. Snapshotted from the
        # roster as plain msisdn/name data (no FK - see app.models.staff),
        # exactly like audience_members already stores customer_msisdn
        # directly rather than referencing a customers table. A staff
        # member who is also in the real audience naturally dedupes via
        # the same (campaign_run_id, customer_msisdn, channel) uniqueness
        # constraint (ON CONFLICT DO NOTHING) - never a duplicate send.
        db.execute(
            text("""
                INSERT INTO campaign.messages
                    (campaign_run_id, customer_msisdn, channel, status, message_body, sender_id)
                SELECT :run_id, sc.msisdn, ch.channel, 'CREATED', :message_body,
                       COALESCE(:sender_id_override, cc.sender_id)
                FROM campaign.staff_contacts sc
                CROSS JOIN unnest(:channels) AS ch(channel)
                JOIN campaign.channel_configs cc ON cc.channel = ch.channel
                WHERE sc.is_active
                ON CONFLICT (campaign_run_id, customer_msisdn, channel) DO NOTHING
            """),
            {
                "run_id": campaign_run_id,
                "message_body": campaign.message_template,
                "channels": campaign.channels,
                "sender_id_override": campaign.sender_id,
            },
        )

    db.execute(
        text("""
            UPDATE campaign.messages SET status = 'QUEUED', updated_at = now()
            WHERE campaign_run_id = :run_id AND status = 'CREATED'
        """),
        {"run_id": campaign_run_id},
    )
    db.execute(
        text("""
            UPDATE campaign.campaign_runs
            SET status = 'RUNNING', started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE id = :run_id
        """),
        {"run_id": campaign_run_id},
    )
    db.commit()

    published = _publish_queued_messages(db, campaign_run_id)
    logger.info("dispatch.run_queued", campaign_run_id=campaign_run_id, published=published)
    return published


def pause_run(db: Session, campaign_run_id: int, actor_id: int | None = None) -> bool:
    result = db.execute(
        text("""
            UPDATE campaign.campaign_runs SET status = 'PAUSED', paused_at = now(), updated_at = now()
            WHERE id = :id AND status = 'RUNNING'
        """),
        {"id": campaign_run_id},
    )
    if result.rowcount > 0:
        write_audit_log(
            db, actor_id=actor_id, action="campaign_run.pause", entity_type="campaign_run", entity_id=str(campaign_run_id)
        )
    db.commit()
    return result.rowcount > 0


def resume_run(db: Session, campaign_run_id: int, actor_id: int | None = None) -> int:
    result = db.execute(
        text("""
            UPDATE campaign.campaign_runs SET status = 'RUNNING', updated_at = now()
            WHERE id = :id AND status = 'PAUSED'
        """),
        {"id": campaign_run_id},
    )
    if result.rowcount == 0:
        db.commit()
        return 0

    published = _publish_queued_messages(db, campaign_run_id)
    write_audit_log(
        db,
        actor_id=actor_id,
        action="campaign_run.resume",
        entity_type="campaign_run",
        entity_id=str(campaign_run_id),
        new_value={"republished": published},
    )
    db.commit()
    return published


def stop_run(db: Session, campaign_run_id: int, actor_id: int | None = None) -> bool:
    result = db.execute(
        text("""
            UPDATE campaign.campaign_runs SET status = 'CANCELLED', completed_at = now(), updated_at = now()
            WHERE id = :id AND status IN ('RUNNING', 'PAUSED')
        """),
        {"id": campaign_run_id},
    )
    if result.rowcount > 0:
        db.execute(
            text("""
                UPDATE campaign.messages SET status = 'CANCELLED', updated_at = now()
                WHERE campaign_run_id = :id AND status = ANY(:statuses)
            """),
            {"id": campaign_run_id, "statuses": list(CANCELLABLE_MESSAGE_STATUSES)},
        )
        write_audit_log(
            db, actor_id=actor_id, action="campaign_run.stop", entity_type="campaign_run", entity_id=str(campaign_run_id)
        )
    db.commit()
    return result.rowcount > 0


NON_TERMINAL_MESSAGE_STATUSES = ("CREATED", "QUEUED", "SUBMITTING", "RETRYING")


def check_and_complete_run(db: Session, campaign_run_id: int) -> bool:
    """Called by worker-message-events after every terminal message
    outcome (see app.workers.message_events_worker) - RUNNING -> COMPLETED
    once every message for the run has reached a terminal status
    (SENT/DEAD/FAILED_UNCONFIRMED/CANCELLED). Idempotent: the CAS's
    `AND status = 'RUNNING'` means a redelivered/duplicate check is a
    harmless no-op once the run has already completed. Cheap even at
    scale - ix_messages_run_status makes this a single-partition indexed
    lookup, not a table scan (messages is HASH-partitioned by
    campaign_run_id).
    """
    still_pending = db.execute(
        text("""
            SELECT count(*) FROM campaign.messages
            WHERE campaign_run_id = :id AND status = ANY(:statuses)
        """),
        {"id": campaign_run_id, "statuses": list(NON_TERMINAL_MESSAGE_STATUSES)},
    ).scalar_one()
    if still_pending > 0:
        return False

    result = db.execute(
        text("""
            UPDATE campaign.campaign_runs SET status = 'COMPLETED', completed_at = now(), updated_at = now()
            WHERE id = :id AND status = 'RUNNING'
        """),
        {"id": campaign_run_id},
    )
    if result.rowcount > 0:
        write_event(
            db,
            aggregate_type="campaign_run",
            aggregate_id=str(campaign_run_id),
            event_type="run.completed",
            payload={"campaign_run_id": campaign_run_id},
            kafka_topic="campaign.analytics.events",
            kafka_key=str(campaign_run_id),
        )
    db.commit()
    return result.rowcount > 0


def _retry_backoff(attempt_count: int) -> datetime:
    seconds = min(30 * (2 ** max(attempt_count - 1, 0)), 300)
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _max_attempts(db: Session, channel: str) -> int:
    row = db.execute(
        text("SELECT default_retry_policy FROM campaign.channel_configs WHERE channel = :c"), {"c": channel}
    ).first()
    if row and row.default_retry_policy:
        return int(row.default_retry_policy.get("max_attempts", DEFAULT_MAX_ATTEMPTS))
    return DEFAULT_MAX_ATTEMPTS


def process_dispatch_message(
    db: Session,
    *,
    message_id: int,
    campaign_run_id: int,
    channel: str,
    text_body: str | None,
    sender_id: str,
) -> str | None:
    """Called by a dispatch worker for one consumed Kafka dispatch command.
    Returns the resulting message status, or None if this delivery was a
    no-op (already handled, or the run isn't RUNNING - e.g. paused/
    cancelled between publish and consume)."""
    if not acquire_blocking(channel, max_wait_seconds=5.0):
        # Ceiling saturated and no slot opened in time - leave the message
        # QUEUED and do not commit the Kafka offset, so this exact
        # delivery is retried on the next poll (same at-least-once +
        # don't-commit-until-done pattern used throughout this codebase).
        raise TimeoutError(f"no rate-limit slot available for channel {channel}")

    claimed = db.execute(
        text("""
            UPDATE campaign.messages m
            SET status = 'SUBMITTING', attempt_count = attempt_count + 1, updated_at = now()
            FROM campaign.campaign_runs r
            WHERE m.id = :mid AND m.campaign_run_id = :rid
              AND r.id = m.campaign_run_id
              AND m.status = 'QUEUED' AND r.status = 'RUNNING'
            RETURNING m.customer_msisdn, m.attempt_count
        """),
        {"mid": message_id, "rid": campaign_run_id},
    ).first()
    if claimed is None:
        logger.info("dispatch.claim_skipped", message_id=message_id, campaign_run_id=campaign_run_id)
        db.commit()
        return None

    result = kannel.send(to_msisdn=claimed.customer_msisdn, text=text_body or "", sender_id=sender_id)

    # message_attempts.outcome is a coarse 3-way audit signal (SENT/FAILED/
    # AMBIGUOUS per the schema's CHECK constraint) - the finer-grained
    # DispatchOutcome (which distinguishes permanent vs. transient failure
    # for retry purposes) drives messages.status below instead.
    attempt_outcome = {
        kannel.DispatchOutcome.SENT: "SENT",
        kannel.DispatchOutcome.FAILED_PERMANENT: "FAILED",
        kannel.DispatchOutcome.FAILED_TRANSIENT: "FAILED",
        kannel.DispatchOutcome.FAILED_UNCONFIRMED: "AMBIGUOUS",
    }[result.outcome]

    db.execute(
        text("""
            INSERT INTO campaign.message_attempts
                (campaign_run_id, message_id, attempt_number, kannel_port, http_status,
                 kannel_response_body, outcome)
            VALUES (:rid, :mid, :attempt, :port, :http_status, :body, :outcome)
        """),
        {
            "rid": campaign_run_id,
            "mid": message_id,
            "attempt": claimed.attempt_count,
            "port": result.kannel_port,
            "http_status": result.http_status,
            "body": result.response_body,
            "outcome": attempt_outcome,
        },
    )

    if result.outcome == kannel.DispatchOutcome.SENT:
        new_status, next_attempt_at = "SENT", None
    elif result.outcome == kannel.DispatchOutcome.FAILED_PERMANENT:
        new_status, next_attempt_at = "DEAD", None
    elif result.outcome == kannel.DispatchOutcome.FAILED_TRANSIENT:
        if claimed.attempt_count >= _max_attempts(db, channel):
            new_status, next_attempt_at = "DEAD", None
        else:
            new_status, next_attempt_at = "RETRYING", _retry_backoff(claimed.attempt_count)
    else:
        new_status, next_attempt_at = "FAILED_UNCONFIRMED", None

    db.execute(
        text("""
            UPDATE campaign.messages SET status = :status, next_attempt_at = :next_attempt_at, updated_at = now()
            WHERE id = :id AND campaign_run_id = :rid
        """),
        {"status": new_status, "next_attempt_at": next_attempt_at, "id": message_id, "rid": campaign_run_id},
    )

    write_event(
        db,
        aggregate_type="message",
        aggregate_id=str(message_id),
        event_type="message.attempt_outcome",
        payload={
            "message_id": message_id,
            "campaign_run_id": campaign_run_id,
            "customer_msisdn": claimed.customer_msisdn,
            "channel": channel,
            "status": new_status,
            "outcome": result.outcome.value,
            "attempt_count": claimed.attempt_count,
        },
        kafka_topic="campaign.message-events",
        kafka_key=str(message_id),
    )

    if new_status == "DEAD":
        write_event(
            db,
            aggregate_type="message",
            aggregate_id=str(message_id),
            event_type="message.dead_lettered",
            payload={
                "message_id": message_id,
                "campaign_run_id": campaign_run_id,
                "customer_msisdn": claimed.customer_msisdn,
                "channel": channel,
                "final_outcome": result.outcome.value,
            },
            kafka_topic=f"{_dispatch_topic(channel)}.dlq",
            kafka_key=claimed.customer_msisdn,
        )

    db.commit()
    return new_status
