from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ImportProfile(Base, TimestampMixin):
    """Reusable source-column -> canonical-field mapping, so operators don't
    re-map columns per file the way each legacy convert_*_to_csv.py script
    hardcoded its own one-off column layout."""

    __tablename__ = "import_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    delimiter: Mapped[str] = mapped_column(String, nullable=False, server_default=",")
    encoding: Mapped[str] = mapped_column(String, nullable=False, server_default="utf-8")
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    product_scope: Mapped[str | None] = mapped_column(String)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.users.id"))


class Import(Base, TimestampMixin):
    """One row per GUI-upload or server-drop import job. Tracks the full
    import lifecycle state machine (see docs/architecture.md)."""

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_profile_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.import_profiles.id")
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    import_kind: Mapped[str] = mapped_column(String, nullable=False, server_default="BASE")
    source_path: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String)
    file_hash: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="IMPORT_CREATED")
    total_rows: Mapped[int | None] = mapped_column(BigInteger)
    valid_rows: Mapped[int | None] = mapped_column(BigInteger)
    invalid_rows: Mapped[int | None] = mapped_column(BigInteger)
    duplicate_rows: Mapped[int | None] = mapped_column(BigInteger)
    dnd_impact_count: Mapped[int | None] = mapped_column(BigInteger)
    zone_distribution: Mapped[dict | None] = mapped_column(JSONB)
    sample_rows: Mapped[dict | None] = mapped_column(JSONB)
    error_summary: Mapped[dict | None] = mapped_column(JSONB)
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.users.id"))
    approved_at: Mapped[datetime | None]
    committed_base_version_id: Mapped[int | None] = mapped_column(BigInteger)
    committed_dnd_list_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.dnd_lists.id")
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.users.id"))


class ImportStagingRow(Base):
    """Transient per-import staging area (Odoo-like preview). Purged/archived
    after commit - see docs/architecture.md retention note."""

    __tablename__ = "import_staging_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.imports.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_msisdn: Mapped[str | None] = mapped_column(String(12))
    validation_status: Mapped[str] = mapped_column(String, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String)
