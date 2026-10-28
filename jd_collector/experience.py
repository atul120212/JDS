"""Best-effort experience-level classification from a job's title and description.

Looks for an explicit years-of-experience statement ("3-5 years", "5+ yrs", "fresher",
"entry level", "minimum 2 years", ...) in the title and the start of the description, and
buckets it. A posting that states nothing recognizable about experience is left
unclassified (None) rather than guessed - plenty of postings (especially outside India's IT
services industry) never state a number at all.
"""

from __future__ import annotations

import re

EXPERIENCE_LEVELS = ("Fresher / 0-1 yr", "1-3 yrs", "3-5 yrs", "5-8 yrs", "8-12 yrs", "12+ yrs")

_YR = r"(?:years?|yrs?)"

_FRESHER_RX = re.compile(
    rf"\b(freshers?|entry[- ]level|no (?:prior |relevant )?experience (?:required|needed|necessary)?|"
    rf"campus hire|graduate trainee|intern(?:ship)?s?|0\s*(?:-|–|to)\s*1\s*{_YR})\b", re.I,
)
# Checked in this order: a range ("3-5 years") and an explicit minimum ("minimum 2 years",
# "at least 2 yrs") are the most specific; "X+ years" next; a bare "X years of experience"
# last, since it's the loosest pattern and most likely to pick up an unrelated number.
_RANGE_RX = re.compile(rf"\b(\d{{1,2}})\s*(?:-|–|to)\s*(\d{{1,2}})\s*{_YR}\b", re.I)
_MIN_RX = re.compile(rf"\b(?:minimum(?:\s*of)?|at least)\s*(\d{{1,2}})\+?\s*{_YR}\b", re.I)
_PLUS_RX = re.compile(rf"\b(\d{{1,2}})\s*\+\s*{_YR}\b", re.I)
_EXACT_RX = re.compile(rf"\b(\d{{1,2}})\s*{_YR}\s*(?:of\s*)?(?:relevant\s*)?experience\b", re.I)


def _bucket(min_years: float) -> str:
    if min_years < 1:
        return "Fresher / 0-1 yr"
    if min_years < 3:
        return "1-3 yrs"
    if min_years < 5:
        return "3-5 yrs"
    if min_years < 8:
        return "5-8 yrs"
    if min_years < 12:
        return "8-12 yrs"
    return "12+ yrs"


def detect_experience_level(title: str | None, description: str = "") -> str | None:
    text = f"{title or ''}\n{(description or '')[:1500]}"
    if _FRESHER_RX.search(text):
        return "Fresher / 0-1 yr"
    for rx in (_RANGE_RX, _MIN_RX, _PLUS_RX, _EXACT_RX):
        m = rx.search(text)
        if not m:
            continue
        nums = [float(g) for g in m.groups() if g]
        if nums:
            return _bucket(min(nums))
    return None
