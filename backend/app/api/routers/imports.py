import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.bases import CampaignBase
from app.models.imports import Import
from app.models.user import User
from app.services.audit import write_audit_log
from app.services.outbox import write_event

router = APIRouter(prefix="/imports", tags=["imports"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".csv", ".txt"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # matches nginx client_max_body_size
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
IMPORT_KINDS = {"BASE", "DND"}


class ImportOut(BaseModel):
    id: int
    source_type: str
    import_kind: str
    original_filename: str | None
    status: str
    total_rows: int | None
    valid_rows: int | None
    invalid_rows: int | None
    duplicate_rows: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportPreviewOut(BaseModel):
    id: int
    import_kind: str
    status: str
    total_rows: int | None
    valid_rows: int | None
    invalid_rows: int | None
    duplicate_rows: int | None
    zone_distribution: dict | None
    sample_rows: dict | None
    error_summary: dict | None


class DropFileOut(BaseModel):
    filename: str
    size_bytes: int
    modified_at: datetime
    detected_format: str


class CreateFromDropRequest(BaseModel):
    filename: str
    import_profile_id: int | None = None
    import_kind: str = "BASE"


class ApproveImportRequest(BaseModel):
    base_id: int | None = None
    new_base_name: str | None = None
    dnd_list_name: str | None = None


@router.get(
    "", response_model=list[ImportOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_imports(db: Session = Depends(get_db)) -> list[Import]:
    return db.query(Import).order_by(Import.created_at.desc()).limit(100).all()


@router.get(
    "/{import_id}/preview",
    response_model=ImportPreviewOut,
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def preview_import(import_id: int, db: Session = Depends(get_db)) -> Import:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import not found")
    return imp


@router.post("/upload", response_model=ImportOut, status_code=status.HTTP_202_ACCEPTED)
def upload_import(
    file: UploadFile,
    import_kind: str = Form("BASE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_CREATE)),
) -> Import:
    """Streams the upload straight to disk in bounded chunks (never
    buffering the whole file in memory) and returns immediately once it's
    saved - the actual parse/validate pipeline runs asynchronously in
    worker-ingestion via the campaign.import.events Kafka topic, per the
    "do not keep HTTP requests open for a 17M-row import" requirement.
    import_kind selects the eventual commit target (BASE -> base_members,
    DND -> dnd_records) - staging/preview is identical either way.
    """
    if import_kind not in IMPORT_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"import_kind must be one of {IMPORT_KINDS}")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unsupported file type '{ext}'; allowed: {ALLOWED_EXTENSIONS}"
        )

    storage_dir = Path(settings.import_storage_path)
    storage_dir.mkdir(parents=True, exist_ok=True)
    # Generated filename, never the user-supplied one, to rule out path
    # traversal / malicious filenames entirely (requirements doc §11).
    dest_path = storage_dir / f"{uuid.uuid4().hex}{ext}"

    sha256 = hashlib.sha256()
    total_bytes = 0
    with open(dest_path, "wb") as out:
        while chunk := file.file.read(UPLOAD_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds maximum allowed size")
            sha256.update(chunk)
            out.write(chunk)

    file_hash = sha256.hexdigest()
    existing = db.query(Import).filter(Import.file_hash == file_hash).first()
    if existing is not None:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An identical file was already imported as import #{existing.id} (status={existing.status})",
        )

    imp = Import(
        source_type="UPLOAD",
        import_kind=import_kind,
        source_path=str(dest_path),
        original_filename=file.filename,
        file_hash=file_hash,
        status="IMPORT_CREATED",
        created_by=current_user.id,
    )
    db.add(imp)
    db.flush()  # need imp.id for the outbox payload

    write_event(
        db,
        aggregate_type="import",
        aggregate_id=str(imp.id),
        event_type="import.stage_requested",
        payload={"import_id": imp.id},
        kafka_topic="campaign.import.events",
        kafka_key=str(imp.id),
    )
    db.commit()
    return imp


@router.get("/drop-path/scan", response_model=list[DropFileOut])
def scan_drop_path(
    current_user: User = Depends(require_action(Action.IMPORT_CREATE)),
) -> list[DropFileOut]:
    """Lists files sitting in the controlled server-side drop directory.
    Never processes anything automatically - an operator must explicitly
    create an import job per file via POST /imports/drop-path/create.
    """
    drop_dir = Path(settings.server_drop_path)
    if not drop_dir.is_dir():
        return []

    results: list[DropFileOut] = []
    for entry in sorted(drop_dir.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        stat = entry.stat()
        results.append(
            DropFileOut(
                filename=entry.name,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                detected_format=entry.suffix.lower().lstrip("."),
            )
        )
    return results


@router.post("/drop-path/create", response_model=ImportOut, status_code=status.HTTP_202_ACCEPTED)
def create_from_drop_path(
    req: CreateFromDropRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_CREATE)),
) -> Import:
    if req.import_kind not in IMPORT_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"import_kind must be one of {IMPORT_KINDS}")

    drop_dir = Path(settings.server_drop_path).resolve()
    candidate = (drop_dir / req.filename).resolve()

    # Path traversal protection: the resolved path must stay inside drop_dir.
    if drop_dir not in candidate.parents and candidate != drop_dir:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")
    if not candidate.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found in drop path")
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported file type")

    sha256 = hashlib.sha256()
    with open(candidate, "rb") as f:
        while chunk := f.read(UPLOAD_CHUNK_BYTES):
            sha256.update(chunk)
    file_hash = sha256.hexdigest()

    existing = db.query(Import).filter(Import.file_hash == file_hash).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An identical file was already imported as import #{existing.id} (status={existing.status})",
        )

    imp = Import(
        import_profile_id=req.import_profile_id,
        source_type="SERVER_DROP",
        import_kind=req.import_kind,
        source_path=str(candidate),
        original_filename=candidate.name,
        file_hash=file_hash,
        status="IMPORT_CREATED",
        created_by=current_user.id,
    )
    db.add(imp)
    db.flush()

    write_event(
        db,
        aggregate_type="import",
        aggregate_id=str(imp.id),
        event_type="import.stage_requested",
        payload={"import_id": imp.id},
        kafka_topic="campaign.import.events",
        kafka_key=str(imp.id),
    )
    db.commit()
    return imp


@router.post("/{import_id}/approve", response_model=ImportOut)
def approve_import(
    import_id: int,
    req: ApproveImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_APPROVE)),
) -> Import:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import not found")
    if imp.status != "PREVIEW_READY":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Import must be PREVIEW_READY to approve (current: {imp.status})"
        )

    payload: dict = {"import_id": imp.id}

    if imp.import_kind == "DND":
        if not req.dnd_list_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide dnd_list_name for a DND import")
        payload["dnd_list_name"] = req.dnd_list_name
    else:
        if req.base_id is not None:
            base = db.get(CampaignBase, req.base_id)
            if base is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "base not found")
            payload["base_id"] = base.id
        elif req.new_base_name:
            base = CampaignBase(name=req.new_base_name)
            db.add(base)
            db.flush()
            payload["base_id"] = base.id
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide either base_id or new_base_name")

    old_status = imp.status
    imp.status = "APPROVED"
    imp.approved_by = current_user.id
    imp.approved_at = datetime.now(timezone.utc)
    db.flush()

    write_event(
        db,
        aggregate_type="import",
        aggregate_id=str(imp.id),
        event_type="import.commit_requested",
        payload=payload,
        kafka_topic="campaign.import.events",
        kafka_key=str(imp.id),
    )
    write_audit_log(
        db,
        actor_id=current_user.id,
        action="import.approve",
        entity_type="import",
        entity_id=str(imp.id),
        old_value={"status": old_status},
        new_value={"status": imp.status, **payload},
    )
    db.commit()
    return imp


