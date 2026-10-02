# SAM Tracker feed

Every morning, a GitHub workflow downloads SAM.gov's public daily extract of contract
opportunities (`ContractOpportunitiesFullCSV.csv`, no account or API key), keeps the notices
that can still be answered and publishes them on GitHub Pages:

https://jordanduplain-svg.github.io/sam-tracker-feed/sam.json

This is the file the SAM Tracker browser extension reads, so the extension never calls sam.gov.

- `tools/build_sam_feed.py`: builds the feed (`python tools/build_sam_feed.py --out site/sam.json`)
- `app/parser.py`, `app/models.py`: CSV reading shared with the SAM Tracker desktop app
- `tools/check_sources.py`: daily check that the extension's other sources still answer (Texas ESBD excluded: its robots.txt turns robots away)
- `.github/workflows/sam-feed.yml`: daily run (11:30 UTC) and "Run workflow" button

Data: U.S. Government public data from SAM.gov.
