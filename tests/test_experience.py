from jd_collector.experience import EXPERIENCE_LEVELS, detect_experience_level as d


def test_fresher_phrasing():
    assert d("Associate Software Engineer", "We are hiring freshers for our graduate program.") == "Fresher / 0-1 yr"
    assert d("Java Developer", "0-1 Yrs of experience required.") == "Fresher / 0-1 yr"
    assert d("Intern - Software Engineering", "Entry level position, no experience needed.") == "Fresher / 0-1 yr"
    assert d("Product Manager", "B.Tech freshers can apply.") == "Fresher / 0-1 yr"
    assert d("Software Engineering Intern", "Join us for a summer internship with our team.") == "Fresher / 0-1 yr"


def test_intern_does_not_false_positive_on_similar_words():
    assert d("Senior Internal Auditor", "Review financial controls across the org.") is None
    assert d("International Sales Manager", "Drive growth across EMEA.") is None


def test_ranges_and_buckets():
    assert d("Senior Engineer", "Minimum 5 years of experience in backend development.") == "5-8 yrs"
    assert d("Staff Engineer", "At least 8 yrs experience with distributed systems.") == "8-12 yrs"
    assert d("Principal Engineer", "12+ years of experience required.") == "12+ yrs"
    assert d("Data Analyst", "2-4 Yrs Exp in SQL and Python.") == "1-3 yrs"
    assert d("Software Engineer III", "3 years of experience with Java required.") == "3-5 yrs"
    assert d("Software Engineer", "Experience: 12-14 years") == "12+ yrs"
    assert d("Ops Lead", "Exp: 8-10 Yrs required.") == "8-12 yrs"


def test_takes_the_lower_bound_of_a_range():
    assert d(None, "Looking for someone with 1-10 years of experience.") == "1-3 yrs"


def test_no_signal_stays_unclassified():
    assert d("Director", "We are looking for a leader.") is None
    assert d("Engineer", "") is None
    assert d(None, None) is None


def test_result_is_always_a_known_level_or_none():
    for title, desc in [("Engineer", "5 years experience"), ("CEO", ""), (None, "fresher role")]:
        r = d(title, desc)
        assert r is None or r in EXPERIENCE_LEVELS
