from conftest import load_fixture

from jd_collector.config import SourceConfig
from jd_collector.normalize import normalize
from jd_collector.scrapers import SCRAPERS, build_scraper


def scrape(fake_client, source, routes, known=None):
    client = fake_client(routes)
    scraper = build_scraper(source, client, known)
    return list(scraper.fetch_jobs()), scraper, client


def test_registry_has_all_types():
    assert {"greenhouse", "lever", "ashby", "smartrecruiters", "jsonld", "css", "accenture"} <= set(SCRAPERS)


def test_greenhouse(fake_client):
    src = SourceConfig(name="stripe", type="greenhouse", company="Stripe", options={"board_token": "stripe"})
    jobs, _, _ = scrape(fake_client, src, {"https://boards-api.greenhouse.io/v1/boards/stripe/jobs": load_fixture("greenhouse.json")})
    assert len(jobs) == 3
    posting, _ = normalize(jobs[0])
    assert posting.title == "Senior Backend Engineer, Payments"
    assert posting.location == "San Francisco, CA"
    assert posting.job_type == "Full-time"
    assert posting.department == "Engineering"
    assert {"Java", "Go", "Ruby", "AWS", "Kafka", "PostgreSQL"} <= set(posting.skills)
    assert (posting.salary_min, posting.salary_max) == (180000, 250000)
    assert posting.apply_link == "https://stripe.com/jobs/listing/senior-backend-engineer/4012345"
    intern, _ = normalize(jobs[1])
    assert intern.job_type == "Internship" and intern.is_remote
    assert normalize(jobs[2])[0] is None  # missing title


def test_lever(fake_client):
    src = SourceConfig(name="palantir", type="lever", company="Palantir", options={"site": "palantir"})
    jobs, _, _ = scrape(fake_client, src, {"https://api.lever.co/v0/postings/palantir": load_fixture("lever.json")})
    posting, _ = normalize(jobs[0])
    assert posting.company == "Palantir"
    assert posting.is_remote is False
    assert posting.salary == "GBP 70,000 - 95,000 per year"
    assert {"TypeScript", "Java", "Docker", "Kubernetes"} <= set(posting.skills)
    assert posting.posted_date.year == 2025
    assert posting.apply_link.endswith("/apply")


def test_ashby_skips_unlisted(fake_client):
    src = SourceConfig(name="ramp", type="ashby", company="Ramp", options={"board": "ramp"})
    jobs, _, _ = scrape(fake_client, src, {"https://api.ashbyhq.com/posting-api/job-board/ramp": load_fixture("ashby.json")})
    assert len(jobs) == 1
    posting, _ = normalize(jobs[0])
    assert posting.location == "New York, NY; Remote (US)"
    assert posting.is_remote and posting.job_type == "Full-time"
    assert (posting.salary_min, posting.salary_max, posting.salary_interval) == (150000, 210000, "year")
    assert {"Python", "SQL", "scikit-learn", "Snowflake", "dbt"} <= set(posting.skills)


SR_ROUTES = {
    "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings": load_fixture("smartrecruiters_list.json"),
    "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/744000012345678": load_fixture("smartrecruiters_detail.json"),
}


def test_smartrecruiters(fake_client):
    src = SourceConfig(name="bosch", type="smartrecruiters", company="Bosch", options={"company_id": "BoschGroup"})
    jobs, scraper, _ = scrape(fake_client, src, SR_ROUTES)
    posting, _ = normalize(jobs[0])
    assert posting.location == "Stuttgart, BW, DE"
    assert {"C++", "Agile", "Git", "Jenkins", "Linux"} <= set(posting.skills)
    assert posting.department == "Mobility Solutions"
    assert scraper.complete


def test_smartrecruiters_incremental_skips_detail(fake_client):
    src = SourceConfig(name="bosch", type="smartrecruiters", company="Bosch", options={"company_id": "BoschGroup"})
    jobs, _, client = scrape(fake_client, src, SR_ROUTES, known={"744000012345678": "2026-09-20T07:30:00.000Z"})
    assert jobs[0].unchanged
    assert len(client.calls) == 1  # listing only, no detail request


def test_smartrecruiters_max_jobs_marks_incomplete(fake_client):
    src = SourceConfig(name="bosch", type="smartrecruiters", company="Bosch",
                       options={"company_id": "BoschGroup", "max_jobs": 1})
    listing = load_fixture("smartrecruiters_list.json")
    listing["content"] = listing["content"] * 2
    listing["totalFound"] = 2
    routes = {**SR_ROUTES, "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings": listing}
    jobs, scraper, _ = scrape(fake_client, src, routes)
    assert len(jobs) == 1 and scraper.complete is False


