"""Parse-time ATS score + claimed skills feeding TailorPlan whitelist."""

from backend.nlp.scoring import score_resume
from backend.nlp.tailor_plan import build_tailor_plan, skills_whitelist
from backend.nlp.jd_keywords import extract_keywords, is_claimable_keyword
from backend.parsing import parse_resume_text
from backend.schema import JDKeyword, ParseResponse

RESUME = """\
JANE DOE
jane@example.com

Experience
Software Engineer — Acme    Jan 2021 – Present
• Built APIs in Java serving payments

Skills
Java, TypeScript
"""

JD = """\
Requirements:
- Must have Java, Python, and Go
- Kubernetes experience required

Nice to have:
- TypeScript
"""


def test_parse_response_model_includes_before_score():
    resume = parse_resume_text(RESUME)
    keywords = extract_keywords(JD)
    before = score_resume(resume, keywords)
    response = ParseResponse(resume=resume, jd_keywords=keywords, before=before)

    assert response.before is not None
    assert response.before.score > 0
    by_name = {m.keyword: m for m in response.before.matches}
    assert by_name["Java"].status == "matched"
    assert by_name["Python"].status == "missing"
    assert by_name["Go"].status == "missing"


def test_claimable_missing_are_dictionary_skills_only():
    resume = parse_resume_text(RESUME)
    keywords = extract_keywords(JD)
    before = score_resume(resume, keywords)
    missing = [m.keyword for m in before.matches if m.status == "missing"]
    kw_map = {k.keyword: k for k in keywords}
    claimable = [
        name
        for name in missing
        if name in kw_map and is_claimable_keyword(kw_map[name])
    ]
    assert "Python" in claimable
    assert "Go" in claimable
    assert "Kubernetes" in claimable
    # Non-dictionary YAKE phrases (if any) are not claimable.
    for name in missing:
        if name in kw_map and not kw_map[name].in_dictionary:
            assert name not in claimable


def test_user_claimed_skill_enters_tailor_plan_whitelist():
    resume = parse_resume_text(RESUME)
    # Simulate Review checklist: user claims Python.
    resume.skills = list(dict.fromkeys([*resume.skills, "Python"]))
    keywords = [
        JDKeyword(keyword="Python", importance="required"),
        JDKeyword(keyword="Java", importance="required"),
    ]
    plan = build_tailor_plan(resume, keywords)

    assert "Python" in skills_whitelist(resume)
    assert plan.skills_order[0] == "Python" or "Python" in plan.skills_order[:2]
    assert "Python" not in plan.keyword_gaps