_RETRIABLE_COMMIT_STATUSES = {"APPROVED", "COMMITTING"}


class RetryCommitRequest(BaseModel):
    base_id: int | None = None
    dnd_list_name: str | None = None


@router.post("/{import_id}/retry-commit", response_model=ImportOut)
def retry_commit(
    import_id: int,
    req: RetryCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_APPROVE)),
) -> Import:
    """Mirrors retry-staging for the commit step. The target (base_id or
    dnd_list_name) must be supplied explicitly because it isn't durably
    recorded on the import row until commit actually succeeds - callers
    must know which target they approved into (visible via GET /bases or
    GET /dnd/lists)."""
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import not found")
    if imp.status not in _RETRIABLE_COMMIT_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Import status '{imp.status}' is not retriable for commit",
        )

    payload: dict = {"import_id": imp.id}
    if imp.import_kind == "DND":
        if not req.dnd_list_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide dnd_list_name for a DND import")
        payload["dnd_list_name"] = req.dnd_list_name
    else:
        if req.base_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide base_id for a BASE import")
        payload["base_id"] = req.base_id

    write_event(
        db,
        aggregate_type="import",
        aggregate_id=str(imp.id),
        event_type="import.commit_requested",
        payload=payload,
        kafka_topic="campaign.import.events",
        kafka_key=str(imp.id),
    )
    write_audit_log(
        db,
        actor_id=current_user.id,
        action="import.retry_commit",
        entity_type="import",
        entity_id=str(imp.id),
        new_value=payload,
    )
    db.commit()
    return imp


@router.post("/{import_id}/reject", response_model=ImportOut)
def reject_import(
    import_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_APPROVE)),
) -> Import:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import not found")
    if imp.status != "PREVIEW_READY":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Import must be PREVIEW_READY to reject (current: {imp.status})"
        )
    old_status = imp.status
    imp.status = "REJECTED"
    write_audit_log(
        db,
        actor_id=current_user.id,
        action="import.reject",
        entity_type="import",
        entity_id=str(imp.id),
        old_value={"status": old_status},
        new_value={"status": imp.status},
    )
    db.commit()
    return imp


# Statuses from which staging can be manually retried - covers both a fresh
# import (never staged) and one interrupted mid-stream (see
# app.services.import_service.stage_import: safe to redo from scratch).
_RETRIABLE_STAGING_STATUSES = {"IMPORT_CREATED", "UPLOADED", "VALIDATING", "FAILED"}


@router.post("/{import_id}/retry-staging", response_model=ImportOut)
def retry_staging(
    import_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.IMPORT_CREATE)),
) -> Import:
    """Manually re-triggers staging for an import stuck outside the normal
    Kafka-redelivery self-heal path - e.g. the event that would have
    triggered it was lost (broker data loss, topic manually purged) rather
    than the more common case of a worker crash with Kafka still intact
    (which self-heals via at-least-once redelivery, no operator action
    needed). Operators must be able to recover without SSH/worker restarts
    per the requirements doc's operational-resilience goals.
    """
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "import not found")
    if imp.status not in _RETRIABLE_STAGING_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Import status '{imp.status}' is not retriable for staging",
        )

    write_event(
        db,
        aggregate_type="import",
        aggregate_id=str(imp.id),
        event_type="import.stage_requested",
        payload={"import_id": imp.id},
        kafka_topic="campaign.import.events",
        kafka_key=str(imp.id),
    )
    write_audit_log(
        db,
        actor_id=current_user.id,
        action="import.retry_staging",
        entity_type="import",
        entity_id=str(imp.id),
        old_value={"status": imp.status},
    )
    db.commit()
    return imp
