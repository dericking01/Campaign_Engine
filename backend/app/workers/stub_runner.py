"""Shared worker entrypoint: dispatches to the real per-worker-type module
where one now exists (ingestion, outbox-relay as of Phase 2; audience as of
Phase 4; scheduler/dispatch-*/retry-scheduler as of Phase 5;
message-events/analytics as of Phase 7), and falls back to a
heartbeat-only stub loop for worker types not yet implemented (rotation -
see the note below for why that one stays a stub on purpose). Proves each
container starts cleanly, can reach Postgres, and heartbeats into Redis -
see docs/architecture.md "Docker / Networking" health-check design.
"""

import os
import sys
import time

import redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.environment)

WORKER_TYPE = os.environ.get("WORKER_TYPE", "unknown")
logger = get_logger(component="worker", worker_type=WORKER_TYPE)

_REAL_WORKER_ENTRYPOINTS = {
    "ingestion": "app.workers.ingestion_worker",
    "outbox-relay": "app.workers.outbox_relay_worker",
    # Rotation is folded into the audience worker rather than split into a
    # separate process: selecting a zone's slice and advancing its
    # rotation_state cursor are one atomic transaction (see
    # app.rotation.engine), so a standalone "rotation worker" would need
    # complex cross-process coordination for what is fundamentally a single
    # step. worker-rotation stays a stub for now - a candidate future role
    # is scheduling *which* runs are due, not performing rotation itself.
    "audience": "app.workers.audience_worker",
    # Materializes + publishes a run's dispatch commands on
    # 'run.start_requested' (app.services.dispatch_service.queue_run_messages) -
    # see docs/architecture.md Phase 5.
    "scheduler": "app.workers.scheduler_worker",
    # One process per channel; app.workers.dispatch_worker derives which
    # channel/topic from WORKER_TYPE's "dispatch-" suffix.
    "dispatch-sms": "app.workers.dispatch_worker",
    "dispatch-ivr": "app.workers.dispatch_worker",
    "dispatch-doctor": "app.workers.dispatch_worker",
    "retry-scheduler": "app.workers.retry_scheduler_worker",
    # Detects run completion (RUNNING -> COMPLETED) and triggers the
    # analytics rollup - see app.workers.message_events_worker.
    "message-events": "app.workers.message_events_worker",
    # Computes + caches each completed run's analytics rollup - see
    # app.workers.analytics_worker / app.analytics.rollup.
    "analytics": "app.workers.analytics_worker",
}


def main() -> None:
    if WORKER_TYPE in _REAL_WORKER_ENTRYPOINTS:
        import importlib

        module = importlib.import_module(_REAL_WORKER_ENTRYPOINTS[WORKER_TYPE])
        module.run()
        return

    logger.info("worker.stub_start")

    from app.core.db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("worker.postgres_check", status="ok")
    except Exception:
        logger.exception("worker.postgres_check_failed")
        sys.exit(1)

    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)
    heartbeat_key = f"worker:heartbeat:{WORKER_TYPE}"

    while True:
        r.set(heartbeat_key, str(int(time.time())), ex=60)
        logger.info("worker.heartbeat")
        time.sleep(15)


if __name__ == "__main__":
    main()
