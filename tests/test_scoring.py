"""Tests for pipeline steps 3/9: ATS keyword-coverage scoring."""

from backend.nlp.scoring import band_for, score_resume
from backend.parsing import parse_resume_text
from backend.schema import JDKeyword


def _kw(name: str, importance: str = "required", in_dictionary: bool = True) -> JDKeyword:
    return JDKeyword(keyword=name, importance=importance, in_dictionary=in_dictionary)


JD_KEYWORDS = [
    _kw("Python"),
    _kw("Kubernetes"),
    _kw("Docker"),
    _kw("FastAPI"),
    _kw("PostgreSQL"),
    _kw("AWS", importance="nice_to_have"),
    _kw("Terraform", importance="nice_to_have"),
]

MATCHING_RESUME = """\
JANE DOE
jane@example.com

Experience
Senior Software Engineer — Acme Corp    Jan 2021 – Present
• Deployed 12 microservices with Docker and K8s on AWS
• Built REST APIs in Python with FastAPI backed by Postgres

Skills
Python, FastAPI, Docker, Kubernetes, PostgreSQL, AWS, Terraform
"""

NON_MATCHING_RESUME = """\
JOHN SMITH
john@example.com

Experience
Head Chef — Bistro Nouveau    2019 – Present
• Designed seasonal menus for a 120-seat restaurant
• Managed a kitchen brigade of 15 staff

Skills
Menu Planning, Food Safety, Inventory Management
"""


def test_matching_resume_scores_high_and_green():
    resume = parse_resume_text(MATCHING_RESUME)
    report = score_resume(resume, JD_KEYWORDS)

    assert report.score == 100.0
    assert report.required_coverage == 100.0
    assert report.band == "green"
    assert all(m.status == "matched" for m in report.matches)


def test_non_matching_resume_scores_low_and_red():
    resume = parse_resume_text(NON_MATCHING_RESUME)
    report = score_resume(resume, JD_KEYWORDS)

    assert report.score == 0.0
    assert report.required_coverage == 0.0
    assert report.band == "red"
    assert all(m.status == "missing" for m in report.matches)


def test_synonym_match_reports_type_and_location():
    resume = parse_resume_text(
        "JANE DOE\n\nExperience\nEngineer — Acme\n• Ran workloads on K8s clusters"
    )
    report = score_resume(resume, [_kw("Kubernetes")])

    match = report.matches[0]
    assert match.status == "matched"
    assert match.match_type == "synonym"
    assert match.matched_text == "K8s"
    assert match.location == "experience B1"


def test_mentioned_keywords_do_not_affect_required_coverage_band():
    resume = parse_resume_text(NON_MATCHING_RESUME)
    keywords = [
        _kw("Python", importance="required"),
        _kw("NLP", importance="mentioned"),
        _kw("Security", importance="mentioned"),
    ]
    report = score_resume(resume, keywords)
    # No required matches → red band; mentioned misses don't change coverage.
    assert report.required_coverage == 0.0
    assert report.band == "red"
    # Overall score still lightly includes mentioned weight in denominator.
    assert report.score == 0.0


def test_mentioned_match_credits_low_weight_without_greening_band():
    resume = parse_resume_text(
        "JANE DOE\njane@example.com\n\nSkills\nNLP, Python\n"
    )
    keywords = [
        _kw("Python", importance="required"),
        _kw("NLP", importance="mentioned"),
        _kw("Kubernetes", importance="required"),
    ]
    report = score_resume(resume, keywords, mentioned_weight=0.25)
    # 1 of 2 required → 50% coverage → red
    assert report.required_coverage == 50.0
    assert report.band == "red"
    # Matched: Python (2) + NLP (0.25) / total 2+2+0.25
    assert report.score == round(2.25 / 4.25 * 100, 1)


def test_fuzzy_match_survives_typo():
    resume = parse_resume_text(
        "JANE DOE\n\nExperience\nEngineer — Acme\n• Managed Kuberntes deployments"
    )
    report = score_resume(resume, [_kw("Kubernetes")])

    match = report.matches[0]
    assert match.status == "matched"
    assert match.match_type == "fuzzy"
    assert match.matched_text == "Kuberntes"


def test_java_does_not_match_javascript():
    resume = parse_resume_text(
        "JANE DOE\n\nSkills\nJavaScript, TypeScript, React"
    )
    report = score_resume(resume, [_kw("Java")])
    assert report.matches[0].status == "missing"


def test_required_weighs_double():
    # 1 required missing + 2 nice-to-have matched: 2/4 weight = 50.
    resume = parse_resume_text("JANE DOE\n\nSkills\nAWS, Terraform")
    report = score_resume(
        resume,
        [_kw("Kubernetes"), _kw("AWS", "nice_to_have"), _kw("Terraform", "nice_to_have")],
    )
    assert report.score == 50.0
    assert report.required_coverage == 0.0
    assert report.band == "red"


def test_banding_edges():
    assert band_for(80) == "green"
    assert band_for(79.9) == "yellow"
    assert band_for(70) == "yellow"
    assert band_for(69.9) == "red"


def test_empty_keyword_list_is_perfect_score():
    resume = parse_resume_text("JANE DOE\n\nSkills\nPython")
    report = score_resume(resume, [])
    assert report.score == 100.0
    assert report.band == "green"
