"""Resume parsing endpoint: extract text, sections, and numbered bullets."""

from fastapi import APIRouter, Form, HTTPException, UploadFile

from backend.nlp.jd_keywords import extract_keywords
from backend.nlp.portal_profiles import resolve_portal_profile
from backend.nlp.scoring import score_resume
from backend.parsing import (
    extract_text_from_docx,
    extract_text_from_pdf,
    parse_resume_text,
)
from backend.schema import ParseResponse, PortalInfo

router = APIRouter(tags=["parse"])


def _portal_info(portal: str | None) -> PortalInfo:
    profile = resolve_portal_profile(portal)
    return PortalInfo(
        family=profile.family,
        display_name=profile.display_name,
        hint=profile.hint,
        force_classic_template=profile.force_classic_template,
    )


@router.post("/parse", response_model=ParseResponse)
async def parse_resume(
    file: UploadFile,
    job_description: str | None = Form(None),
    job_portal: str | None = Form(None),
) -> ParseResponse:
    """Pipeline steps 1-3: extract resume structure locally; if a JD is
    provided, extract keywords and compute a parse-time ATS score for Review."""
    filename = (file.filename or "").lower()
    data = await file.read()

    page_count = None
    try:
        if filename.endswith(".pdf"):
            raw_text, page_count = extract_text_from_pdf(data)
        elif filename.endswith(".docx"):
            raw_text = extract_text_from_docx(data)
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported file type. Upload a PDF or DOCX."
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not read the file: {exc}"
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No extractable text found (the file may be a scanned image).",
        )

    resume = parse_resume_text(raw_text)
    resume.page_count = page_count

    profile = resolve_portal_profile(job_portal)
    portal = _portal_info(job_portal)

    jd_keywords = None
    before = None
    if job_description and job_description.strip():
        jd_keywords = extract_keywords(job_description)
        before = score_resume(
            resume, jd_keywords, mentioned_weight=profile.mentioned_weight
        )

    return ParseResponse(
        resume=resume, jd_keywords=jd_keywords, before=before, portal=portal
    )
