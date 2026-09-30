"""Shared data structures."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordRule:
    """One keyword from config.yaml."""

    text: str
    weight: float = 1.0
    title_only: bool = False


@dataclass
class Offer:
    """One contract opportunity, whatever the source."""

    notice_id: str
    title: str
    agency: str = ""
    sub_agency: str = ""
    type: str = ""
    posted_date: str = ""  # "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
    deadline: str = ""
    naics: str = ""
    set_aside: str = ""
    place: str = ""
    contact_name: str = ""
    contact_email: str = ""
    url: str = ""
    description: str = ""
    solicitation_number: str = ""
    archive_date: str = ""  # SAM.gov stops showing the offer after this date


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def group_key(offer: Offer) -> str:
    """Key shared by every version (amendments, reposts) of the same opportunity.

    Uses the solicitation number when there is one, else title + agency.
    The agency is always part of the key: short numbers like "00307" are reused.
    """
    agency = _normalize(offer.agency)
    if offer.solicitation_number.strip():
        return f"sol:{_normalize(offer.solicitation_number)}|{agency}"
    return f"title:{_normalize(offer.title)}|{agency}"
