"""Tests for pipeline step 2: JD keyword extraction and classification."""

from backend.nlp.jd_keywords import extract_keywords, is_claimable_keyword
from backend.nlp.portal_profiles import resolve_portal_profile
from backend.schema import JDKeyword

SAMPLE_JD = """\
Senior Backend Engineer

We are looking for a backend engineer to build our payment processing platform.

Requirements:
- Expert-level Python and experience with FastAPI or Django
- Must have hands-on experience running K8s and Docker in production
- Strong SQL and PostgreSQL skills
- Experience building REST APIs and microservices
- CI/CD pipelines (GitHub Actions or Jenkins)

Nice to have:
- Familiarity with Terraform and AWS
- Exposure to Kafka
- ML experience is a plus
"""

GOOGLE_STYLE_JD = """\
Software Engineer, Cloud Storage

Google's software engineers develop the next-generation technologies that change
how billions of users connect. We're looking for engineers who bring fresh ideas
from all areas, including information retrieval, distributed computing,
large-scale system design, networking and data storage, security, artificial
intelligence, natural language processing, UI design and mobile.

About the job
You will work on Google Cloud Storage file systems at massive scale.

Minimum qualifications:
- Bachelor's degree or equivalent practical experience.
- 2 years of experience with software development in one or more programming
  languages (C, C++, Python, Java, or Go).
- 2 years of experience with developing large-scale infrastructure, storage,
  distributed systems, or file systems.

Preferred qualifications:
- Master's degree or PhD in Computer Science or related technical fields.
- 2 years of experience with data structures or algorithms in either an
  academic or industry setting.
"""


def _by_name(keywords):
    return {kw.keyword: kw for kw in keywords}


def test_dictionary_keywords_extracted_with_synonyms():
    kws = _by_name(extract_keywords(SAMPLE_JD))

    assert "Python" in kws
    assert "FastAPI" in kws
    assert "Django" in kws
    assert "Kubernetes" in kws
    assert "K8s" in kws["Kubernetes"].aliases_matched
    assert "Machine Learning" in kws
    assert "ML" in kws["Machine Learning"].aliases_matched
    assert "PostgreSQL" in kws
    assert "REST APIs" in kws
    assert "CI/CD" in kws
    assert kws["Python"].category == "Languages"
    assert kws["Kubernetes"].category == "Cloud & DevOps"
    assert kws["PostgreSQL"].category == "Databases"


def test_required_vs_nice_to_have_classification():
    kws = _by_name(extract_keywords(SAMPLE_JD))

    for required in ["Python", "Kubernetes", "Docker", "SQL", "Microservices"]:
        assert kws[required].importance == "required", required

    for nice in ["Terraform", "AWS", "Kafka", "Machine Learning"]:
        assert kws[nice].importance == "nice_to_have", nice


def test_required_sorted_before_nice_to_have():
    keywords = extract_keywords(SAMPLE_JD)
    ranks = {"required": 0, "nice_to_have": 1, "mentioned": 2}
    scores = [ranks[kw.importance] for kw in keywords]
    assert scores == sorted(scores)


def test_case_sensitive_aliases_do_not_match_english_words():
    jd = "You will go to conferences and take the rest of the week to recharge."
    kws = _by_name(extract_keywords(jd))
    assert "Go" not in kws
    assert "REST APIs" not in kws


def test_yake_drops_minimum_qualifications_heading():
    jd = """\
Software Engineer

Minimum qualifications:
- Experience with distributed systems
- Bachelor's degree

Preferred qualifications:
- Python experience is a plus

Requirements:
- Must have Java and Kubernetes
"""
    kws = _by_name(extract_keywords(jd))
    assert "Minimum qualifications" not in kws
    assert "Preferred qualifications" not in kws
    assert "Java" in kws
    assert "Kubernetes" in kws


def test_is_claimable_keyword_dictionary_only():
    assert is_claimable_keyword(
        JDKeyword(keyword="Python", importance="required", in_dictionary=True)
    )
    assert not is_claimable_keyword(
        JDKeyword(
            keyword="payment processing platform",
            importance="required",
            in_dictionary=False,
        )
    )
    assert not is_claimable_keyword(
        JDKeyword(
            keyword="Minimum qualifications",
            importance="required",
            in_dictionary=True,
        )
    )
    assert not is_claimable_keyword(
        JDKeyword(keyword="NLP", importance="mentioned", in_dictionary=True)
    )


def test_google_boilerplate_nlp_is_mentioned_not_required():
    kws = _by_name(extract_keywords(GOOGLE_STYLE_JD))

    assert "NLP" in kws
    assert kws["NLP"].importance == "mentioned"
    assert not is_claimable_keyword(kws["NLP"])

    # Bare "Google Cloud" alias removed — product branding should not create GCP.
    assert "GCP" not in kws

    # Bare "security" in laundry list should not create Security skill.
    assert "Security" not in kws

    for lang in ["Python", "C++", "Java", "Go"]:
        assert lang in kws, lang
        assert kws[lang].importance == "required", lang

    assert "Data Structures" in kws
    assert kws["Data Structures"].importance == "nice_to_have"
    assert "Algorithms" in kws
    assert kws["Algorithms"].importance == "nice_to_have"


def test_portal_resolve_aliases():
    assert resolve_portal_profile("Greenhouse").family == "greenhouse"
    assert resolve_portal_profile("boards.greenhouse.io/acme").family == "greenhouse"
    assert resolve_portal_profile("AshbyHQ").family == "ashby"
    assert resolve_portal_profile("myworkdayjobs.com").family == "workday"
    assert resolve_portal_profile("Workday").family == "workday"
    assert resolve_portal_profile(None).family == "generic"
    assert resolve_portal_profile("").family == "generic"
    assert resolve_portal_profile("some random board").family == "generic"
    assert resolve_portal_profile("workday").force_classic_template is True
    assert resolve_portal_profile("greenhouse").force_classic_template is False
    # Dual-form skill rewriting removed — profiles no longer expose that knob.
    assert not hasattr(resolve_portal_profile("workday"), "require_dual_forms")
