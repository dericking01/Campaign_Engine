from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("api.startup", environment=settings.environment)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Control-plane API for the AfyaCall Campaign Engine. "
            "PostgreSQL is the source of truth; Kafka is the durable execution "
            "queue; Redis provides distributed coordination and the global "
            "200 TPS rate limiter; Kannel is a downstream gateway only."
        ),
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
