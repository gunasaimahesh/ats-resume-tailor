"""Tests for deterministic TailorPlan construction."""

from backend.nlp.tailor_plan import build_tailor_plan
from backend.parsing import parse_resume_text
from backend.schema import JDKeyword

RESUME_TEXT = """\
JANE DOE
jane@example.com

Experience
Senior Software Engineer — Acme Corp    Jan 2021 – Present
• Led migration of 12 services to K8s, cutting deploy time by 40%
• Mentored 4 junior engineers
• Built REST APIs in Python serving 2M requests per day

Skills
Python, Docker, Kubernetes, AWS
"""


def test_canonical_swaps_and_evidenced_keywords():
    resume = parse_resume_text(RESUME_TEXT)
    keywords = [
        JDKeyword(keyword="Kubernetes", importance="required"),
        JDKeyword(keyword="Python", importance="required"),
        JDKeyword(keyword="Terraform", importance="required"),
    ]
    plan = build_tailor_plan(resume, keywords)

    b1 = plan.bullet_plans["B1"]
    assert "Kubernetes" in b1.evidenced_keywords
    assert ("K8s", "Kubernetes") in b1.canonical_swaps or any(
        a == "K8s" and b == "Kubernetes" for a, b in b1.canonical_swaps
    )
    assert plan.keyword_gaps == ["Terraform"]
    assert "Terraform" not in plan.summary_must_include


def test_skills_order_puts_jd_matches_first():
    resume = parse_resume_text(RESUME_TEXT)
    keywords = [
        JDKeyword(keyword="Kubernetes", importance="required"),
        JDKeyword(keyword="AWS", importance="nice_to_have"),
    ]
    plan = build_tailor_plan(resume, keywords)
    assert plan.skills_order[0] == "Kubernetes"
    assert "AWS" in plan.skills_order[:3]
    # All whitelist skills retained — Gemini cannot drop them.
    assert set(plan.skills_order) == {"Python", "Docker", "Kubernetes", "AWS"}


def test_standard_skill_groups_ignore_original_style():
    resume = parse_resume_text(RESUME_TEXT)
    # Original style would be a flat uncategorized list; plan must rebuild.
    resume.skill_groups = []
    keywords = [
        JDKeyword(keyword="Kubernetes", importance="required"),
        JDKeyword(keyword="Python", importance="required"),
    ]
    plan = build_tailor_plan(resume, keywords)
    by_cat = {cat: items for cat, items in plan.skill_groups}
    assert "Languages" in by_cat
    assert "Python" in by_cat["Languages"]
    assert "Cloud & DevOps" in by_cat
    assert "Kubernetes" in by_cat["Cloud & DevOps"]
    assert "Docker" in by_cat["Cloud & DevOps"]
    assert "AWS" in by_cat["Cloud & DevOps"]
    # No "Claimed for this JD" or null-category leftovers.
    assert all(cat for cat, _ in plan.skill_groups)


def test_bullet_reorder_by_relevance():
    resume = parse_resume_text(RESUME_TEXT)
    keywords = [
        JDKeyword(keyword="Python", importance="required"),
        JDKeyword(keyword="Kubernetes", importance="nice_to_have"),
    ]
    plan = build_tailor_plan(resume, keywords)
    order = plan.experience_bullet_order[0]
    # B3 (Python) should outrank B2 (no keywords); B1 has Kubernetes (nice).
    assert order.index("B3") < order.index("B2")
    assert "B1" in order
