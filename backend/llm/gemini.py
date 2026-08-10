"""The single Gemini Flash call (pipeline step 4).

This is the ONLY LLM call in the whole app: temperature 0, JSON schema mode,
exactly one API call per resume run plus at most one retry on invalid JSON.

Python builds a TailorPlan (skills order, bullet order, per-bullet keyword
directives). Gemini ONLY rewrites bullet text + summary under that plan.
Contact info, companies, titles, dates, education, and skills are never in
the schema — merge_tailored() applies them programmatically.

Configured via env vars: LLM_API_KEY, LLM_BASE_URL (an OpenAI-compatible
endpoint, defaulting to Gemini's), and LLM_MODEL.
"""

from __future__ import annotations

import json
import os

import httpx
from pydantic import ValidationError

from backend.nlp.portal_profiles import PortalProfile, portal_prompt_instructions
from backend.nlp.tailor_plan import TailorPlan, skills_whitelist
from backend.schema import (
    JDKeyword,
    LLMOutput,
    ParsedResume,
    SkillGroup,
    TailoredBullet,
    TailoredExperienceEntry,
    TailoredProjectEntry,
    TailoredResume,
)

DEFAULT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
_JD_EXCERPT_CHARS = 1500


class GeminiError(Exception):
    """Raised when the tailoring call cannot produce a valid result."""


# ---------------------------------------------------------------------------
# Prompt + response schema
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are a resume rewrite EXECUTOR, not a strategist. A deterministic plan \
below tells you exactly which JD terms to use and which synonym swaps to \
apply. Follow it precisely.

HARD RULES:
1. NEVER invent experience, skills, tools, numbers, metrics, companies, \
titles, dates, or soft claims (e.g. "proven leader", "highly scalable") \
that are not already in the source bullet or original summary.
2. Keep each rewritten bullet grounded in its OWN source bullet only — do \
not move facts between bullets.
3. Keep EVERY number, metric, and proper noun from the source bullet intact.
4. Max ~28 words per bullet; start with a strong action verb.
5. When the plan lists USE THESE JD TERMS, weave those exact surface forms \
into the bullet ONLY because the source already demonstrates them (evidence \
was verified in Python). Do not add terms not listed for that bullet.
6. When the plan lists APPLY SWAPS, replace the left form with the right \
form (e.g. K8s → Kubernetes). Do not add new tools.
7. When LEAD WITH is set, put that theme/clause first in the bullet.
8. Summary: 2–3 sentences. Weave in the SUMMARY MUST-INCLUDE keywords \
naturally. Ground ONLY in source bullets, skills whitelist context, and \
original summary. No invented employers, titles, metrics, or seniority.
9. You MUST return exactly one rewritten object for EVERY bullet_id listed. \
Do not omit, merge, or invent IDs. Do not return a skills list.

