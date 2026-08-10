"""Render endpoint: page fitting, WeasyPrint PDF generation, and the
round-trip self-check (pipeline steps 7-8), plus the 'after' ATS score
on the final content (step 9)."""

import base64

from fastapi import APIRouter, Depends, HTTPException

from backend.nlp.portal_profiles import resolve_portal_profile
from backend.nlp.scoring import score_segments, segments_from_tailored
from backend.render.renderer import (
    RenderError,
    fit_to_pages,
    resolve_target_pages,
    roundtrip_check,
)
from backend.schema import RenderRequest, RenderResponse
from backend.security import require_access_code

router = APIRouter(tags=["render"], dependencies=[Depends(require_access_code)])


@router.post("/render", response_model=RenderResponse)
async def render_resume(request: RenderRequest) -> RenderResponse:
    profile = resolve_portal_profile(request.job_portal)
    template = request.template
    if profile.force_classic_template and template != "classic":
        template = "classic"

    target_pages = resolve_target_pages(
        request.target_pages, request.original_pages, request.tailored
    )

    try:
        final, pdf_bytes, pages, fit, repairs = fit_to_pages(
            request.tailored,
            request.jd_keywords,
            target_pages,
            before_matched_keywords=request.before_matched_keywords,
            template=template,
        )
    except RenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    check = roundtrip_check(pdf_bytes, final)
    after = (
        score_segments(
            segments_from_tailored(final),
            request.jd_keywords,
            mentioned_weight=profile.mentioned_weight,
        )
        if request.jd_keywords
        else None
    )

    return RenderResponse(
        pdf_base64=base64.b64encode(pdf_bytes).decode("ascii"),
        pages=pages,
        target_pages=target_pages,
        fit=fit,
        roundtrip=check,
        after=after,
        keyword_repairs=repairs,
    )
