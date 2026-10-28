"""Turn heterogeneous ``RawJob`` records into validated ``JobPosting`` objects."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from jd_collector.config import get_settings
from jd_collector.experience import detect_experience_level
from jd_collector.models import JobPosting, RawJob
from jd_collector.regions import detect_region
from jd_collector.roles import detect_role_category

# --------------------------------------------------------------------------- text


_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"]


def html_to_text(html: str | None) -> str:
    """Convert HTML to readable plain text, keeping paragraph and list structure."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert(0, "• ")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")
    return clean_text(soup.get_text())


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    lines = (re.sub(r"[ \t ​]+", " ", line).strip() for line in text.splitlines())
    out, blank = [], False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


# --------------------------------------------------------------------------- ids / urls

_TRACKING_PARAMS = re.compile(r"^(utm_.*|gh_src|source|ref|lever-source.*|src)$", re.I)


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", query, ""))


def make_job_id(source: str, external_id: str | None, url: str | None) -> str:
    """Stable unique id: hash of source + external id (falls back to the canonical URL)."""
    key = external_id or canonical_url(url) or ""
    return hashlib.sha1(f"{source}|{key}".encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- skills

# (canonical name, regex, case sensitive). Boundaries are added automatically.
_SKILL_DEFS: list[tuple[str, str, bool]] = [
    # languages
    ("Python", r"python", False), ("Java", r"java", False), ("JavaScript", r"javascript|js", False),
    ("TypeScript", r"typescript", False), ("Go", r"[Gg]olang|Go(?=\s*(?:,|/|\)|and\b|or\b|lang))", True),
    ("Rust", r"rust", False), ("C++", r"c\+\+|cpp", False), ("C#", r"c#|c sharp", False),
    ("Ruby", r"ruby", False), ("PHP", r"php", False), ("Scala", r"scala", False),
    ("Kotlin", r"kotlin", False), ("Swift", r"swift", False), ("Objective-C", r"objective-c", False),
    ("R", r"R(?=\s*(?:,|/|\)|and\b|or\b))", True), ("SQL", r"sql", False), ("Bash", r"bash|shell scripting", False),
    ("Elixir", r"elixir", False), ("Haskell", r"haskell", False), ("Dart", r"dart", False),
    ("Solidity", r"solidity", False), ("MATLAB", r"matlab", False), ("Perl", r"perl", False),
    # frontend / mobile
    ("React", r"react(?:\.js|js)?", False), ("React Native", r"react native", False),
    ("Angular", r"angular(?:js)?", False), ("Vue.js", r"vue(?:\.js|js)?", False), ("Next.js", r"next\.js|nextjs", False),
    ("Svelte", r"svelte", False), ("HTML", r"html5?", False), ("CSS", r"css3?", False),
    ("Tailwind CSS", r"tailwind(?: css)?", False), ("Redux", r"redux", False), ("Flutter", r"flutter", False),
    ("iOS", r"ios", False), ("Android", r"android", False), ("GraphQL", r"graphql", False),
    # backend frameworks
    ("Node.js", r"node(?:\.js|js)?", False), ("Django", r"django", False), ("Flask", r"flask", False),
    ("FastAPI", r"fastapi", False), ("Spring", r"spring(?: boot)?", False), ("Ruby on Rails", r"rails|ruby on rails", False),
    (".NET", r"\.net|dotnet|asp\.net", False), ("Express", r"express(?:\.js|js)", False),
    ("gRPC", r"grpc", False), ("REST APIs", r"rest(?:ful)? apis?", False), ("Microservices", r"microservices?", False),
    # data stores / streaming
    ("PostgreSQL", r"postgres(?:ql)?", False), ("MySQL", r"mysql", False), ("MongoDB", r"mongo(?:db)?", False),
    ("Redis", r"redis", False), ("Elasticsearch", r"elasticsearch|elastic search", False),
    ("Cassandra", r"cassandra", False), ("DynamoDB", r"dynamodb", False), ("Snowflake", r"snowflake", False),
    ("BigQuery", r"bigquery", False), ("Redshift", r"redshift", False), ("Kafka", r"kafka", False),
    ("RabbitMQ", r"rabbitmq", False), ("Spark", r"(?:apache )?spark|pyspark", False), ("Hadoop", r"hadoop", False),
    ("Airflow", r"airflow", False), ("dbt", r"dbt", False), ("Databricks", r"databricks", False),
    ("NoSQL", r"nosql", False),
    # cloud / devops
    ("AWS", r"aws|amazon web services", False), ("GCP", r"gcp|google cloud(?: platform)?", False),
    ("Azure", r"azure", False), ("Docker", r"docker", False), ("Kubernetes", r"kubernetes|k8s", False),
    ("Terraform", r"terraform", False), ("Ansible", r"ansible", False), ("Jenkins", r"jenkins", False),
    ("CI/CD", r"ci/cd|ci ?/ ?cd|continuous integration", False), ("Linux", r"linux|unix", False),
    ("Git", r"git", False), ("Prometheus", r"prometheus", False), ("Grafana", r"grafana", False),
    ("Helm", r"helm", False),
    # data science / AI
    ("Machine Learning", r"machine learning|ml", False), ("Deep Learning", r"deep learning", False),
    ("NLP", r"nlp|natural language processing", False), ("Computer Vision", r"computer vision", False),
    ("LLMs", r"llms?|large language models?", False), ("Generative AI", r"generative ai|genai|gen ai", False),
    ("PyTorch", r"pytorch", False), ("TensorFlow", r"tensorflow", False), ("scikit-learn", r"scikit-learn|sklearn", False),
    ("Pandas", r"pandas", False), ("NumPy", r"numpy", False), ("Statistics", r"statistics|statistical", False),
    ("Data Analysis", r"data analysis|data analytics", False), ("Tableau", r"tableau", False),
    ("Power BI", r"power ?bi", False), ("Looker", r"looker", False), ("Excel", r"(?:Microsoft |MS )?Excel(?! (?:at|in|as|with|when|on)\b)|excel (?:spreadsheets?|models?|modeling)", True),
    # practices / other
    ("Agile", r"agile|scrum", False), ("System Design", r"system design|distributed systems", False),
    ("Security", r"cyber ?security|information security|appsec", False), ("Figma", r"figma", False),
    ("Salesforce", r"salesforce", False), ("SAP", r"sap", True), ("Jira", r"jira", False),
    ("Product Management", r"product management", False), ("SEO", r"seo", False),
]

_SKILL_PATTERNS = [
    (name, re.compile(rf"(?<![A-Za-z0-9+#.])(?:{pattern})(?![A-Za-z0-9+#])", 0 if cs else re.IGNORECASE))
    for name, pattern, cs in _SKILL_DEFS
]


def extract_skills(text: str, extra: list[str] | None = None) -> list[str]:
    found = {name for name, rx in _SKILL_PATTERNS if rx.search(text or "")}
    for skill in extra or []:
        skill = (skill or "").strip()
        if skill and len(skill) <= 60:
            found.add(skill)
    return sorted(found, key=str.lower)


# --------------------------------------------------------------------------- job type / remote

_JOB_TYPE_RULES = [
    ("Internship", re.compile(r"\bintern(ship)?s?\b|\bco-?op\b|\btrainee\b", re.I)),
    ("Temporary", re.compile(r"\btemp(orary)?\b|\bseasonal\b|\bfixed[- ]term\b", re.I)),
    ("Contract", re.compile(
        r"(?<!smart )\bcontract(or)?\b(?!s? (success|management|manager|negotiat|admin|specialist|analyst|lawyer|counsel))"
        r"|\bfreelance\b", re.I)),
    ("Part-time", re.compile(r"\bpart[-_ ]?time\b|\bparttime\b", re.I)),
    ("Full-time", re.compile(r"\bfull[-_ ]?time\b|\bfulltime\b|\bpermanent\b|\bregular\b", re.I)),
]

# Descriptions mention words like "contracts" or "regular" casually, so only explicit
# phrases about the role itself count there.
_DESCRIPTION_TYPE_RULES = [
    ("Internship", re.compile(r"\b(this|the|our) (summer )?internship\b|\binternship (program|position|role)\b", re.I)),
    ("Contract", re.compile(r"\bcontract(-to-hire)? (role|position|opportunity|assignment)\b|\b\d+[- ]month contract\b", re.I)),
    ("Temporary", re.compile(r"\bfixed[- ]term (contract|role|position)\b|\btemporary (role|position)\b", re.I)),
    ("Part-time", re.compile(r"\bpart[- ]time (role|position|job|opportunity)\b|\bthis is a part[- ]time\b", re.I)),
    ("Full-time", re.compile(r"\bfull[- ]time (role|position|job|opportunity|employee|employment)\b|\bthis is a full[- ]time\b", re.I)),
]


def detect_job_type(employment_type: str | None, title: str | None, description: str = "") -> str | None:
    """Prefer the structured field, then the title, then explicit phrases in the description."""
    for text in (employment_type, title):
        if text:
            for label, rx in _JOB_TYPE_RULES:
                if rx.search(text):
                    return label
    for label, rx in _DESCRIPTION_TYPE_RULES:
        if rx.search(description or ""):
            return label
    return None


_REMOTE_RX = re.compile(r"\b(remote|work from home|wfh|anywhere|telecommute|distributed)\b", re.I)


def detect_remote(flag: bool | None, location: str | None, title: str | None) -> bool:
    if flag is not None:
        return bool(flag)
    return bool(_REMOTE_RX.search(location or "") or _REMOTE_RX.search(title or ""))


# --------------------------------------------------------------------------- dates


def parse_date(value: Any) -> datetime | None:
    """Accept epoch seconds/milliseconds, ISO strings, or datetimes; return naive UTC."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            num = float(value)
            dt = datetime.fromtimestamp(num / 1000 if num > 1e11 else num, tz=timezone.utc)
        else:
            dt = date_parser.parse(str(value))
    except (ValueError, OverflowError, OSError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if dt.year < 2000 or dt > datetime.utcnow() + timedelta(days=366):
        return None
    return dt


# --------------------------------------------------------------------------- salary

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY", "C$": "CAD", "A$": "AUD"}
_CUR = r"(?:C\$|A\$|[$€£₹¥]|USD|EUR|GBP|INR|CAD|AUD|SGD|CHF|JPY)"
_NUM = r"\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SALARY_RX = re.compile(
    rf"(?P<cur>{_CUR})\s?(?P<min>{_NUM})\s?(?P<mink>[kKmM])?"
    rf"\s*(?:-|–|—|to)\s*(?:(?P<cur2>{_CUR})\s?)?(?P<max>{_NUM})\s?(?P<maxk>[kKmM])?"
    rf"(?:\s?(?P<cur3>USD|EUR|GBP|INR|CAD|AUD|SGD|CHF|JPY))?"
)
_INTERVALS = [
    ("hour", re.compile(r"per hour|/\s?h(ou)?r|hourly|an hour", re.I)),
    ("day", re.compile(r"per day|/\s?day|daily", re.I)),
    ("week", re.compile(r"per week|/\s?w(ee)?k|weekly", re.I)),
    ("month", re.compile(r"per month|/\s?mo(nth)?|monthly", re.I)),
    ("year", re.compile(r"per year|/\s?y(ea)?r|annual|annually|per annum|p\.a\.|yearly", re.I)),
]
_INTERVAL_ALIASES = {
    "hour": "hour", "hourly": "hour", "1 hour": "hour", "per-hour-wage": "hour",
    "day": "day", "daily": "day", "1 day": "day",
    "week": "week", "weekly": "week", "1 week": "week",
    "month": "month", "monthly": "month", "1 month": "month", "per-month-salary": "month",
    "year": "year", "yearly": "year", "annual": "year", "1 year": "year", "per-year-salary": "year",
}


def _to_number(raw: str, suffix: str | None) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):  # European thousands separator: 120.000
        raw = raw.replace(".", "")
    value = float(raw.replace(",", ""))
    if suffix and suffix.lower() == "k":
        value *= 1_000
    elif suffix and suffix.lower() == "m":
        value *= 1_000_000
    return value


def normalize_interval(value: str | None) -> str | None:
    if not value:
        return None
    return _INTERVAL_ALIASES.get(str(value).strip().lower().replace("_", " "))


def parse_salary_text(text: str) -> dict[str, Any] | None:
    """Find the first salary range like "$120,000 - $150,000 per year" or "€60k–80k"."""
    if not text:
        return None
    match = _SALARY_RX.search(text)
    if not match:
        return None
    lo = _to_number(match["min"], match["mink"] or match["maxk"])
    hi = _to_number(match["max"], match["maxk"])
    if lo <= 0 or hi < lo:
        return None
    cur_raw = match["cur"] or match["cur2"] or match["cur3"]
    currency = _CURRENCY_SYMBOLS.get(cur_raw, cur_raw)
    tail = text[match.end(): match.end() + 40]
    interval = next((name for name, rx in _INTERVALS if rx.search(tail)), None)
    if interval is None:
        interval = "hour" if hi < 500 else "year"
    return {"min": lo, "max": hi, "currency": currency, "interval": interval, "text": match.group(0).strip()}


def format_salary(lo: float | None, hi: float | None, currency: str | None, interval: str | None) -> str | None:
    if lo is None and hi is None:
        return None

    def fmt(v: float) -> str:
        return f"{v:,.0f}" if v >= 100 else f"{v:,.2f}"

    amount = fmt(lo) if hi is None or lo == hi else (fmt(hi) if lo is None else f"{fmt(lo)} - {fmt(hi)}")
    parts = [currency or "", amount]
    text = " ".join(p for p in parts if p)
    return f"{text} per {interval}" if interval else text


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- main entry


def normalize(raw: RawJob, store_raw: bool | None = None) -> tuple[JobPosting | None, list[str]]:
    """Return (posting, issues). ``posting`` is None when the record fails validation."""
    settings = get_settings()
    store_raw = settings.store_raw if store_raw is None else store_raw
    issues: list[str] = []

    title = clean_text(raw.title).replace("\n", " ")
    company = clean_text(raw.company).replace("\n", " ")
    apply_link = canonical_url(raw.apply_url) or canonical_url(raw.url)
    description = clean_text(raw.description_text) if raw.description_text else html_to_text(raw.description_html)

    if not title:
        issues.append("missing title")
    if not company:
        issues.append("missing company")
    if not apply_link:
        issues.append("missing or invalid apply link")
    if len(description) < settings.min_description_length:
        issues.append(f"description shorter than {settings.min_description_length} chars")
    if issues:
        return None, issues

    location = clean_text(raw.location).replace("\n", "; ") or None

    salary = dict(raw.salary or {})
    lo, hi = _num(salary.get("min")), _num(salary.get("max"))
    currency = (salary.get("currency") or "").upper() or None
    interval = normalize_interval(salary.get("interval"))
    salary_text = salary.get("text")
    if lo is None and hi is None:
        parsed = parse_salary_text(salary_text or "") or parse_salary_text(description)
        if parsed:
            lo, hi, currency, interval = parsed["min"], parsed["max"], parsed["currency"], parsed["interval"]
            salary_text = salary_text or parsed["text"]
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    salary_display = format_salary(lo, hi, currency, interval) or (salary_text or None)
    is_remote = detect_remote(raw.remote, location, title)

    posting = JobPosting(
        job_id=make_job_id(raw.source, raw.external_id, raw.url or raw.apply_url),
        source=raw.source,
        external_id=raw.external_id,
        title=title[:500],
        company=company[:200],
        location=location[:500] if location else None,
        is_remote=is_remote,
        region=detect_region(location, is_remote),
        role_category=detect_role_category(title, description),
        experience_level=detect_experience_level(title, description),
        description=description,
        # A company's own name (e.g. "Databricks" at Databricks) is not a skill requirement.
        skills=[s for s in extract_skills(f"{title}\n{description}", raw.extra_skills) if s.lower() != company.lower()],
        salary=salary_display,
        salary_min=lo,
        salary_max=hi,
        salary_currency=currency,
        salary_interval=interval,
        job_type=detect_job_type(raw.employment_type, title, description),
        department=clean_text(raw.department).replace("\n", " ") or None,
        posted_date=parse_date(raw.posted_at),
        apply_link=apply_link,
        source_marker=str(raw.marker) if raw.marker is not None else None,
        raw=raw.raw if store_raw else None,
    )
    return posting, issues
