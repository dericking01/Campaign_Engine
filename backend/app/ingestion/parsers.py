"""Streaming, chunked, malformed-row-tolerant file parsing.

Deliberately uses Python's stdlib `csv` module rather than Polars' or
pandas' CSV parsers for the initial row-splitting pass. This is not a
performance shortcut - it is a direct fix for a real bug class found in the
legacy codebase: `not_in_base.py` documents real AfyaCall source files where
a row's MSISDN/GENDER/AGE are all crammed into one quoted CSV field (e.g.
`"255746116585,M         ,39"`, produced by some upstream export bug) plus a
truncated final line with an unterminated quote. pandas' C parser hard-fails
the entire file on both ("EOF inside string"); Python's `csv` module
tolerates them row-by-row, which is exactly the "isolate/report invalid
rows rather than failing the whole import" requirement. Vectorized
Polars/normalization work happens per-chunk downstream in ingestion
services, once rows are already safely split.

Never reads a whole file into memory: `stream_row_chunks` is a generator
that yields bounded-size chunks, backed by a plain line-by-line file handle.
"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CHUNK_SIZE = 20_000

# csv.field_size_limit default (128KiB) is too small for some legacy export
# quirks (see module docstring) - raise it the same way the legacy Python
# scripts did (csv.field_size_limit(10**9)).
csv.field_size_limit(10**9)


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """Maps canonical field names to source columns. `by_header` takes
    precedence when the file has a header row; `by_position` is the
    fallback for headerless TXT files (matching the legacy converters'
    positional column layouts, e.g. MPA_MSISDN/GENDER/AGE)."""

    by_header: dict[str, str] = field(default_factory=dict)  # canonical -> source header (case-insensitive)
    by_position: dict[str, int] = field(default_factory=dict)  # canonical -> 0-based column index


@dataclass(frozen=True, slots=True)
class ParsedRow:
    row_number: int
    raw: dict[str, str]
    parse_warning: str | None = None


def sniff_delimiter(sample_lines: list[str]) -> str:
    """Best-effort delimiter detection between the two the legacy files
    actually used (comma, tab). Falls back to comma."""
    tab_count = sum(line.count("\t") for line in sample_lines)
    comma_count = sum(line.count(",") for line in sample_lines)
    return "\t" if tab_count > comma_count else ","


def _resolve_header_index(header: list[str], source_header: str) -> int | None:
    normalized = [h.strip().lower() for h in header]
    target = source_header.strip().lower()
    return normalized.index(target) if target in normalized else None


def _extract_field(raw_row: list[str], index: int) -> str:
    return raw_row[index].strip() if index < len(raw_row) else ""


def _unglue_field(value: str) -> str:
    """Legacy data quirk: some rows have MSISDN,GENDER,AGE crammed into one
    quoted field (`"255746116585,M         ,39"`). If a field mapped to a
    single canonical column itself contains commas, the real value is the
    part before the first comma - see module docstring."""
    return value.split(",")[0].strip() if "," in value else value


def stream_row_chunks(
    file_path: Path,
    mapping: ColumnMapping,
    *,
    delimiter: str = ",",
    has_header: bool = True,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    encoding: str = "utf-8",
) -> Iterator[list[ParsedRow]]:
    """Yield bounded-size chunks of parsed rows. Malformed individual rows
    are isolated (returned with a parse_warning) rather than aborting the
    whole stream."""
    with open(file_path, encoding=encoding, errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)

        header_index: dict[str, int] = {}
        if has_header:
            try:
                header = next(reader)
            except StopIteration:
                return
            for canonical, source_header in mapping.by_header.items():
                idx = _resolve_header_index(header, source_header)
                if idx is not None:
                    header_index[canonical] = idx
        header_index.update(mapping.by_position)

        chunk: list[ParsedRow] = []
        row_number = 1 if not has_header else 2  # 1-based, matching how operators read the file

        for raw_row in reader:
            warning = None
            if not raw_row or all(not cell.strip() for cell in raw_row):
                row_number += 1
                continue  # skip genuinely blank lines, not a data error

            values: dict[str, str] = {}
            for canonical, idx in header_index.items():
                val = _extract_field(raw_row, idx)
                if canonical == "msisdn":
                    val = _unglue_field(val)
                values[canonical] = val

            if len(raw_row) < len(header_index):
                warning = f"row has {len(raw_row)} columns, expected at least {len(header_index)}"

            chunk.append(ParsedRow(row_number=row_number, raw=values, parse_warning=warning))
            row_number += 1

            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        if chunk:
            yield chunk
