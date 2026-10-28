from datetime import datetime

from jd_collector.models import RawJob
from jd_collector.normalize import (
    canonical_url, detect_job_type, extract_skills, html_to_text, make_job_id, normalize, parse_date,
    parse_salary_text,
)


def test_html_to_text_keeps_structure():
    text = html_to_text("<p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul><script>x()</script>")
    assert text.splitlines() == ["Hello world", "• One", "• Two"]


def test_extract_skills_handles_symbols_and_boundaries():
    text = "We use Python, C++, C#, Node.js and PostgreSQL on AWS. Go, Rust and k8s too. NoSQL nice."
    skills = extract_skills(text)
    for expected in ["Python", "C++", "C#", "Node.js", "PostgreSQL", "AWS", "Go", "Rust", "Kubernetes", "NoSQL"]:
        assert expected in skills
    # "SQL" must not be found inside "PostgreSQL"/"NoSQL"; "Java" not inside "JavaScript"
    assert "SQL" not in skills
    assert "Java" not in extract_skills("Strong JavaScript skills")
    assert "Go" not in extract_skills("You will go to market with us")
    assert "Excel" not in extract_skills("You excel at communication. Excel at ambiguity.")
    assert "Excel" in extract_skills("Advanced Excel and SQL skills")


def test_extract_skills_adds_extra():
    assert "Observability" in extract_skills("nothing", ["Observability", ""])


def test_detect_job_type():
    assert detect_job_type("FULL_TIME", None) == "Full-time"
    assert detect_job_type("FullTime", None) == "Full-time"
    assert detect_job_type(None, "Software Engineering Intern") == "Internship"
    assert detect_job_type(None, "Contract iOS Developer") == "Contract"
    assert detect_job_type("Part time", "Barista") == "Part-time"
    assert detect_job_type(None, "Engineer", "no hints") is None
    # casual wording in descriptions must not decide the type
    assert detect_job_type(None, "Account Executive", "Help close contracts with regular customers") is None
    assert detect_job_type(None, "Technical Solutions Consultant") is None
    assert detect_job_type(None, "Software Engineer - Smart Contract") is None
    assert detect_job_type(None, "Contract Success Specialist") is None
    assert detect_job_type(None, "Recruiter (Fixed-Term Contract)") == "Temporary"
    assert detect_job_type(None, "Recruiter", "This is a 12-month contract based in Dublin") == "Contract"


def test_parse_salary_text():
    s = parse_salary_text("The annual salary range is $180,000 - $250,000 USD.")
    assert (s["min"], s["max"], s["currency"], s["interval"]) == (180000, 250000, "USD", "year")
    s = parse_salary_text("Pay: €60k–80k per year")
    assert (s["min"], s["max"], s["currency"]) == (60000, 80000, "EUR")
    s = parse_salary_text("$45 - $60 per hour")
    assert s["interval"] == "hour"
    assert parse_salary_text("We have 5 - 10 engineers") is None


def test_parse_date_variants():
    assert parse_date(1758000000000) == datetime(2025, 9, 16, 5, 20)
    assert parse_date("2026-09-01T09:00:00-04:00") == datetime(2026, 9, 1, 13, 0)
    assert parse_date("not a date") is None
    assert parse_date(None) is None


def test_canonical_url_strips_tracking_and_rejects_unsafe():
    assert canonical_url("https://Example.com/jobs/1/?utm_source=x&id=5&gh_src=y") == "https://example.com/jobs/1?id=5"
    assert canonical_url("javascript:alert(1)") is None
    assert canonical_url("/relative") is None


def test_job_id_is_stable():
    assert make_job_id("s", "1", "https://a.com") == make_job_id("s", "1", "https://b.com")
    assert make_job_id("s", None, "https://a.com/x?utm_source=1") == make_job_id("s", None, "https://a.com/x")


def test_normalize_validates_required_fields():
    posting, issues = normalize(RawJob(source="s", company="Acme", title="", url="https://a.com/1",
                                       description_text="x" * 100))
    assert posting is None and "missing title" in issues
    posting, issues = normalize(RawJob(source="s", company="Acme", title="Dev", url="https://a.com/1",
                                       description_text="short"))
    assert posting is None


def test_normalize_full_record():
    raw = RawJob(
        source="s", company="Acme", external_id="42", title="Remote Senior Python Developer",
        url="https://acme.com/jobs/42", description_html="<p>Work with Django and Docker. Salary $120k - $150k.</p>",
        employment_type="Full-time", posted_at="2026-10-01",
    )
    posting, issues = normalize(raw, store_raw=False)
    assert issues == []
    assert posting.is_remote is True
    assert posting.region == "Remote / Global"  # no location given, but is_remote is True
    assert posting.role_category == "Engineering"
    assert posting.job_type == "Full-time"
    assert {"Python", "Django", "Docker"} <= set(posting.skills)
    assert (posting.salary_min, posting.salary_max, posting.salary_currency) == (120000, 150000, "USD")
    assert posting.salary == "USD 120,000 - 150,000 per year"
    assert posting.posted_date == datetime(2026, 10, 1)


def test_normalize_derives_region_and_role_from_location_and_title():
    raw = RawJob(
        source="s", company="Acme", title="Senior Data Scientist", url="https://acme.com/jobs/7",
        location="Berlin, Germany", description_text="x" * 100,
    )
    posting, issues = normalize(raw, store_raw=False)
    assert issues == []
    assert posting.region == "Europe"
    assert posting.role_category == "Data & AI"
