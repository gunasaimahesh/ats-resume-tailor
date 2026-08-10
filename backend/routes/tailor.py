"""Tailoring endpoint: JD keywords, 'before' scoring, TailorPlan, the single
Gemini call, then the deterministic groundedness verifier and keyword
preservation (pipeline steps 2-6)."""

from fastapi import APIRouter, Depends, HTTPException

from backend.llm.gemini import GeminiError, merge_tailored, run_tailor_call
from backend.nlp.jd_keywords import extract_keywords
from backend.nlp.portal_profiles import resolve_portal_profile
from backend.nlp.scoring import score_resume
from backend.nlp.tailor_plan import build_tailor_plan
from backend.nlp.verifier import preserve_keywords, verify_bullets, verify_summary
from backend.render.renderer import default_target_pages
from backend.schema import PortalInfo, TailorRequest, TailorResponse
from backend.security import require_access_code

router = APIRouter(tags=["tailor"], dependencies=[Depends(require_access_code)])


def _target_pages_for_prompt(request: TailorRequest) -> int:
    """Page budget hint for Gemini; prefer original pages when known."""
    if isinstance(request.target_pages, int):
        return max(1, request.target_pages)
    if request.resume.page_count:
        return max(1, request.resume.page_count)
    return default_target_pages(request.resume.experience)


@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(request: TailorRequest) -> TailorResponse:
    profile = resolve_portal_profile(request.job_portal)
    jd_keywords = extract_keywords(request.job_description)
    before = score_resume(
        request.resume, jd_keywords, mentioned_weight=profile.mentioned_weight
    )
    plan = build_tailor_plan(request.resume, jd_keywords)
    target_pages = _target_pages_for_prompt(request)

    try:
        output = run_tailor_call(
            request.resume,
            jd_keywords,
            plan,
            target_pages,
            job_description=request.job_description,
            company_name=request.company_name,
            job_title=request.job_title,
            job_portal=request.job_portal,
            portal_profile=profile,
        )
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tailored = merge_tailored(request.resume, output, plan)
    verify_bullets(tailored, request.resume.raw_text)  # step 5: revert + flag
    summary_flags = verify_summary(tailored, request.resume, plan)
    repairs = preserve_keywords(tailored, request.resume, jd_keywords)  # step 6
    return TailorResponse(
        tailored=tailored,
        jd_keywords=jd_keywords,
        before=before,
        keyword_gaps=plan.keyword_gaps,
        keyword_repairs=repairs,
        summary_flags=summary_flags,
        portal=PortalInfo(
            family=profile.family,
            display_name=profile.display_name,
            hint=profile.hint,
            force_classic_template=profile.force_classic_template,
        ),
    )
