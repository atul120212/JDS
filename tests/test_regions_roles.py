from jd_collector.regions import REGIONS, detect_region
from jd_collector.roles import ROLE_CATEGORIES, detect_role_category


def test_detect_region_countries_and_cities():
    assert detect_region("San Francisco, CA, US", False) == "North America"
    assert detect_region("Dublin, IE", False) == "Europe"
    assert detect_region("Bengaluru, India", False) == "Asia Pacific"
    assert detect_region("São Paulo, BR", False) == "Latin America"
    assert detect_region("Tel Aviv", False) == "Middle East & Africa"
    assert detect_region("Warsaw, Poland", False) == "Europe"
    assert detect_region("Nashville, Tennessee, United States", False) == "North America"
    assert detect_region("New York, NY", False) == "North America"


def test_detect_region_shorthand_and_remote():
    assert detect_region("Remote (EMEA)", True) == "Europe"
    assert detect_region("APAC", False) == "Asia Pacific"
    assert detect_region("LATAM", False) == "Latin America"
    assert detect_region("AMER", False) == "North America"
    assert detect_region("Remote - US", True) == "North America"
    assert detect_region("Remote", True) == "Remote / Global"
    assert detect_region("Global", False) == "Remote / Global"
    assert detect_region(None, True) == "Remote / Global"
    assert detect_region(None, False) is None
    assert detect_region("Hybrid", False) is None  # no locatable signal -> left unclassified


def test_detect_region_short_codes_are_word_bounded():
    # lowercase "us"/"uk" inside ordinary words must not false-positive
    assert detect_region("Must be comfortable with ambiguous situations", False) is None
    assert detect_region("United Kingdom", False) == "Europe"


def test_region_result_is_always_a_known_region_or_none():
    for loc in ["Dublin", "Remote", "APAC", None, "Nowhereville"]:
        r = detect_region(loc, True)
        assert r is None or r in REGIONS


def test_detect_role_category_priority_order():
    assert detect_role_category("Senior Backend Engineer, Payments") == "Engineering"
    assert detect_role_category("Data Scientist") == "Data & AI"
    assert detect_role_category("Machine Learning Engineer") == "Data & AI"  # not generic Engineering
    assert detect_role_category("Account Executive, SMB") == "Sales & Business Development"
    assert detect_role_category("Sales Engineer") == "Sales & Business Development"  # not Engineering
    assert detect_role_category("Support Engineer") == "Customer Support & Success"  # not Engineering
    assert detect_role_category("Solutions Engineer, Enterprise") == "Sales & Business Development"
    assert detect_role_category("Recruiting Coordinator (Contract)") == "People & Talent"
    assert detect_role_category("Product Manager, Growth") == "Product"
    assert detect_role_category("Product Marketing Manager") == "Marketing & Communications"
    assert detect_role_category("Senior Product Designer") == "Design"
    assert detect_role_category("Legal Counsel, Privacy") == "Legal & Compliance"
    assert detect_role_category("Financial Analyst, FP&A") == "Finance & Accounting"
    assert detect_role_category("Technical Program Manager") == "Operations"
    assert detect_role_category("VP of Engineering") == "Engineering"
    assert detect_role_category("Head of Design") == "Design"
    assert detect_role_category("Growth Marketing Manager") == "Marketing & Communications"
    assert detect_role_category("Business Ops Associate") == "Operations"  # "Ops" abbreviation
    assert detect_role_category("Record to Report Ops Associate") == "Operations"
    assert detect_role_category("People Ops Partner") == "People & Talent"  # checked before Operations


def test_title_is_exhausted_before_the_description_is_ever_consulted():
    """A long description's boilerplate must never outvote a title that already said plainly
    what the role is - found via real scraped data: a generic "Design and implement processes"
    bullet in an Ops posting's body text was overriding its own clear title.
    """
    assert detect_role_category(
        "Software Engineering Intern, iOS",
        "About the company: our Finance organization partners closely with every team...",
    ) == "Engineering"
    assert detect_role_category(
        "Record to Report Ops Associate",
        "...Design and implement processes for direct tax income tax reporting...",
    ) == "Operations"
    assert detect_role_category(
        "Executive Assistant",
        "You will support our engineering leadership team and partner with engineers daily.",
    ) is None  # title alone gives no category; "engineer(ing)" in the body is too weak a signal


def test_bare_design_and_engineer_are_title_only_fallbacks():
    # Specific enough even in a description: unaffected.
    assert detect_role_category(None, "We need a software engineer who loves Python.") == "Engineering"
    # Too generic for a description (ordinary verb usage), fine for a title.
    assert detect_role_category(None, "Help us design and implement better onboarding.") is None
    assert detect_role_category("Head of Design", "") == "Design"


def test_detect_role_category_unknown_stays_none():
    assert detect_role_category("Chief of Staff") is None
    assert detect_role_category("Solutions Architect - Benelux") is None  # genuinely ambiguous; no guess
    assert detect_role_category(None) is None
    assert detect_role_category("") is None


def test_role_category_result_is_always_known_or_none():
    titles = ["Software Engineer", "Account Executive", None, "Chief of Staff", "Barista"]
    for t in titles:
        r = detect_role_category(t)
        assert r is None or r in ROLE_CATEGORIES
