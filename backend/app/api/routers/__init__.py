from fastapi import APIRouter

from app.api.routers import (
    analytics,
    audience,
    audit,
    auth,
    bases,
    campaigns,
    dnd,
    health,
    imports,
    messages,
    roles,
    runs,
    staff,
    subscriptions,
    system,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(imports.router)
api_router.include_router(bases.router)
api_router.include_router(dnd.router)
api_router.include_router(subscriptions.router)
api_router.include_router(campaigns.router)
api_router.include_router(runs.router)
api_router.include_router(audience.router)
api_router.include_router(messages.router)
api_router.include_router(analytics.router)
api_router.include_router(audit.router)
api_router.include_router(system.router)
api_router.include_router(staff.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
