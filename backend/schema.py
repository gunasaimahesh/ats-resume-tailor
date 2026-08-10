"""Pydantic models shared across the pipeline."""

from typing import Literal

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    """Contact fields copied verbatim into the final resume (never rewritten)."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    links: list[str] = []


class Bullet(BaseModel):
    """A single resume bullet, numbered B1, B2, ... at parse time."""

    id: str
    text: str


class ExperienceEntry(BaseModel):
    """One job: header (company/title/dates/location) plus its bullets."""

    company: str | None = None
    title: str | None = None
    dates: str | None = None
    location: str | None = None
    header_raw: str
    bullets: list[Bullet] = []


class EducationEntry(BaseModel):
    """One education row with labeled fields for Review / PDF."""

    school: str | None = None
    degree: str | None = None
    gpa: str | None = None
    location: str | None = None
    dates: str | None = None
    raw_lines: list[str] = []


class ProjectEntry(BaseModel):
    """One project: name line plus its bullets."""

    name: str
    dates: str | None = None
    url: str | None = None
    tech: str | None = None
    bullets: list[Bullet] = []


class SkillGroup(BaseModel):
    """A categorized skills row (category may be null for uncategorized)."""

    category: str | None = None
    items: list[str] = []


class CertificationEntry(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
    url: str | None = None


class AwardEntry(BaseModel):
    """One achievement/award line (no structured date fields)."""

    text: str


class PublicationEntry(BaseModel):
    """One publication line."""

    text: str


class LanguageEntry(BaseModel):
    language: str
    proficiency: str | None = None


class SectionBlock(BaseModel):
    """A section we detected but don't structure further (kept verbatim)."""

    name: str
    heading_raw: str
    lines: list[str] = []


class ParsedResume(BaseModel):
    """Output of pipeline step 1: local text extraction + structure detection."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = []
    skill_groups: list[SkillGroup] = []
    experience: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    certifications: list[CertificationEntry] = []
    awards: list[AwardEntry] = []
    publications: list[PublicationEntry] = []
    languages: list[LanguageEntry] = []
    other_sections: list[SectionBlock] = []
    raw_text: str
    page_count: int | None = None  # only known for PDF uploads


class JDKeyword(BaseModel):
    """One keyword extracted from the job description (pipeline step 2)."""

    keyword: str
    importance: Literal["required", "nice_to_have", "mentioned"]
    aliases_matched: list[str] = []
    in_dictionary: bool = True
    # Standard skill category for dictionary skills; None for YAKE extras.
    category: str | None = None


class KeywordMatch(BaseModel):
    """Match result for one JD keyword against the resume (pipeline steps 3/9)."""

    keyword: str
    importance: Literal["required", "nice_to_have", "mentioned"]
    status: Literal["matched", "missing"]
    match_type: Literal["exact", "synonym", "fuzzy"] | None = None
    matched_text: str | None = None
    location: str | None = None


class ScoreReport(BaseModel):
    """ATS score: weighted overall coverage plus per-keyword detail."""

    score: float
    required_coverage: float
    band: Literal["green", "yellow", "red"]
    matches: list[KeywordMatch] = []


class PortalInfo(BaseModel):
    """Resolved ATS family for the selected job portal."""

    family: str
    display_name: str
    hint: str
    force_classic_template: bool = True


class ParseResponse(BaseModel):
    """Response of POST /api/parse: parsed resume plus optional JD keywords
    and a parse-time 'before' ATS score when a JD was provided."""

    resume: ParsedResume
    jd_keywords: list[JDKeyword] | None = None
    before: ScoreReport | None = None
    portal: PortalInfo | None = None


class LLMBullet(BaseModel):
    """One rewritten bullet in the Gemini output, keyed by source bullet ID."""

    bullet_id: str
    text: str


class LLMOutput(BaseModel):
    """The COMPLETE Gemini output schema (pipeline step 4).

    Deliberately contains ONLY rewritten bullets and a summary. Skills order
    is computed deterministically in Python. Contact info, companies, titles,
    dates, education, and other fact sections are NOT here — they are copied
    from the original programmatically."""

    bullets: list[LLMBullet]
    summary: str


class TailoredBullet(BaseModel):
    """A bullet in the tailored resume, with its original for diff/verify."""

    id: str
    original: str
    text: str
    changed: bool
    reverted: bool = False
    flags: list[str] = []


class TailoredExperienceEntry(BaseModel):
    """Experience entry with facts copied verbatim and bullets rewritten."""

    company: str | None = None
    title: str | None = None
    dates: str | None = None
    location: str | None = None
    header_raw: str
    bullets: list[TailoredBullet] = []


class TailoredProjectEntry(BaseModel):
    name: str
    dates: str | None = None
    url: str | None = None
    tech: str | None = None
    bullets: list[TailoredBullet] = []


class TailoredResume(BaseModel):
    """LLM-rewritten content merged with programmatically-copied fact fields."""

    contact: ContactInfo
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = []
    skill_groups: list[SkillGroup] = []
    experience: list[TailoredExperienceEntry] = []
    projects: list[TailoredProjectEntry] = []
    education: list[EducationEntry] = []
    certifications: list[CertificationEntry] = []
    awards: list[AwardEntry] = []
    publications: list[PublicationEntry] = []
    languages: list[LanguageEntry] = []
    other_sections: list[SectionBlock] = []


class TailorRequest(BaseModel):
    """Input for the tailoring pipeline."""

    resume: ParsedResume
    job_description: str
    target_pages: int | None = None
    # Optional context — portal also selects ATS screening knobs.
    company_name: str | None = None
    job_title: str | None = None
    job_portal: str | None = None


class TailorResponse(BaseModel):
    """Tailored resume plus JD keywords and the 'before' ATS score."""

    tailored: TailoredResume
    jd_keywords: list[JDKeyword] = []
    before: ScoreReport
    keyword_gaps: list[str] = []  # required JD keywords with no resume evidence
    keyword_repairs: list[str] = []  # skills re-added to preserve matches
    summary_flags: list[str] = []  # summary verification / fallback notes
    portal: PortalInfo | None = None


class RoundTripCheck(BaseModel):
    """Result of the post-render self-check (pipeline step 8)."""

    passed: bool
    issues: list[str] = []


class FitReport(BaseModel):
    """How page fitting resolved without dropping content."""

    density_step: Literal["normal", "compact", "dense"] = "normal"
    requested_pages: int
    actual_pages: int
    template: Literal["classic", "two_column"] = "classic"


class RenderRequest(BaseModel):
    """Input for POST /api/render."""

    tailored: TailoredResume
    jd_keywords: list[JDKeyword] = []
    # None -> prefer original_pages when known, else experience heuristic.
    target_pages: int | Literal["same_as_original"] | None = None
    original_pages: int | None = None
    # Keywords matched on the original (before) — used for non-regression repair.
    before_matched_keywords: list[str] = []
    template: Literal["classic", "two_column"] = "classic"
    job_portal: str | None = None


class RenderResponse(BaseModel):
    """Rendered PDF plus page-fitting and self-check results."""

    pdf_base64: str
    pages: int
    target_pages: int
    fit: FitReport
    roundtrip: RoundTripCheck
    after: ScoreReport | None = None
    keyword_repairs: list[str] = []
