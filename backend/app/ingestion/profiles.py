"""Column-mapping resolution: explicit import_profiles.column_mapping, or a
sensible default auto-detected from the header - covering the real header
names found across the legacy converter scripts (MPA_MSISDN, TERRITORY,
COMMERCIAL_REGION, GENDER, AGE, ARPU_SEGMENT, ...), so common recurring
formats don't require an operator to hand-build a profile first.
"""

import csv
from pathlib import Path

from app.ingestion.parsers import ColumnMapping

_ALIASES: dict[str, list[str]] = {
    "msisdn": ["msisdn", "customer_msisdn", "mpa_msisdn", "phone", "phone_number"],
    "territory": ["territory", "zone"],
    "commercial_region": ["commercial_region", "region"],
    "gender": ["gender", "sex"],
    "age": ["age"],
    "arpu_segment": ["arpu_segment"],
}


def resolve_default_mapping(header: list[str]) -> ColumnMapping:
    normalized = {h.strip().lower(): h for h in header}
    by_header: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                by_header[canonical] = normalized[alias]
                break
    return ColumnMapping(by_header=by_header)


def mapping_from_profile_config(config: dict) -> ColumnMapping:
    return ColumnMapping(
        by_header=config.get("by_header", {}),
        by_position=config.get("by_position", {}),
    )


def sniff_has_header(file_path: Path, encoding: str = "utf-8") -> bool:
    """A row is treated as a header if its first field isn't a plausible
    MSISDN (all-digit-ish). Best-effort; explicit profiles should set
    has_header themselves for anything unusual (e.g. the DND single-column
    files, which have no header at all)."""
    with open(file_path, encoding=encoding, errors="replace") as fh:
        first_line = fh.readline()
    first_cell = next(csv.reader([first_line]), [""])[0]
    digits = sum(c.isdigit() for c in first_cell)
    return digits < len(first_cell) * 0.5
