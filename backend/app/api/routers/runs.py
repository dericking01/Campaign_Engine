from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.campaigns import Campaign, CampaignRun
from app.models.user import User
from app.services.campaign_service import create_run_and_request_audience
from app.services.dispatch_service import pause_run as _pause_run
from app.services.dispatch_service import request_run_start
from app.services.dispatch_service import resume_run as _resume_run
from app.services.dispatch_service import stop_run as _stop_run

router = APIRouter(prefix="/campaign-runs", tags=["campaign-runs"])


class CampaignRunOut(BaseModel):
    id: int
    campaign_id: int
    run_date: date
    status: str
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class CreateRunRequest(BaseModel):
    campaign_id: int
    run_date: date


@router.get(
    "", response_model=list[CampaignRunOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_runs(db: Session = Depends(get_db)) -> list[CampaignRun]:
    return db.query(CampaignRun).order_by(CampaignRun.run_date.desc()).limit(200).all()


@router.get(
    "/{run_id}", response_model=CampaignRunOut, dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def get_run(run_id: int, db: Session = Depends(get_db)) -> CampaignRun:
    run = db.get(CampaignRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign run not found")
    return run


@router.post("", response_model=CampaignRunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    req: CreateRunRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_action(Action.CAMPAIGN_CONFIGURE)),
) -> CampaignRun:
    """Creates the campaign_run and writes the outbox event that triggers
    worker-audience to run the rotation engine - see
    app.services.campaign_service.create_run_and_request_audience. Poll
    GET /campaign-runs/{id} for status (PENDING -> AUDIENCE_GENERATING ->
    READY), then GET /audience/runs/{id}/members for the resulting rows.
    """
    campaign = db.get(Campaign, req.campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    existing = (
        db.query(CampaignRun)
        .filter(CampaignRun.campaign_id == req.campaign_id, CampaignRun.run_date == req.run_date)
        .first()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "a run already exists for this campaign and run_date")
    return create_run_and_request_audience(db, req.campaign_id, req.run_date)


@router.post("/{run_id}/start")
def start_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_START_STOP)),
) -> dict:
    """Validates the run is READY/SCHEDULED and writes the outbox event
    that triggers worker-scheduler to materialize and publish this run's
    dispatch messages (app.services.dispatch_service.queue_run_messages) -
    the heavy lifting happens out-of-process, matching every other
    "trigger async work" endpoint in this API. Poll GET /campaign-runs/{id}
    for status (READY -> RUNNING)."""
    try:
        request_run_start(db, run_id, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"detail": "Run start requested; messages are being queued for dispatch."}


@router.post("/{run_id}/pause")
def pause_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_START_STOP)),
) -> dict:
    """RUNNING -> PAUSED. Dispatch workers check campaign_runs.status as
    part of their claim CAS (see app.services.dispatch_service.
    process_dispatch_message) - a still-QUEUED message for a paused run
    simply isn't claimed; in-flight SUBMITTING messages finish normally.
    No customer state is lost (requirements doc §29)."""
    if not _pause_run(db, run_id, actor_id=current_user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "run is not RUNNING")
    return {"detail": "Run paused."}


@router.post("/{run_id}/resume")
def resume_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_START_STOP)),
) -> dict:
    """PAUSED -> RUNNING, then republishes every still-QUEUED message for
    this run back onto its dispatch topic - continues from exactly where
    it left off, never restarts from zero."""
    published = _resume_run(db, run_id, actor_id=current_user.id)
    if published == 0:
        existing = db.get(CampaignRun, run_id)
        if existing is None or existing.status != "RUNNING":
            raise HTTPException(status.HTTP_409_CONFLICT, "run is not PAUSED")
    return {"detail": f"Run resumed; {published} queued message(s) republished."}


@router.post("/{run_id}/stop")
def stop_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_START_STOP)),
) -> dict:
    """RUNNING/PAUSED -> CANCELLED (terminal). Every not-yet-dispatched
    message (CREATED/QUEUED/RETRYING) is marked CANCELLED; anything already
    SUBMITTING/SENT/DEAD/FAILED_UNCONFIRMED is left as its real outcome."""
    if not _stop_run(db, run_id, actor_id=current_user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "run is not RUNNING or PAUSED")
    return {"detail": "Run stopped."}
