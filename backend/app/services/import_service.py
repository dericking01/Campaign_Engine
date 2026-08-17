"""Import staging and commit orchestration - the Phase 2 core pipeline.

stage_import() streams the source file in bounded chunks (never loading the
whole file into memory), normalizes MSISDNs and classifies each row, and
bulk-loads each chunk into campaign.import_staging_rows via COPY. This
directly replaces the legacy per-file, per-format converter scripts
(convert_txt_to_csv.py et al) with one general pipeline driven by
import_profiles instead of a bespoke script per source format.

commit_import() moves VALID staged rows into a new base_version via one
set-based INSERT...SELECT - never a Python loop over rows.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.normalizers import normalize_msisdn
from app.ingestion.parsers import ColumnMapping, ParsedRow, sniff_delimiter, stream_row_chunks
from app.ingestion.profiles import (
    mapping_from_profile_config,
    resolve_default_mapping,
    sniff_has_header,
)
from app.models.bases import BaseVersion, CampaignBase
from app.models.dnd import DndList
from app.models.imports import Import, ImportProfile
from app.repositories.import_repository import (
    StagedRow,
    commit_valid_rows_to_base,
    commit_valid_rows_to_dnd,
    compute_staging_summary,
    copy_staging_rows,
    mark_duplicate_msisdns,
)
from app.core.logging import get_logger

logger = get_logger(component="import_service")


def _resolve_mapping_and_format(
    db: Session, imp: Import, file_path: Path
) -> tuple[ColumnMapping, str, bool]:
    if imp.import_profile_id:
        profile = db.get(ImportProfile, imp.import_profile_id)
        mapping = mapping_from_profile_config(profile.column_mapping)
        return mapping, profile.delimiter, True

    with open(file_path, encoding="utf-8", errors="replace") as fh:
        sample = [next(fh, "") for _ in range(5)]
    delimiter = sniff_delimiter(sample)
    has_header = sniff_has_header(file_path)
    if not has_header:
        # Headerless single-column files (DND lists) - position 0 is msisdn.
        return ColumnMapping(by_position={"msisdn": 0}), delimiter, False

    header = next(iter(sample), "").strip().split(delimiter)
    mapping = resolve_default_mapping(header)
    if "msisdn" not in mapping.by_header:
        raise ValueError(
            "Could not auto-detect an MSISDN column; create an import_profile "
            "with an explicit column_mapping for this file format."
        )
    return mapping, delimiter, True


def _classify(row: ParsedRow) -> StagedRow:
    raw_msisdn = row.raw.get("msisdn", "")
    result = normalize_msisdn(raw_msisdn)
    if result.is_valid:
        return StagedRow(
            row_number=row.row_number,
            raw=row.raw,
            normalized_msisdn=result.msisdn,
            validation_status="VALID",
            rejection_reason=None,
        )
    # result.reason is always set here since result.is_valid was False above.
    reason = row.parse_warning or result.reason.value
    return StagedRow(
        row_number=row.row_number,
        raw=row.raw,
        normalized_msisdn=None,
        validation_status="INVALID",
        rejection_reason=reason,
    )


def stage_import(db: Session, import_id: int) -> None:
    """Streams and stages the whole file. Safe to re-enter from scratch if a
    prior attempt was interrupted mid-stream (worker killed, container
    removed, etc. - not just a clean Python exception): staging is a
    derived/rebuildable artifact, never irreplaceable state, so resuming
    means "redo the chunked stream, not resume some partial offset." Any
    staging rows a previous, interrupted attempt already committed for this
    import are discarded first so re-staging is idempotent regardless of how
    far that attempt got. See docs/decisions.md for the incident that
    surfaced this gap - an interrupted first attempt left ~11M/17M rows
    durably staged (proving the per-chunk-commit design works) but the
    import was stuck in VALIDATING with no automatic path to resume.
    """
    imp = db.get(Import, import_id)
    if imp is None:
        raise ValueError(f"import {import_id} not found")

    # Atomic claim: the caller already checked status via a separate read
    # (app.workers.ingestion_worker._should_process), which is NOT
    # sufficient on its own under READ COMMITTED - two concurrent
    # transactions can both read the pre-claim status before either commits
    # (classic TOCTOU), both conclude they're clear to proceed, and both
    # start staging concurrently. This UPDATE ... WHERE status IN (...) is
    # the actual concurrency guard: only one transaction can ever affect a
    # row here, so a rowcount of 0 means another invocation already claimed
    # it and this one must not do any work. Caught live during Phase 2
    # real-scale testing - see docs/decisions.md.
    claim = db.execute(
        text("""
            UPDATE campaign.imports SET status = 'VALIDATING', updated_at = now()
            WHERE id = :id AND status IN ('IMPORT_CREATED', 'UPLOADED', 'VALIDATING')
        """),
        {"id": import_id},
    )
    db.commit()
    if claim.rowcount == 0:
        logger.info("import.stage_already_claimed", import_id=import_id)
        return

    db.execute(
        text("DELETE FROM campaign.import_staging_rows WHERE import_id = :id"),
        {"id": import_id},
    )
    db.commit()

    file_path = Path(imp.source_path)
    mapping, delimiter, has_header = _resolve_mapping_and_format(db, imp, file_path)

    rows_seen = 0
    for chunk in stream_row_chunks(
        file_path, mapping, delimiter=delimiter, has_header=has_header
    ):
        staged = [_classify(row) for row in chunk]
        copy_staging_rows(db, import_id, staged)
        db.commit()  # bound transaction/WAL size per chunk, not one giant txn for 17M rows
        rows_seen += len(chunk)
        logger.info("import.stage_progress", import_id=import_id, rows_seen=rows_seen)

    duplicates_marked = mark_duplicate_msisdns(db, import_id)
    db.commit()
    logger.info("import.duplicates_marked", import_id=import_id, count=duplicates_marked)

    summary = compute_staging_summary(db, import_id)
    db.execute(
        text("""
            UPDATE campaign.imports SET
                status = 'PREVIEW_READY',
                total_rows = :total_rows,
                valid_rows = :valid_rows,
                invalid_rows = :invalid_rows,
                duplicate_rows = :duplicate_rows,
                zone_distribution = :zone_distribution,
                sample_rows = :sample_rows,
                updated_at = now()
            WHERE id = :id
        """),
        {
            "id": import_id,
            "total_rows": summary["total_rows"],
            "valid_rows": summary["valid_rows"],
            "invalid_rows": summary["invalid_rows"],
            "duplicate_rows": summary["duplicate_rows"],
            "zone_distribution": _to_json(summary["zone_distribution"]),
            "sample_rows": _to_json(
                {
                    "valid": summary["sample_valid_rows"],
                    "rejected": summary["sample_rejected_rows"],
                }
            ),
        },
    )
    db.commit()
    logger.info("import.staged", import_id=import_id, **{k: v for k, v in summary.items() if k in ("total_rows", "valid_rows", "invalid_rows", "duplicate_rows")})


def commit_import(
    db: Session, import_id: int, *, base_id: int | None = None, dnd_list_name: str | None = None
) -> None:
    """Moves VALID staged rows into their commit target. Branches on
    imports.import_kind - BASE and DND share the entire stage/preview/
    approve/commit pipeline up to this point (same parser, normalizer,
    staging table, worker, lock) and only diverge at the final target
    table, per the Phase 3 "reuse the ingestion pipeline for DND" design.
    """
    imp = db.get(Import, import_id)
    if imp is None:
        raise ValueError(f"import {import_id} not found")

    db.execute(
        text("UPDATE campaign.imports SET status = 'COMMITTING', updated_at = now() WHERE id = :id"),
        {"id": import_id},
    )

    if imp.import_kind == "DND":
        if not dnd_list_name:
            raise ValueError("dnd_list_name is required to commit a DND import")
        _commit_dnd(db, import_id, dnd_list_name)
    else:
        if base_id is None:
            raise ValueError("base_id is required to commit a BASE import")
        _commit_base(db, import_id, base_id)

    db.commit()


def _commit_base(db: Session, import_id: int, base_id: int) -> None:
    """Flips the previous current version off first (in the same
    transaction) so the partial unique index on base_versions(base_id)
    WHERE is_current never sees two current rows at once."""
    base = db.get(CampaignBase, base_id)
    if base is None:
        raise ValueError(f"base {base_id} not found")

    db.execute(
        text("UPDATE campaign.base_versions SET is_current = false WHERE base_id = :base_id"),
        {"base_id": base_id},
    )

    new_version = BaseVersion(base_id=base_id, source_import_id=import_id, is_current=True)
    db.add(new_version)
    db.flush()  # need new_version.id before the INSERT...SELECT below

    inserted = commit_valid_rows_to_base(db, import_id, new_version.id)

    new_version.member_count = inserted
    new_version.committed_at = datetime.now(timezone.utc)

    db.execute(
        text("""
            UPDATE campaign.imports SET
                status = 'READY', committed_base_version_id = :base_version_id, updated_at = now()
            WHERE id = :id
        """),
        {"id": import_id, "base_version_id": new_version.id},
    )
    logger.info("import.committed", import_id=import_id, base_version_id=new_version.id, member_count=inserted)


def _commit_dnd(db: Session, import_id: int, dnd_list_name: str) -> None:
    """Unlike bases, DND has no single-current-version constraint - "on
    DND" is the union of all active lists (default policy, see
    docs/decisions.md item 6), so committing just adds a new active list
    rather than superseding a previous one."""
    next_version = db.execute(
        text("SELECT COALESCE(MAX(version), 0) + 1 FROM campaign.dnd_lists WHERE name = :name"),
        {"name": dnd_list_name},
    ).scalar_one()

    new_list = DndList(
        name=dnd_list_name,
        source_import_id=import_id,
        version=next_version,
        is_active=True,
    )
    db.add(new_list)
    db.flush()  # need new_list.id before the INSERT...SELECT below

    inserted = commit_valid_rows_to_dnd(db, import_id, new_list.id)

    db.execute(
        text("""
            UPDATE campaign.imports SET
                status = 'READY', committed_dnd_list_id = :dnd_list_id, updated_at = now()
            WHERE id = :id
        """),
        {"id": import_id, "dnd_list_id": new_list.id},
    )
    logger.info("import.committed", import_id=import_id, dnd_list_id=new_list.id, record_count=inserted)


def _to_json(value: dict) -> str:
    return json.dumps(value, default=str)
