"""Daily check of the sources the SAM Tracker extension reads.

Each check asks the source for what the extension needs (the same fields, open
opportunities only) and fails if it errors, if a field is gone or if nothing is open.
Run by .github/workflows/sam-feed.yml: a failed run sends GitHub's usual e-mail.

Texas ESBD is checked with one request a day (the first page of open solicitations),
the lightest possible look. SAM.gov is checked by the feed build itself.

    python tools/check_sources.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

TODAY = f"{date.today().isoformat()}T00:00:00"
HEADERS = {"User-Agent": "SAM-Tracker-source-check (github.com/jordanduplain-svg/sam-tracker-feed)"}

# name -> (domain, dataset, fields the extension reads, filter of what is open)
SOCRATA = {
    "RAMP LA": ("data.lacity.org", "hf3r-utnq",
                "rampid, title, stagename, category, type, bidpost, closedate, department, url",
                "stagename in ('Open', 'Amended')"),
    "NYC City Record": ("data.cityofnewyork.us", "dg92-zbpx",
                        "request_id, short_title, agency_name, category_description, selection_method_description, "
                        "start_date, due_date, pin, additional_description_1",
                        f"section_name='Procurement' AND type_of_notice_description='Solicitation' AND due_date >= '{TODAY}'"),
    "San Francisco": ("data.sf.gov", "eshn-8t3a",
                      "event_id, department, category, type, open_date, due_date, title, sfcitypartner_link",
                      f"due_date >= '{TODAY}'"),
    "Montgomery County MD": ("data.montgomerycountymd.gov", "eeq6-nnwe",
                             "status, type, number, description, issuancedate, closingdate, construction, lsbrpindicator, department",
                             f"status='Active' AND closingdate >= '{TODAY}'"),
    "Delaware": ("data.delaware.gov", "2hnj-zwix",
                 "contractnumber, contracttitle, opendate, deadlinedate, agencycode, unspsc, bidurl",
                 f"deadlinedate >= '{TODAY}'"),
    "TxDOT lettings": ("data.texas.gov", "drau-zphx",
                       "control_section_job_csj, project_name, project_description, district_division, county, "
                       "bid_received_until_date_and, project_estimate_low_bid, type_of_work",
                       f"bid_received_until_date_and >= '{TODAY}'"),
    "USAC E-Rate": ("datahub.usac.org", "jp7a-89nd",
                    "application_number, billed_entity_name, applicant_type, billed_entity_city, billed_entity_state, "
                    "certified_datetime, allowable_contract_date, funding_year, f470_number",
                    f"f470_status='Certified' AND allowable_contract_date >= '{TODAY}'"),
}

SUBNET_URL = ("https://legacy.sba.gov/federal-contracting/contracting-guide/prime-subcontracting/"
              "subcontracting-opportunities?state=All&page=0")
USASPENDING_URL = "https://api.usaspending.gov/api/v2/references/toptier_agencies/"
ESBD_URL = "https://www.txsmartbuy.gov/app/extensions/CPA/CPAMain/1.0.0/services/ESBD.Service.ss"
ESBD_FIELDS = ("solicitationId", "title", "agencyName", "responseDue", "postingDate", "nigpCodes")


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as resp:
        return resp.read()


def check_socrata(domain: str, dataset: str, fields: str, where: str) -> str:
    """Rows with the extension's fields (a missing field makes Socrata answer 400)."""
    query = urllib.parse.urlencode({"$select": fields, "$where": where, "$limit": "5000"})
    rows = json.loads(get(f"https://{domain}/resource/{dataset}.json?{query}"))
    if not rows:
        raise RuntimeError("no open opportunity")
    return f"{len(rows)} open"


def check_subnet() -> str:
    page = get(SUBNET_URL).decode("utf-8", "replace")
    count = page.count("subnet_title")
    if not count:
        raise RuntimeError("no opportunity found in the page (layout changed?)")
    return f"{count} on the first page"


def check_esbd() -> str:
    """First page of posted solicitations, as the extension asks for it (lib/sources/esbd.js)."""
    body = json.dumps({"lines": [], "page": 1, "status": "1", "urlRoot": "esbd"}).encode()
    request = urllib.request.Request(ESBD_URL, data=body, headers={**HEADERS, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as resp:
        data = json.loads(resp.read())
    lines = data.get("lines") or []
    if not lines:
        raise RuntimeError("no open solicitation (service changed?)")
    missing = [f for f in ESBD_FIELDS if f not in lines[0]]
    if missing:
        raise RuntimeError(f"fields gone: {', '.join(missing)}")
    return f"{data.get('totalRecordsFound', len(lines))} open"


def check_usaspending() -> str:
    agencies = json.loads(get(USASPENDING_URL)).get("results", [])
    if not agencies:
        raise RuntimeError("no agency")
    return f"{len(agencies)} agencies"


def main() -> None:
    checks = {name: (lambda a=args: check_socrata(*a)) for name, args in SOCRATA.items()}
    checks["SBA SUBNet"] = check_subnet
    checks["Texas ESBD"] = check_esbd
    checks["USAspending (past awards)"] = check_usaspending

    lines, failed = [], []
    for name, check in checks.items():
        try:
            lines.append(f"| {name} | OK | {check()} |")
        except Exception as e:  # noqa: BLE001 - any error means the source needs a look
            failed.append(name)
            lines.append(f"| {name} | **FAILED** | {str(e)[:200]} |")
    report = "\n".join(["## Sources", "", "| Source | State | Detail |", "|---|---|---|", *lines])
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report + "\n")
    if failed:
        sys.exit(f"Sources to look at: {', '.join(failed)}")


if __name__ == "__main__":
    main()
