"""Turn the rows of the SAM.gov CSV into Offer objects."""
from __future__ import annotations

import codecs
import csv
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterator
from zoneinfo import ZoneInfo

from .models import Offer

SAM_TIME_ZONE = ZoneInfo("America/New_York")

# Offer field -> CSV column. The only place that knows the CSV layout.
CSV_COLUMNS = {
    "notice_id": "NoticeId",
    "title": "Title",
    "solicitation_number": "Sol#",
    "agency": "Department/Ind.Agency",
    "sub_agency": "Sub-Tier",
    "type": "Type",
    "posted_date": "PostedDate",
    "deadline": "ResponseDeadLine",
    "archive_date": "ArchiveDate",
    "naics": "NaicsCode",
    "set_aside": "SetASide",
    "contact_name": "PrimaryContactFullname",
    "contact_email": "PrimaryContactEmail",
    "url": "Link",
    "description": "Description",
}
PLACE_COLUMNS = ("PopCity", "PopState", "PopCountry")

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


class CsvFormatError(Exception):
    """The CSV does not have the columns we expect."""


def parse_date(value: str) -> date | None:
    """Read the date part of '2026-09-25 10:41:47' or '2026-09-25T...'."""
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _cp1252_fallback(error: UnicodeDecodeError) -> tuple[str, int]:
    """Bytes that are not valid UTF-8 are read as Windows-1252 instead."""
    bad = error.object[error.start:error.end]
    return bad.decode("cp1252", errors="replace"), error.end


codecs.register_error("cp1252_fallback", _cp1252_fallback)


def decode_line(raw: bytes) -> str:
    """The SAM.gov file mixes UTF-8 and Windows-1252, sometimes in the same line:
    decode as UTF-8, and only the invalid bytes as Windows-1252."""
    return raw.decode("utf-8", errors="cp1252_fallback")


def _lines(path: Path) -> Iterator[str]:
    with open(path, "rb") as f:
        first = True
        for raw in f:
            line = decode_line(raw)
            if first:
                line = line.removeprefix("﻿")  # UTF-8 byte order mark
                first = False
            yield line


def is_still_open(deadline: str, archive_date: str, today: date) -> bool:
    """Can the offer still be answered? Day-level check, the pages do the exact time.

    Closed when archived by SAM.gov or when the deadline day has passed.
    Without a deadline, open until its archive date.
    """
    archived = parse_date(archive_date or "")
    if archived is not None and archived < today:
        return False
    due = parse_date(deadline or "")
    return due is None or due >= today


def normalize_deadline(value: str) -> str:
    """Give a time zone to deadlines that have a time but none ("2026-10-30T23:59:00").

    SAM.gov works in US Eastern time; without this they would be read as UTC,
    up to 5 hours off.
    """
    value = value.strip()
    if len(value) <= 10:
        return value  # empty or date only
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        return value
    return parsed.replace(tzinfo=SAM_TIME_ZONE).isoformat()


def read_csv(
    path: Path,
    since: date,
    on_row: Callable[[int], None] | None = None,
    today: date | None = None,
) -> Iterator[Offer]:
    """Yield offers posted on or after `since`, plus older ones that are still open.

    An offer can stay open for months: looking only at the posting date would
    miss it. `on_row` gets the row count.
    """
    today = today or date.today()
    reader = csv.DictReader(_lines(path))
    missing = [c for c in CSV_COLUMNS.values() if c not in (reader.fieldnames or [])]
    if missing:
        raise CsvFormatError(f"Missing CSV columns: {', '.join(missing)}")

    for count, row in enumerate(reader, start=1):
        if on_row and count % 10000 == 0:
            on_row(count)
        posted = parse_date(row.get("PostedDate") or "")
        if posted is None or not (row.get("NoticeId") or "").strip():
            continue
        if posted < since and not is_still_open(row.get("ResponseDeadLine") or "",
                                                row.get("ArchiveDate") or "", today):
            continue
        yield row_to_offer(row)


def row_to_offer(row: dict[str, str]) -> Offer:
    fields = {name: (row.get(col) or "").strip() for name, col in CSV_COLUMNS.items()}
    fields["deadline"] = normalize_deadline(fields["deadline"])
    place = ", ".join(p.strip() for p in (row.get(c) or "" for c in PLACE_COLUMNS) if p.strip())
    return Offer(place=place, **fields)

