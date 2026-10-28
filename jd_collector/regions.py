"""Best-effort region classification from a job's free-text location.

Not authoritative — a location string like "Hybrid" or "APAC" carries real ambiguity,
and this makes a reasonable, documented choice rather than leaving everything unclassified:

- Explicit shorthand (EMEA, APAC, LATAM, AMER/Americas) is trusted directly. EMEA is mapped
  to Europe (not Middle East & Africa) since most EMEA-tagged roles at the companies this
  project targets are based in Europe; this is a simplification, not a guarantee.
- A recognized country name (incl. common abbreviations like "US", "UK", "UAE") wins next.
- A recognized US state name/abbreviation counts as North America.
- A recognized city (without a country given) counts next.
- "Remote" / "Global" / "Worldwide" with no other signal becomes "Remote / Global".
- Otherwise the region is left as None ("Not specified") rather than guessed.
"""

from __future__ import annotations

import re

REGIONS = ("North America", "Latin America", "Europe", "Middle East & Africa", "Asia Pacific", "Remote / Global")

# --------------------------------------------------------------------------- explicit shorthand

_HINTS = [
    ("Europe", re.compile(r"\bEMEA\b")),
    ("North America", re.compile(r"\bAMER\b|\bAmericas\b")),
    ("Asia Pacific", re.compile(r"\bAPAC\b|\bAsia[- ]Pacific\b")),
    ("Latin America", re.compile(r"\bLATAM\b|\bLatam\b|\bLatin America\b")),
]

# --------------------------------------------------------------------------- countries

_COUNTRIES: dict[str, tuple[str, ...]] = {
    "North America": ("United States", "USA", "U.S.A.", "U.S.", "Canada"),
    "Latin America": (
        "Mexico", "Brazil", "Brasil", "Argentina", "Chile", "Colombia", "Peru", "Ecuador",
        "Uruguay", "Paraguay", "Bolivia", "Venezuela", "Costa Rica", "Panama", "Guatemala",
        "Honduras", "El Salvador", "Nicaragua", "Dominican Republic", "Puerto Rico", "Cuba",
    ),
    "Europe": (
        "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland",
        "Germany", "France", "Spain", "Italy", "Portugal", "Netherlands", "Belgium",
        "Switzerland", "Austria", "Ireland", "Sweden", "Norway", "Denmark", "Finland",
        "Iceland", "Poland", "Czech Republic", "Czechia", "Slovakia", "Hungary", "Romania",
        "Bulgaria", "Greece", "Croatia", "Slovenia", "Serbia", "Estonia", "Latvia",
        "Lithuania", "Luxembourg", "Malta", "Cyprus", "Ukraine", "Moldova", "Albania",
        "Bosnia", "Montenegro", "North Macedonia", "Monaco", "Liechtenstein",
    ),
    "Middle East & Africa": (
        "United Arab Emirates", "Israel", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain",
        "Oman", "Jordan", "Lebanon", "Turkey", "Egypt", "South Africa", "Nigeria", "Kenya",
        "Morocco", "Tunisia", "Algeria", "Ghana", "Ethiopia", "Rwanda", "Uganda", "Tanzania",
        "Senegal", "Ivory Coast", "Botswana", "Namibia", "Zambia", "Zimbabwe",
    ),
    "Asia Pacific": (
        "India", "China", "Japan", "Singapore", "Australia", "New Zealand", "South Korea",
        "Korea", "Indonesia", "Malaysia", "Thailand", "Vietnam", "Philippines", "Hong Kong",
        "Taiwan", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Cambodia", "Myanmar",
        "Mongolia", "Fiji",
    ),
}
# Short codes need a case-sensitive, word-bounded match (lowercase "us"/"in" are common words).
_SHORT_CODES: dict[str, tuple[str, ...]] = {
    "North America": ("US", "USA"),
    "Europe": ("UK",),
    "Middle East & Africa": ("UAE",),
}

