"""Best-effort role-category classification from a job title (and, as a fallback, its description).

Like job-type detection in normalize.py, this is a readable heuristic, not a model: an
ordered list of regex rules, most specific first, so a compound title like "Sales Engineer"
or "Data Engineer" is caught by its specific rule before the broad "Engineering" catch-all
claims every title containing the word "engineer". Titles that match nothing stay
unclassified (None) rather than being guessed into the wrong bucket.

A single generic word (bare "design", "engineer") is a strong signal in a four-word title but
a weak one buried in a long description, where ordinary sentences ("design and implement
processes", "reverse-engineer the issue") use the same words as plain verbs. Those few
catch-alls are checked against the title only; every other rule here is specific enough
(a two-word phrase, an abbreviation with its own meaning) to check against both.
"""

from __future__ import annotations

import re

ROLE_CATEGORIES = (
    "Engineering", "Data & AI", "Product", "Design", "Sales & Business Development",
    "Marketing & Communications", "Customer Support & Success", "People & Talent",
    "Finance & Accounting", "Legal & Compliance", "Operations",
)

# Ordered most-specific-first. Checked against the title, then (if nothing matched) the
# start of the description.
_RULES: tuple[tuple[str, str], ...] = (
    ("People & Talent", r"\b(recruit(er|ing|ment)?|talent (acquisition|partner)|people (ops|operations|partner|team)|human resources|\bhr\b|compensation (&|and) benefits|benefits (specialist|analyst))\b"),
    ("Legal & Compliance", r"\b(legal counsel|general counsel|attorney|paralegal|compliance (officer|analyst|manager)|contracts? manager|privacy counsel|regulatory affairs)\b"),
    ("Finance & Accounting", r"\b(finance|financial analyst|accounting|accountant|controller|treasury|payroll|fp&a|bookkeep(er|ing)|tax (analyst|manager|specialist))\b"),
    ("Marketing & Communications", r"\b(marketing|brand (manager|strategist)|content marketing|growth marketing|\bseo\b|social media|communications?|public relations|\bpr\b manager|demand generation|campaign manager|copywriter)\b"),
    ("Customer Support & Success", r"\b(customer (support|success|service|experience|care)|support (specialist|agent|associate|engineer)|technical support|help ?desk|\bcsm\b)\b"),
    ("Sales & Business Development", r"\b(sales|account executive|account manager|business development|\bbdr\b|\bsdr\b|partnerships?|sales engineer|solutions engineer|revenue (operations|manager))\b"),
    ("Product", r"\b(product manager|product management|product owner|product lead|group product manager|associate product manager)\b"),
    ("Design", r"\b(designer|\bux\b|\bui\b|user experience|user research(er)?|graphic design|visual design)\b"),
    ("Data & AI", r"\b(data scientist|data engineer|data analyst|machine learning|\bml\b engineer|\bai\b engineer|analytics engineer|research scientist|applied scientist|business intelligence|\bbi\b analyst|data platform)\b"),
    ("Engineering", r"\b(software engineer|backend|front[- ]?end|full[- ]?stack|\bswe\b|developer|platform engineer|infrastructure engineer|site reliability|devops|security engineer|qa engineer|test engineer|mobile engineer|ios engineer|android engineer|embedded engineer)\b"),
    ("Operations", r"\b(operations? (manager|analyst|associate|lead)|\bops\b|supply chain|logistics|warehouse|fulfillment|program manager|project manager|business operations|strategy (&|and) operations|facilities)\b"),
)
_patterns = [(category, re.compile(pattern, re.IGNORECASE)) for category, pattern in _RULES]

# Checked against the title only - see the module docstring.
_TITLE_ONLY_RULES: tuple[tuple[str, str], ...] = (
    ("Design", r"\bdesign\b"),
    ("Engineering", r"\b(engineer|engineering)\b"),
)
_title_only_patterns = [(category, re.compile(pattern, re.IGNORECASE)) for category, pattern in _TITLE_ONLY_RULES]


def detect_role_category(title: str | None, description: str = "") -> str | None:
    # The title is checked exhaustively - specific rules, then the broad title-only ones -
    # before the description is ever consulted. A long description's boilerplate (benefits
    # text, a company blurb) can otherwise trip an early, unrelated rule for a title that
    # already said plainly what the role is (e.g. a "finance" mention in the perks section
    # outvoting a title that said "Software Engineering Intern").
    if title:
        for category, rx in _patterns:
            if rx.search(title):
                return category
        for category, rx in _title_only_patterns:
            if rx.search(title):
                return category
    if description:
        text = description[:600]
        for category, rx in _patterns:
            if rx.search(text):
                return category
    return None
