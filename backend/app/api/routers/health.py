from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

router = APIRouter(tags=["system"])
settings = get_settings()


@router.get("/health")
def health() -> dict:
    """Liveness only - no dependency calls. If this doesn't return 200, the
    process itself is wedged and should be restarted."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    """Readiness - checks the dependencies this API actually needs to serve
    traffic correctly. Distinguished from /health per the observability
    requirement: a DB/Kafka/Redis blip should pull this instance out of the
    load balancer without killing/restarting it."""
    checks: dict[str, str] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
        checks["postgres"] = f"error: {exc}"

    try:
        import redis as redis_lib

        client = redis_lib.Redis(
            host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
            socket_connect_timeout=2,
        )
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        from confluent_kafka.admin import AdminClient

        admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
        admin.list_topics(timeout=2)
        checks["kafka"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["kafka"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    body = {"status": "ok" if all_ok else "degraded", "checks": checks}
    return JSONResponse(
        content=body,
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