_country_patterns: list[tuple[str, re.Pattern]] = []
for region, names in _COUNTRIES.items():
    for name in sorted(names, key=len, reverse=True):  # longest first: "United Arab Emirates" before "United"
        _country_patterns.append((region, re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)))
for region, codes in _SHORT_CODES.items():
    for code in codes:
        _country_patterns.append((region, re.compile(rf"\b{re.escape(code)}\b")))  # case-sensitive

# --------------------------------------------------------------------------- US states

_US_STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
)
_US_STATE_CODES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
)
_us_state_rx = re.compile(
    "|".join([rf"\b{re.escape(s)}\b" for s in _US_STATES] + [rf"\b{c}\b" for c in _US_STATE_CODES])
)

# --------------------------------------------------------------------------- cities (no country given)

_CITIES: dict[str, tuple[str, ...]] = {
    "North America": (
        "San Francisco", "New York City", "Los Angeles", "Seattle", "Austin", "Boston",
        "Chicago", "Denver", "Atlanta", "Miami", "Toronto", "Vancouver", "Montreal",
        "Ottawa", "San Diego", "Portland", "Philadelphia", "Houston", "Dallas", "Phoenix",
        "Menlo Park", "Mountain View", "Palo Alto", "San Jose, CA", "Brooklyn",
    ),
    "Latin America": (
        "Sao Paulo", "São Paulo", "Rio de Janeiro", "Mexico City", "Bogota", "Bogotá",
        "Buenos Aires", "Santiago", "Lima", "Montevideo", "San Jose, Costa Rica", "Medellin",
    ),
    "Europe": (
        "London", "Dublin", "Berlin", "Munich", "Hamburg", "Frankfurt", "Paris", "Amsterdam",
        "Madrid", "Barcelona", "Lisbon", "Warsaw", "Krakow", "Stockholm", "Copenhagen",
        "Helsinki", "Oslo", "Zurich", "Geneva", "Vienna", "Prague", "Bucharest", "Athens",
        "Rome", "Milan", "Brussels", "Riga", "Vilnius", "Tallinn", "Budapest", "Sofia",
    ),
    "Middle East & Africa": (
        "Tel Aviv", "Dubai", "Abu Dhabi", "Riyadh", "Doha", "Cairo", "Johannesburg",
        "Cape Town", "Lagos", "Nairobi", "Casablanca", "Herzliya",
    ),
    "Asia Pacific": (
        "Bengaluru", "Bangalore", "Mumbai", "New Delhi", "Delhi", "Hyderabad", "Pune",
        "Gurugram", "Gurgaon", "Chennai", "Noida", "Kolkata", "Singapore", "Tokyo", "Osaka",
        "Seoul", "Shanghai", "Beijing", "Shenzhen", "Hong Kong", "Sydney", "Melbourne",
        "Brisbane", "Perth", "Auckland", "Wellington", "Jakarta", "Manila", "Kuala Lumpur",
        "Bangkok", "Ho Chi Minh City", "Hanoi", "Taipei",
    ),
}
_city_patterns = [
    (region, re.compile(rf"\b{re.escape(city)}\b", re.IGNORECASE))
    for region, cities in _CITIES.items()
    for city in sorted(cities, key=len, reverse=True)
]

_remote_rx = re.compile(r"\b(remote|global|worldwide|anywhere|distributed)\b", re.IGNORECASE)


def detect_region(location: str | None, is_remote: bool = False) -> str | None:
    text = (location or "").strip()
    if not text:
        return "Remote / Global" if is_remote else None
    for region, rx in _HINTS:
        if rx.search(text):
            return region
    for region, rx in _country_patterns:
        if rx.search(text):
            return region
    if _us_state_rx.search(text):
        return "North America"
    for region, rx in _city_patterns:
        if rx.search(text):
            return region
    if _remote_rx.search(text):
        return "Remote / Global"
    return "Remote / Global" if is_remote else None
