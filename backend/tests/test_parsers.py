from pathlib import Path

from app.ingestion.parsers import ColumnMapping, stream_row_chunks

FIXTURE = Path(__file__).parent / "fixtures" / "malformed_base_sample.csv"

MAPPING = ColumnMapping(by_header={"msisdn": "MSISDN", "gender": "GENDER", "age": "AGE"})


def test_parses_well_formed_rows() -> None:
    chunks = list(stream_row_chunks(FIXTURE, MAPPING, chunk_size=100))
    rows = chunks[0]
    assert rows[0].raw["msisdn"] == "255712345671"
    assert rows[0].raw["gender"] == "M"
    assert rows[1].raw["msisdn"] == "255712345672"


def test_tolerates_glued_quoted_field_without_failing_the_whole_import() -> None:
    """Reproduces the real legacy bug documented in not_in_base.py: a row
    where MSISDN,GENDER,AGE are all crammed into one quoted CSV field
    (upstream export bug). pandas' C parser hard-fails the entire file on
    this; the parser here must isolate just this row."""
    chunks = list(stream_row_chunks(FIXTURE, MAPPING, chunk_size=100))
    rows = chunks[0]
    glued_row = rows[2]
    assert glued_row.raw["msisdn"] == "255746116585"
    # GENDER/AGE were swallowed into the glued field upstream - empty, not a crash.
    assert glued_row.raw["gender"] == ""
    assert glued_row.raw["age"] == ""


def test_tolerates_truncated_final_line_with_unterminated_quote() -> None:
    """Reproduces the second real legacy bug: the source file's last line
    has an unterminated quote. Python's csv module tolerates this (unlike
    pandas' C parser, which raises 'EOF inside string')."""
    chunks = list(stream_row_chunks(FIXTURE, MAPPING, chunk_size=100))
    rows = chunks[0]
    last_row = rows[-1]
    assert last_row.raw["msisdn"] == "255700000099"


def test_does_not_lose_or_duplicate_rows_across_the_malformed_ones() -> None:
    chunks = list(stream_row_chunks(FIXTURE, MAPPING, chunk_size=100))
    rows = chunks[0]
    assert len(rows) == 5  # 6 data lines in the fixture minus 0 skipped blanks
    assert [r.row_number for r in rows] == [2, 3, 4, 5, 6]


def test_chunking_yields_bounded_size_chunks() -> None:
    chunks = list(stream_row_chunks(FIXTURE, MAPPING, chunk_size=2))
    assert [len(c) for c in chunks] == [2, 2, 1]
