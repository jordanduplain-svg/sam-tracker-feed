"""Build the SAM.gov feed read by the browser extension.

Reads SAM.gov's public daily CSV (the authorized extract, no account or key),
keeps the notices that can still be answered and writes a compact JSON file.
Run every morning by .github/workflows/sam-feed.yml.

    python tools/build_sam_feed.py [--csv FILE] [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser import _lines, is_still_open, normalize_deadline, parse_date  # noqa: E402

CSV_URL = "https://falextracts.s3.amazonaws.com/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"
# Notice types still open to answers (awards and justifications are left out).
OPEN_TYPES = {
    "Solicitation",
    "Combined Synopsis/Solicitation",
    "Presolicitation",
    "Sources Sought",
    "Special Notice",
}
# Enough text for the keywords; keeps the file small enough for the extension.
MAX_DESCRIPTION = 3000
FEED_VERSION = 1


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def to_offer(row: dict[str, str]) -> dict[str, str]:
    agency, sub = clean(row.get("Department/Ind.Agency")), clean(row.get("Sub-Tier"))
    place = ", ".join(p for p in (clean(row.get(c)) for c in ("PopCity", "PopState", "PopCountry")) if p)
    notice_id = row["NoticeId"].strip()
    offer = {
        "id": notice_id,
        "title": clean(row.get("Title")),
        "organization": f"{agency} / {sub}" if sub and sub != agency else agency,
        "type": clean(row.get("Type")),
        "posted": clean(row.get("PostedDate")),
        "deadline": normalize_deadline(row.get("ResponseDeadLine") or ""),
        "place": place,
        "naics": clean(row.get("NaicsCode")),
        "setAside": clean(row.get("SetASide")),
        "description": clean(row.get("Description"))[:MAX_DESCRIPTION],
    }
    return {k: v for k, v in offer.items() if v}  # empty fields left out to save space


def build(csv_path: Path, today: date) -> list[dict[str, str]]:
    offers = []
    for row in csv.DictReader(_lines(csv_path)):
        if not (row.get("NoticeId") or "").strip() or row.get("Active") != "Yes":
            continue
        if clean(row.get("Type")) not in OPEN_TYPES or parse_date(row.get("PostedDate") or "") is None:
            continue
        if not is_still_open(row.get("ResponseDeadLine") or "", row.get("ArchiveDate") or "", today):
            continue
        offers.append(to_offer(row))
    offers.sort(key=lambda o: o.get("posted", ""), reverse=True)
    return offers


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--csv", type=Path, help="use this CSV instead of downloading it")
    args.add_argument("--out", type=Path, default=Path("feed/sam.json"))
    opts = args.parse_args()

    csv_path = opts.csv
    if csv_path is None:
        csv_path = Path("ContractOpportunitiesFullCSV.csv")
        download(CSV_URL, csv_path)

    offers = build(csv_path, date.today())
    if len(offers) < 1000:  # SAM.gov always has thousands open: the CSV is broken
        sys.exit(f"Only {len(offers)} open notices found, feed not updated.")

    opts.out.parent.mkdir(parents=True, exist_ok=True)
    feed = {
        "version": FEED_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offers": offers,
    }
    opts.out.write_text(json.dumps(feed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(offers)} open notices -> {opts.out} ({opts.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
