"""Tests for pipeline steps 5-6: groundedness verifier + keyword preservation."""

from backend.llm.gemini import merge_tailored
from backend.nlp.tailor_plan import build_tailor_plan
from backend.nlp.verifier import preserve_keywords, verify_bullets, verify_summary
from backend.parsing import parse_resume_text
from backend.schema import JDKeyword, LLMOutput, SkillGroup

ORIGINAL_TEXT = """\
JANE DOE
jane@example.com

Experience
Senior Software Engineer — Acme Corp    Jan 2021 – Present
• Led migration of 12 services to K8s, cutting deploy time by 40%
• Mentored 4 junior engineers
• Built REST APIs in Python serving 2M requests per day

Skills
Python, Docker, Kubernetes
"""


def _tailor(llm_bullets, summary="Summary.", skills_override=None):
    resume = parse_resume_text(ORIGINAL_TEXT)
    if skills_override is not None:
        resume.skills = skills_override
    plan = build_tailor_plan(resume, [])
    if skills_override is not None:
        plan.skills_order = list(skills_override)
    output = LLMOutput(bullets=llm_bullets, summary=summary)
    tailored = merge_tailored(resume, output, plan)
    verify_bullets(tailored, resume.raw_text)
    return resume, tailored, plan


def test_fabricated_metric_is_reverted():
    _, tailored, _ = _tailor(
        [
            {
                "bullet_id": "B1",
                "text": "Led migration of 12 services to Kubernetes, cutting deploy time by 85%",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ]
    )
    bullet = tailored.experience[0].bullets[0]

    assert bullet.reverted is True
    assert bullet.text == bullet.original
    assert bullet.changed is False
    assert any("digit rule" in flag and "85" in flag for flag in bullet.flags)


def test_metric_preservation_reverts_when_source_number_dropped():
    _, tailored, _ = _tailor(
        [
            {
                "bullet_id": "B1",
                "text": "Led Kubernetes migration of services, cutting deploy time",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ]
    )
    bullet = next(b for b in tailored.experience[0].bullets if b.id == "B1")
    assert bullet.reverted is True
    assert any("metric preservation" in flag for flag in bullet.flags)


def test_fabricated_technology_is_reverted():
    _, tailored, _ = _tailor(
        [
            {"bullet_id": "B1", "text": "Led migration of 12 services using Terraform"},
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ]
    )
    bullet = next(b for b in tailored.experience[0].bullets if b.id == "B1")

    assert bullet.reverted is True
    assert bullet.text == bullet.original
    assert any("entity rule" in flag and "Terraform" in flag for flag in bullet.flags)


def test_synonym_canonicalization_is_allowed():
    _, tailored, _ = _tailor(
        [
            {
                "bullet_id": "B1",
                "text": "Led Kubernetes migration of 12 services, cutting deploy time by 40%",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ]
    )
    bullet = next(b for b in tailored.experience[0].bullets if b.id == "B1")

    assert bullet.reverted is False
    assert bullet.changed is True
    assert bullet.flags == []


def test_grounded_numbers_pass():
    _, tailored, _ = _tailor(
        [
            {
                "bullet_id": "B1",
                "text": "Cut deploy time by 40% by migrating 12 services to K8s",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built Python REST APIs serving 2M requests per day",
            },
        ]
    )
    assert all(not b.reverted for e in tailored.experience for b in e.bullets)


def test_summary_verification_reverts_ungrounded():
    resume, tailored, plan = _tailor(
        [
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
        ],
        summary="World-class Terraform expert with 99% delivery success.",
    )
    # Give an original summary so verify falls back to it.
    resume.summary = "Engineer with Python experience."
    flags = verify_summary(tailored, resume, plan)
    assert flags
    assert tailored.summary == "Engineer with Python experience."


def test_keyword_preservation_readds_vanished_whitelisted_skill():
    resume, tailored, _ = _tailor(
        [
            {
                "bullet_id": "B1",
                "text": "Led migration of 12 services, cutting deploy time by 40%",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ],
    )
    # Drop Kubernetes from tailored skills to simulate a vanished match.
    tailored.skills = ["Python", "Docker"]
    kubernetes = JDKeyword(keyword="Kubernetes", importance="required")

    assert "Kubernetes" not in tailored.skills
    added = preserve_keywords(tailored, resume, [kubernetes])

    assert added == ["Kubernetes"]
    assert "Kubernetes" in tailored.skills


def test_keyword_preservation_uses_skill_groups_whitelist():
    resume = parse_resume_text(ORIGINAL_TEXT)
    resume.skills = []
    resume.skill_groups = [
        SkillGroup(category="Cloud", items=["Kubernetes", "Docker"]),
        SkillGroup(category="Languages", items=["Python"]),
    ]
    plan = build_tailor_plan(resume, [])
    plan.skills_order = ["Python", "Docker"]  # omit Kubernetes
    output = LLMOutput(
        bullets=[
            {
                "bullet_id": "B1",
                "text": "Led migration of 12 services, cutting deploy time by 40%",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
            {
                "bullet_id": "B3",
                "text": "Built REST APIs in Python serving 2M requests per day",
            },
        ],
        summary="Summary.",
    )
    tailored = merge_tailored(resume, output, plan)
    tailored.skills = ["Python", "Docker"]
    kubernetes = JDKeyword(keyword="Kubernetes", importance="required")
    added = preserve_keywords(tailored, resume, [kubernetes])
    assert added == ["Kubernetes"]


def test_keyword_preservation_skips_non_whitelisted_keyword():
    resume, tailored, _ = _tailor(
        [{"bullet_id": "B2", "text": "Mentored 4 junior engineers"}],
        skills_override=["Python"],
    )
    rest = JDKeyword(keyword="REST APIs", importance="required")

    added = preserve_keywords(tailored, resume, [rest])
    assert added == []
    assert "REST APIs" not in tailored.skills


def test_keyword_preservation_ignores_keyword_without_evidence():
    resume, tailored, _ = _tailor(
        [{"bullet_id": "B2", "text": "Mentored 4 junior engineers"}]
    )
    terraform = JDKeyword(keyword="Terraform", importance="required")

    added = preserve_keywords(tailored, resume, [terraform])
    assert added == []
    assert "Terraform" not in tailored.skills