FEW-SHOT (synonym canonicalize — do this; do NOT invent tools):
BAD:  "Led migration of 12 services to K8s using Terraform"  (Terraform not in source)
GOOD: "Led Kubernetes migration of 12 services, cutting deploy time by 40%"  (K8s→Kubernetes only)
"""


def build_prompt(
    resume: ParsedResume,
    jd_keywords: list[JDKeyword],
    plan: TailorPlan,
    target_pages: int,
    job_description: str = "",
    company_name: str | None = None,
    job_title: str | None = None,
    job_portal: str | None = None,
    portal_profile: PortalProfile | None = None,
) -> str:
    lines: list[str] = [_INSTRUCTIONS, "", f"TARGET LENGTH: {target_pages} page(s)."]

    context_bits = [
        f"Company: {company_name}" if company_name else None,
        f"Target role: {job_title}" if job_title else None,
        f"Job portal: {job_portal}" if job_portal else None,
    ]
    context_bits = [b for b in context_bits if b]
    if context_bits:
        lines.append(
            "TARGET ROLE CONTEXT (tone/phrasing only — do NOT claim you worked there): "
            + "; ".join(context_bits)
        )
    if portal_profile is not None:
        lines.append(
            "ATS SCREENING PROFILE: " + portal_prompt_instructions(portal_profile)
        )

    lines.append(
        "\nJD KEYWORDS (required — prioritize): "
        + (", ".join(plan.required_keywords) or "none")
    )
    lines.append(
        "JD KEYWORDS (nice-to-have): "
        + (", ".join(plan.nice_keywords) or "none")
    )
    lines.append(
        "SUMMARY MUST-INCLUDE (evidenced only): "
        + (", ".join(plan.summary_must_include) or "none")
    )
    if plan.keyword_gaps:
        lines.append(
            "KEYWORD GAPS (no evidence — do NOT invent these): "
            + ", ".join(plan.keyword_gaps)
        )

    lines.append(
        "\nSKILLS (already ordered by Python — for summary context only; "
        "do not return skills): "
        + (", ".join(plan.skills_order) or "none")
    )

    if resume.summary:
        lines.append(f"\nORIGINAL SUMMARY:\n{resume.summary}")
    else:
        lines.append(
            "\nORIGINAL SUMMARY: (none — write a grounded summary from the "
            "source bullets and must-include keywords only)"
        )

    excerpt = (job_description or "").strip()
    if excerpt:
        if len(excerpt) > _JD_EXCERPT_CHARS:
            excerpt = excerpt[:_JD_EXCERPT_CHARS].rstrip() + "…"
        lines.append(f"\nJD EXCERPT (context for verbs/domain; keywords above are hard targets):\n{excerpt}")

    lines.append(
        "\nSOURCE BULLETS — rewrite EACH one exactly once, following its directives:"
    )
    for bid, bp in plan.bullet_plans.items():
        lines.append(f"\nREWRITE {bid} [{bp.context_label}]")
        lines.append(f"SOURCE: {bp.source_text}")
        if bp.evidenced_keywords:
            lines.append(
                "USE THESE JD TERMS IF ALREADY EVIDENCED: "
                + ", ".join(bp.evidenced_keywords)
            )
        else:
            lines.append("USE THESE JD TERMS IF ALREADY EVIDENCED: (none)")
        if bp.canonical_swaps:
            swaps = ", ".join(f"{a} → {b}" for a, b in bp.canonical_swaps)
            lines.append(f"APPLY SWAPS: {swaps}")
        if bp.lead_with:
            lines.append(f"LEAD WITH: {bp.lead_with}")

    return "\n".join(lines)


def build_response_schema(resume: ParsedResume) -> dict:
    """Gemini JSON schema: bullets keyed to source IDs + summary only."""
    bullet_ids = [
        b.id for e in resume.experience for b in e.bullets
    ] + [b.id for p in resume.projects for b in p.bullets]

    return {
        "type": "object",
        "properties": {
            "bullets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "bullet_id": {"type": "string", "enum": bullet_ids or ["B0"]},
                        "text": {"type": "string"},
                    },
                    "required": ["bullet_id", "text"],
                    "additionalProperties": False,
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["bullets", "summary"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------


def _call_gemini(prompt: str, response_schema: dict) -> str:
    """Raw API call (OpenAI-compatible endpoint), isolated so tests can mock it."""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("LLM_API_KEY environment variable is not set.")

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("LLM_MODEL") or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "tailored_resume",
                "strict": True,
                "schema": response_schema,
            },
        },
    }
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise GeminiError(f"LLM API call failed: {exc}") from exc

    if not content:
        raise GeminiError("The LLM returned an empty response.")
    return content


def run_tailor_call(
    resume: ParsedResume,
    jd_keywords: list[JDKeyword],
    plan: TailorPlan,
    target_pages: int,
    job_description: str = "",
    company_name: str | None = None,
    job_title: str | None = None,
    job_portal: str | None = None,
    portal_profile: PortalProfile | None = None,
) -> LLMOutput:
    """One Gemini call, plus at most one retry if the JSON is invalid."""
    prompt = build_prompt(
        resume,
        jd_keywords,
        plan,
        target_pages,
        job_description=job_description,
        company_name=company_name,
        job_title=job_title,
        job_portal=job_portal,
        portal_profile=portal_profile,
    )
    schema = build_response_schema(resume)

    last_error: Exception | None = None
    for _attempt in range(2):
        raw = _call_gemini(prompt, schema)
        try:
            return LLMOutput.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc

    raise GeminiError(
        f"Gemini returned invalid JSON twice; giving up. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Merge: LLM content + programmatically-copied facts + TailorPlan
# ---------------------------------------------------------------------------


def merge_tailored(
    resume: ParsedResume, output: LLMOutput, plan: TailorPlan
) -> TailoredResume:
    """Combine the LLM's rewritten content with fact fields + deterministic plan.

    Bullets missing from the LLM output keep their original text. Skills and
    within-job bullet order come from the TailorPlan, not the LLM.
    """
    rewritten = {b.bullet_id: b.text.strip() for b in output.bullets if b.text.strip()}

    def tailor_bullets(bullets, ordered_ids: list[str]) -> list[TailoredBullet]:
        by_id = {b.id: b for b in bullets}
        result: list[TailoredBullet] = []
        for bid in ordered_ids:
            bullet = by_id.get(bid)
            if bullet is None:
                continue
            if bid in rewritten:
                text = rewritten[bid]
                result.append(
                    TailoredBullet(
                        id=bid,
                        original=bullet.text,
                        text=text,
                        changed=text != bullet.text,
                    )
                )
            else:
                result.append(
                    TailoredBullet(
                        id=bid,
                        original=bullet.text,
                        text=bullet.text,
                        changed=False,
                        flags=["missing_from_llm"],
                    )
                )
        # Any bullets not in the plan order (shouldn't happen) append at end.
        for bullet in bullets:
            if bullet.id not in {b.id for b in result}:
                result.append(
                    TailoredBullet(
                        id=bullet.id,
                        original=bullet.text,
                        text=rewritten.get(bullet.id, bullet.text),
                        changed=bullet.id in rewritten
                        and rewritten[bullet.id] != bullet.text,
                        flags=["missing_from_plan"] if bullet.id not in rewritten else [],
                    )
                )
        return result

    experience = [
        TailoredExperienceEntry(
            company=entry.company,
            title=entry.title,
            dates=entry.dates,
            location=entry.location,
            header_raw=entry.header_raw,
            bullets=tailor_bullets(
                entry.bullets,
                plan.experience_bullet_order[i]
                if i < len(plan.experience_bullet_order)
                else [b.id for b in entry.bullets],
            ),
        )
        for i, entry in enumerate(resume.experience)
    ]
    projects = [
        TailoredProjectEntry(
            name=project.name,
            dates=project.dates,
            url=project.url,
            tech=project.tech,
            bullets=tailor_bullets(
                project.bullets,
                plan.project_bullet_order[i]
                if i < len(plan.project_bullet_order)
                else [b.id for b in project.bullets],
            ),
        )
        for i, project in enumerate(resume.projects)
    ]

    skills = list(plan.skills_order) or list(skills_whitelist(resume))
    skill_groups = [
        SkillGroup(category=cat, items=items) for cat, items in plan.skill_groups
    ] or list(resume.skill_groups)

    return TailoredResume(
        contact=resume.contact,
        headline=resume.headline,
        summary=output.summary.strip() or resume.summary,
        skills=skills,
        skill_groups=skill_groups,
        experience=experience,
        projects=projects,
        education=list(resume.education),
        certifications=list(resume.certifications),
        awards=list(resume.awards),
        publications=list(resume.publications),
        languages=list(resume.languages),
        other_sections=list(resume.other_sections),
    )
