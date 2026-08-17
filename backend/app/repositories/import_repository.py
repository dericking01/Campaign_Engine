"""Bulk data-movement helpers for the ingestion pipeline.

Every function here either uses PostgreSQL COPY (network-bound bulk load
from the app) or a single set-based SQL statement (bulk transformation
already resident in Postgres) - never a per-row INSERT/UPDATE loop, per the
"avoid ORM loops over millions of records" requirement.
"""

import csv
import io
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ingestion.parsers import ParsedRow


@dataclass(frozen=True, slots=True)
class StagedRow:
    row_number: int
    raw: dict[str, str]
    normalized_msisdn: str | None
    validation_status: str  # VALID | INVALID
    rejection_reason: str | None


def copy_staging_rows(db: Session, import_id: int, rows: list[StagedRow]) -> None:
    """Bulk-load one chunk of staged rows via COPY FROM STDIN. `rows` is
    already bounded by the caller's chunk size - this function itself does
    not impose a limit, so callers must chunk (see ingestion service)."""
    if not rows:
        return

    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(
            [
                import_id,
                row.row_number,
                json.dumps(row.raw),
                row.normalized_msisdn or "",
                row.validation_status,
                row.rejection_reason or "",
            ]
        )
    buf.seek(0)

    raw_conn = db.connection().connection
    with raw_conn.cursor() as cur:
        cur.copy_expert(
            """
            COPY campaign.import_staging_rows
                (import_id, row_number, raw, normalized_msisdn, validation_status, rejection_reason)
            FROM STDIN WITH (FORMAT csv, NULL '')
            """,
            buf,
        )


def mark_duplicate_msisdns(db: Session, import_id: int) -> int:
    """Among rows currently VALID for this import, mark every occurrence of
    a normalized_msisdn after its first as DUPLICATE - one set-based
    statement, not an in-memory seen-set (which would need to hold up to
    17M+ strings in application memory)."""
    result = db.execute(
        text("""
            WITH ranked AS (
                SELECT id, row_number() OVER (
                    PARTITION BY normalized_msisdn ORDER BY row_number
                ) AS rn
                FROM campaign.import_staging_rows
                WHERE import_id = :import_id AND validation_status = 'VALID'
            )
            UPDATE campaign.import_staging_rows s
            SET validation_status = 'DUPLICATE'
            FROM ranked
            WHERE s.id = ranked.id AND ranked.rn > 1
        """),
        {"import_id": import_id},
    )
    return result.rowcount


def compute_staging_summary(db: Session, import_id: int) -> dict:
    """Single aggregate query - never iterates staging rows in Python."""
    row = db.execute(
        text("""
            SELECT
                count(*) AS total_rows,
                count(*) FILTER (WHERE validation_status = 'VALID') AS valid_rows,
                count(*) FILTER (WHERE validation_status = 'INVALID') AS invalid_rows,
                count(*) FILTER (WHERE validation_status = 'DUPLICATE') AS duplicate_rows
            FROM campaign.import_staging_rows
            WHERE import_id = :import_id
        """),
        {"import_id": import_id},
    ).mappings().one()

    zone_rows = db.execute(
        text("""
            SELECT coalesce(raw->>'territory', '(unspecified)') AS zone, count(*) AS n
            FROM campaign.import_staging_rows
            WHERE import_id = :import_id AND validation_status = 'VALID'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 50
        """),
        {"import_id": import_id},
    ).all()

    sample_valid = db.execute(
        text("""
            SELECT raw FROM campaign.import_staging_rows
            WHERE import_id = :import_id AND validation_status = 'VALID'
            ORDER BY row_number LIMIT 20
        """),
        {"import_id": import_id},
    ).scalars().all()

    sample_rejected = db.execute(
        text("""
            SELECT row_number, raw, validation_status, rejection_reason
            FROM campaign.import_staging_rows
            WHERE import_id = :import_id AND validation_status IN ('INVALID', 'DUPLICATE')
            ORDER BY row_number LIMIT 20
        """),
        {"import_id": import_id},
    ).mappings().all()

    return {
        "total_rows": row["total_rows"],
        "valid_rows": row["valid_rows"],
        "invalid_rows": row["invalid_rows"],
        "duplicate_rows": row["duplicate_rows"],
        "zone_distribution": {r.zone: r.n for r in zone_rows},
        "sample_valid_rows": list(sample_valid),
        "sample_rejected_rows": [dict(r) for r in sample_rejected],
    }


def commit_valid_rows_to_base(db: Session, import_id: int, base_version_id: int) -> int:
    """One INSERT...SELECT moving every VALID staged row into base_members
    under the new base_version - a set-based bulk operation entirely inside
    Postgres, not a COPY (the data is already resident in the database;
    COPY is for the app->DB network boundary crossed during staging)."""
    result = db.execute(
        text("""
            INSERT INTO campaign.base_members
                (base_version_id, customer_msisdn, territory, commercial_region,
                 gender, age, arpu_segment, source_snapshot)
            SELECT
                :base_version_id,
                normalized_msisdn,
                raw->>'territory',
                raw->>'commercial_region',
                raw->>'gender',
                NULLIF(raw->>'age', '')::int,
                raw->>'arpu_segment',
                raw
            FROM campaign.import_staging_rows
            WHERE import_id = :import_id AND validation_status = 'VALID'
            ON CONFLICT (base_version_id, customer_msisdn) DO NOTHING
        """),
        {"import_id": import_id, "base_version_id": base_version_id},
    )
    return result.rowcount


def commit_valid_rows_to_dnd(db: Session, import_id: int, dnd_list_id: int) -> int:
    """DND counterpart to commit_valid_rows_to_base - same set-based
    INSERT...SELECT pattern, target table only. DND records are just a
    normalized MSISDN plus which list they belong to."""
    result = db.execute(
        text("""
            INSERT INTO campaign.dnd_records (dnd_list_id, customer_msisdn)
            SELECT DISTINCT :dnd_list_id, normalized_msisdn
            FROM campaign.import_staging_rows
            WHERE import_id = :import_id AND validation_status = 'VALID'
            ON CONFLICT (dnd_list_id, customer_msisdn) DO NOTHING
        """),
        {"import_id": import_id, "dnd_list_id": dnd_list_id},
    )
    return result.rowcount