def test_jsonld_follows_links(fake_client):
    src = SourceConfig(name="example", type="jsonld", company="Fallback", options={
        "start_urls": ["https://careers.example.com/jobs"], "link_pattern": r"/jobs/[^/]+$"})
    routes = {
        "https://careers.example.com/jobs": load_fixture("jsonld_listing.html"),
        "https://careers.example.com/jobs/*": load_fixture("jsonld_job.html"),
    }
    jobs, _, client = scrape(fake_client, src, routes)
    assert "https://other-site.com/jobs/ignored" not in client.calls
    assert len(jobs) == 2  # both detail pages (fixture serves the same posting)
    posting, _ = normalize(jobs[0])
    assert posting.company == "Example Corp"
    assert posting.is_remote and posting.location == "India"
    assert posting.job_type == "Full-time"
    assert (posting.salary_currency, posting.salary_min, posting.salary_interval) == ("INR", 2500000, "year")
    assert {"Terraform", "AWS", "Kubernetes", "Observability"} <= set(posting.skills)


def test_jsonld_falls_back_to_microdata(fake_client):
    """A page with no JSON-LD but schema.org HTML microdata (itemscope/itemprop) - the pattern
    found on SAP SuccessFactors "Career Site Builder" sites like HCLTech and Wipro - must
    still be picked up, including a job's nested jobLocation/address object.
    """
    src = SourceConfig(name="example", type="jsonld", company="Fallback",
                       options={"start_urls": ["https://careers.example.com/job/account-manager"]})
    jobs, _, _ = scrape(fake_client, src, {"https://careers.example.com/job/account-manager": load_fixture("microdata_job.html")})
    assert len(jobs) == 1
    posting, issues = normalize(jobs[0])
    assert issues == []
    assert posting.title == "Account Manager"
    assert posting.company == "Example Corp"
    assert posting.job_type == "Full-time"
    assert posting.location == "Gurugram, Haryana, India"  # from the nested jobLocation.address
    assert "Job Summary" in posting.description
    assert "offices worldwide" not in posting.description  # duplicate itemprop="description"
    # (a reused company blurb, shorter than the real one) must lose, not get concatenated in


def test_jsonld_discovers_jobs_from_a_sitemap(fake_client):
    """start_urls pointing straight at a sitemap.xml (<urlset>): its <loc> entries become the
    pages to visit, instead of <a href> links - for listing pages that are client-rendered
    (no links in their raw HTML) but still publish a sitemap for search engines.
    """
    src = SourceConfig(name="example", type="jsonld", company="Fallback", options={
        "start_urls": ["https://careers.example.com/sitemap.xml"], "link_pattern": r"/job/"})
    routes = {
        "https://careers.example.com/sitemap.xml": load_fixture("sitemap_urlset.xml"),
        "https://careers.example.com/job/Account-Manager/1001/": load_fixture("microdata_job.html"),
        "https://careers.example.com/job/Platform-Engineer/1002/": load_fixture("jsonld_job.html"),
    }
    jobs, _, client = scrape(fake_client, src, routes)
    assert "https://careers.example.com/about-us/" not in client.calls  # filtered by link_pattern
    assert {j.title for j in jobs} == {"Account Manager", "Platform Engineer"}


def test_jsonld_discovers_jobs_from_a_sitemap_index(fake_client):
    """A <sitemapindex> (a sitemap of sitemaps) is expanded one level: its entries are treated
    as more sitemaps, not job pages, and are followed the same way.
    """
    src = SourceConfig(name="example", type="jsonld", company="Fallback", options={
        "start_urls": ["https://careers.example.com/sitemap_index.xml"], "link_pattern": r"/job/"})
    routes = {
        "https://careers.example.com/sitemap_index.xml": load_fixture("sitemap_index.xml"),
        "https://careers.example.com/sitemaps/jobs.xml": load_fixture("sitemap_urlset.xml"),
        "https://careers.example.com/job/Account-Manager/1001/": load_fixture("microdata_job.html"),
        "https://careers.example.com/job/Platform-Engineer/1002/": load_fixture("jsonld_job.html"),
    }
    jobs, _, _ = scrape(fake_client, src, routes)
    assert {j.title for j in jobs} == {"Account Manager", "Platform Engineer"}


