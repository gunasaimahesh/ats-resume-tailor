"""Tests for pipeline step 4: the single Gemini call and the merge.

The API itself is mocked; these tests cover the response schema constraints,
JSON validation with one retry, graceful failure, and the merge that copies
fact fields programmatically and applies the TailorPlan.
"""

import json

import pytest

import backend.llm.gemini as gemini
from backend.llm.gemini import (
    GeminiError,
    build_prompt,
    build_response_schema,
    merge_tailored,
    run_tailor_call,
)
from backend.nlp.tailor_plan import build_tailor_plan
from backend.parsing import parse_resume_text
from backend.schema import JDKeyword, LLMOutput

RESUME_TEXT = """\
JANE DOE
jane@example.com | (555) 123-4567

Experience
Senior Software Engineer — Acme Corp    Jan 2021 – Present
• Led migration of 12 services to K8s, cutting deploy time by 40%
• Mentored 4 junior engineers

Education
B.S. Computer Science, State University, 2018

Skills
Python, Docker, Kubernetes, AWS
"""


@pytest.fixture
def resume():
    return parse_resume_text(RESUME_TEXT)


@pytest.fixture
def plan(resume):
    keywords = [
        JDKeyword(keyword="Kubernetes", importance="required"),
        JDKeyword(keyword="Python", importance="nice_to_have"),
    ]
    return build_tailor_plan(resume, keywords), keywords


VALID_RESPONSE = json.dumps(
    {
        "bullets": [
            {
                "bullet_id": "B1",
                "text": "Led Kubernetes migration of 12 services, cutting deploy time by 40%",
            },
            {"bullet_id": "B2", "text": "Mentored 4 junior engineers"},
        ],
        "summary": "Senior engineer with Kubernetes and Docker production experience.",
    }
)


def test_schema_contains_only_allowed_fields(resume):
    schema = build_response_schema(resume)

    assert set(schema["properties"]) == {"bullets", "summary"}
    assert "skills" not in schema["properties"]
    bullet_schema = schema["properties"]["bullets"]["items"]
    assert bullet_schema["properties"]["bullet_id"]["enum"] == ["B1", "B2"]
    dumped = json.dumps(schema).lower()
    for forbidden in ["contact", "company", "title", "date", "education", "skills"]:
        assert forbidden not in dumped


def test_prompt_contains_per_bullet_directives(resume, plan):
    tailor_plan, keywords = plan
    prompt = build_prompt(
        resume,
        keywords,
        tailor_plan,
        target_pages=1,
        job_description="We need Kubernetes and Python experience.",
        company_name="Stripe",
        job_title="Staff Engineer",
    )
    assert "REWRITE B1" in prompt
    assert "USE THESE JD TERMS IF ALREADY EVIDENCED" in prompt
    assert "APPLY SWAPS" in prompt or "Kubernetes" in prompt
    assert "TARGET ROLE CONTEXT" in prompt
    assert "Stripe" in prompt
    assert "JD EXCERPT" in prompt
    assert "do not return skills" in prompt.lower() or "do not return a skills" in prompt.lower()


def test_valid_response_first_try(resume, plan, monkeypatch):
    tailor_plan, keywords = plan
    calls = []

    def fake_call(prompt, schema):
        calls.append(prompt)
        return VALID_RESPONSE

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    output = run_tailor_call(resume, keywords, tailor_plan, target_pages=1)

    assert len(calls) == 1
    assert output.bullets[0].bullet_id == "B1"
    assert output.summary.startswith("Senior engineer")


def test_invalid_json_retries_once_then_succeeds(resume, plan, monkeypatch):
    tailor_plan, keywords = plan
    responses = iter(["{not valid json", VALID_RESPONSE])
    calls = []

    def fake_call(prompt, schema):
        calls.append(1)
        return next(responses)

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    output = run_tailor_call(resume, keywords, tailor_plan, target_pages=1)

    assert len(calls) == 2
    assert isinstance(output, LLMOutput)


def test_invalid_json_twice_fails_gracefully(resume, plan, monkeypatch):
    tailor_plan, keywords = plan
    calls = []

    def fake_call(prompt, schema):
        calls.append(1)
        return "definitely not json"

    monkeypatch.setattr(gemini, "_call_gemini", fake_call)
    with pytest.raises(GeminiError, match="invalid JSON twice"):
        run_tailor_call(resume, keywords, tailor_plan, target_pages=1)
    assert len(calls) == 2


def test_merge_copies_facts_and_applies_plan_skills(resume, plan):
    tailor_plan, _keywords = plan
    output = LLMOutput.model_validate_json(VALID_RESPONSE)
    tailored = merge_tailored(resume, output, tailor_plan)

    assert tailored.contact.name == "JANE DOE"
    assert tailored.contact.email == "jane@example.com"
    entry = tailored.experience[0]
    assert entry.company == "Acme Corp"
    assert entry.title == "Senior Software Engineer"
    assert entry.dates == "Jan 2021 – Present"
    assert len(tailored.education) == 1
    assert "State University" in (tailored.education[0].school or "")

    assert entry.bullets[0].text.startswith("Led Kubernetes migration")
    assert entry.bullets[0].changed is True
    # Skills come from the plan, not the LLM.
    assert tailored.skills == tailor_plan.skills_order
    assert "Kubernetes" in tailored.skills
    assert tailored.summary is not None and "Kubernetes" in tailored.summary


def test_merge_keeps_unmapped_bullets(resume, plan):
    tailor_plan, _keywords = plan
    output = LLMOutput(
        bullets=[
            {"bullet_id": "B1", "text": "Rewritten bullet one"},
            {"bullet_id": "B99", "text": "Hallucinated bullet id"},
        ],
        summary="Summary.",
    )
    tailored = merge_tailored(resume, output, tailor_plan)

    bullets = [b for e in tailored.experience for b in e.bullets]
    assert [b.id for b in bullets] == [b.id for b in tailored.experience[0].bullets]
    assert set(b.id for b in bullets) == {"B1", "B2"}
    b2 = next(b for b in bullets if b.id == "B2")
    assert b2.text.startswith("Mentored 4 junior")
    assert "missing_from_llm" in b2.flags


def test_missing_api_key_fails_gracefully(resume, plan, monkeypatch):
    tailor_plan, keywords = plan
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiError, match="LLM_API_KEY"):
        run_tailor_call(resume, keywords, tailor_plan, target_pages=1)