def test_jsonld_sitemap_respects_known_markers_and_max_pages(fake_client):
    src = SourceConfig(name="example", type="jsonld", company="Fallback", options={
        "start_urls": ["https://careers.example.com/sitemap.xml"], "link_pattern": r"/job/", "max_pages": 2})
    routes = {
        "https://careers.example.com/sitemap.xml": load_fixture("sitemap_urlset.xml"),
        "https://careers.example.com/job/Account-Manager/1001/": load_fixture("microdata_job.html"),
        "https://careers.example.com/job/Platform-Engineer/1002/": load_fixture("jsonld_job.html"),
    }
    # known: the sitemap fetch itself counts toward max_pages, so only 1 of the 2 job pages
    # is actually fetched; the run must be marked incomplete rather than silently partial.
    jobs, scraper, client = scrape(fake_client, src, routes)
    assert len(jobs) == 1 and scraper.complete is False

    # a job already known and unchanged is served from known_markers, no detail fetch needed
    src.options["max_pages"] = 50
    jobs2, _, client2 = scrape(fake_client, src, routes, known={
        "https://careers.example.com/job/Account-Manager/1001/": "m"})
    assert any(j.unchanged for j in jobs2)
    assert "https://careers.example.com/job/Account-Manager/1001/" not in client2.calls


def test_css_scraper(fake_client):
    src = SourceConfig(name="startup", type="css", company="Startup", options={
        "list_url": "https://startup.io/careers", "item_selector": "div.job-card", "title_selector": "h3",
        "location_selector": ".location", "description_selector": "div.job-description"})
    routes = {
        "https://startup.io/careers": load_fixture("css_listing.html"),
        "https://startup.io/careers/*": load_fixture("css_detail.html"),
    }
    jobs, _, _ = scrape(fake_client, src, routes)
    assert [j.title for j in jobs] == ["Growth Marketing Manager", "Contract iOS Developer"]
    first, _ = normalize(jobs[0])
    assert first.location == "Bengaluru, India"
    assert {"SEO", "Excel", "Looker", "Data Analysis"} <= set(first.skills)
    assert "Menu" not in first.description
    second, _ = normalize(jobs[1])
    assert second.is_remote and second.job_type == "Contract"


ACCENTURE_API = "https://www.accenture.com/api/accenture/elastic/findjobs"


def test_accenture(fake_client):
    src = SourceConfig(name="accenture-india", type="accenture", company="Accenture (India)",
                       options={"job_country": "India", "country_site": "in-en"})
    jobs, scraper, client = scrape(fake_client, src, {ACCENTURE_API: load_fixture("accenture.json")})
    assert len(jobs) == 2 and scraper.complete
    assert client.calls == [ACCENTURE_API]  # one page covers it (fixture has fewer than PAGE_SIZE)

    grad, _ = normalize(jobs[0])
    assert grad.title == "Associate Software Engineer"
    assert grad.location == "Bengaluru; Hyderabad"
    assert grad.apply_link == "https://www.accenture.com/in-en/careers/jobdetails?id=R00111111_en&title=Associate+Software+Engineer"
    assert grad.job_type == "Full-time"
    assert grad.experience_level == "Fresher / 0-1 yr"
    assert grad.region == "Asia Pacific"
    assert {"Java", "Python"} <= set(grad.skills)
    assert grad.external_id == "R00111111"

    senior, _ = normalize(jobs[1])
    assert senior.experience_level == "8-12 yrs"
    assert senior.is_remote is True
    assert senior.department == "Senior Manager"
    # Title alone ("Senior Manager - Cloud Infrastructure") doesn't name a category, and
    # "engineering team"/"engineers" in the body is too generic a mention to trust - correctly
    # left unclassified rather than guessed. See test_regions_roles.py for that design choice.
    assert senior.role_category is None


def test_accenture_pagination_and_max_jobs(fake_client):
    page1 = {"data": [
        {"title": f"Role {i}", "requisitionId": f"R{i}", "location": ["Pune"],
         "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=R" + str(i),
         "jobDescriptionClean": "x" * 50, "updateDate": "2026-10-01T00:00:00.000-07:00"}
        for i in range(100)
    ]}
    page2 = {"data": [
        {"title": "Role 100", "requisitionId": "R100", "location": ["Pune"],
         "jobDetailUrl": "https://www.accenture.com/{0}/careers/jobdetails?id=R100",
         "jobDescriptionClean": "y" * 50, "updateDate": "2026-10-01T00:00:00.000-07:00"},
    ]}

    def router(fields):
        return page1 if fields.get("startIndex") == "0" else page2

    src = SourceConfig(name="accenture-india", type="accenture", company="Accenture (India)",
                       options={"job_country": "India", "country_site": "in-en", "max_jobs": 105})
    jobs, scraper, client = scrape(fake_client, src, {ACCENTURE_API: router})
    assert len(jobs) == 101 and scraper.complete  # full second page returned, under the cap
    assert client.calls == [ACCENTURE_API, ACCENTURE_API]  # paged past the first 100

    src.options["max_jobs"] = 50
    jobs, scraper, _ = scrape(fake_client, src, {ACCENTURE_API: router})
    assert len(jobs) == 50 and scraper.complete is False  # stopped mid-page, listing was truncated
