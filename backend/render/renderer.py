"""PDF rendering, page fitting, and the round-trip self-check (steps 7-8).

Page fitting NEVER drops experience. If the render overflows the target page
count, we re-render at progressively denser CSS presets; if it still overflows
at the densest step, we grow the page count rather than deleting content.
"""

from __future__ import annotations

import io
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.nlp.scoring import (
    match_keyword,
    segments_from_tailored,
)
from backend.nlp.skills_dict import SKILL_SYNONYMS, category_for_skill
from backend.nlp.tailor_plan import skills_whitelist
from backend.schema import (
    FitReport,
    JDKeyword,
    ParsedResume,
    RoundTripCheck,
    SkillGroup,
    TailoredResume,
)

TEMPLATE_DIR = Path(__file__).resolve().parent

TemplateName = Literal["classic", "two_column"]
DensityStep = Literal["normal", "compact", "dense"]

DENSITY_STEPS: list[DensityStep] = ["normal", "compact", "dense"]

# CSS variable overrides injected per density step.
DENSITY_CSS: dict[DensityStep, str] = {
    "normal": """
:root {
  --page-margin-y: 0.5in;
  --page-margin-x: 0.6in;
  --body-size: 10.25pt;
  --body-leading: 1.32;
  --h1-size: 18pt;
  --h2-size: 10pt;
  --h2-margin-top: 9pt;
  --entry-margin: 6pt;
  --li-margin: 1.5pt;
  --section-pad: 0;
  --sidebar-width: 32%;
  --col-gap: 14pt;
}
""",
    "compact": """
:root {
  --page-margin-y: 0.4in;
  --page-margin-x: 0.5in;
  --body-size: 9.5pt;
  --body-leading: 1.22;
  --h1-size: 16pt;
  --h2-size: 9.25pt;
  --h2-margin-top: 6pt;
  --entry-margin: 4pt;
  --li-margin: 1pt;
  --section-pad: 0;
  --sidebar-width: 30%;
  --col-gap: 12pt;
}
""",
    "dense": """
:root {
  --page-margin-y: 0.32in;
  --page-margin-x: 0.42in;
  --body-size: 8.75pt;
  --body-leading: 1.15;
  --h1-size: 15pt;
  --h2-size: 8.75pt;
  --h2-margin-top: 4.5pt;
  --entry-margin: 3pt;
  --li-margin: 0.6pt;
  --section-pad: 0;
  --sidebar-width: 28%;
  --col-gap: 10pt;
}
""",
}


class RenderError(Exception):
    """Raised when the PDF cannot be produced (e.g. missing native libs)."""


_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


# ---------------------------------------------------------------------------
# Target page count (step 7)
# ---------------------------------------------------------------------------


def default_target_pages(experience) -> int:
    """SPEC heuristic: 1 page if total experience <= 3 years, else 2."""
    years = [
        int(y)
        for entry in experience
        if entry.dates
        for y in re.findall(r"(?:19|20)\d{2}", entry.dates)
    ]
    if not years:
        return 1
    return 1 if date.today().year - min(years) <= 3 else 2


def resolve_target_pages(
    target_pages, original_pages: int | None, tailored: TailoredResume
) -> int:
    if isinstance(target_pages, int):
        return max(1, target_pages)
    if target_pages == "same_as_original" and original_pages:
        return original_pages
    # Safer default: prefer original page count when known (reduces density extremes).
    if target_pages is None and original_pages:
        return max(1, original_pages)
    if target_pages == "same_as_original":
        return default_target_pages(tailored.experience)
    return default_target_pages(tailored.experience)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _contact_lines(contact) -> list[str]:
    """Two ATS-safe contact lines for the template."""
    line1 = " · ".join(
        part
        for part in [contact.email, contact.phone, contact.location]
        if part
    )
    line2 = " · ".join(
        part
        for part in [
            contact.linkedin,
            contact.github,
            contact.website,
            *contact.links,
        ]
        if part
    )
    return [line for line in [line1, line2] if line]


def _template_filename(template: TemplateName) -> str:
    if template == "two_column":
        return "template_two_column.html"
    return "template.html"


def _normalize_edu_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower().strip(" ,;-–—|()")


def filter_education_raw_lines(entry) -> list[str]:
    """Drop raw_lines that duplicate structured education fields."""
    structured_blob = " ".join(
        _normalize_edu_text(p)
        for p in [entry.school, entry.degree, entry.gpa, entry.location, entry.dates]
        if p
    )
    kept: list[str] = []
    for line in entry.raw_lines or []:
        stripped = (line or "").strip()
        if not stripped:
            continue
        norm = _normalize_edu_text(stripped)
        tokens = [t for t in re.findall(r"[a-z0-9.]+", norm) if len(t) > 1]
        if tokens and sum(1 for t in tokens if t in structured_blob) / len(tokens) >= 0.7:
            continue
        kept.append(stripped)
    return kept


def education_meta_line(entry) -> str | None:
    """Degree · location · GPA (degree omitted when it's already the header title)."""
    parts: list[str] = []
    if entry.school and entry.degree:
        parts.append(entry.degree)
    if entry.location:
        parts.append(entry.location)
    if entry.gpa:
        parts.append(f"GPA: {entry.gpa}")
    return " · ".join(parts) if parts else None


def _prepare_for_template(tailored: TailoredResume) -> tuple[TailoredResume, list[str | None]]:
    """Copy tailored resume with education extras filtered; return edu meta lines."""
    working = tailored.model_copy(deep=True)
    meta_lines: list[str | None] = []
    for entry in working.education:
        entry.raw_lines = filter_education_raw_lines(entry)
        meta_lines.append(education_meta_line(entry))
    return working, meta_lines


def render_pdf(
    tailored: TailoredResume,
    *,
    density: DensityStep = "normal",
    template: TemplateName = "classic",
) -> tuple[bytes, int]:
    """Render to PDF with WeasyPrint; returns (pdf_bytes, page_count)."""
    if sys.platform == "darwin":
        # Homebrew's Pango lives in /opt/homebrew/lib, which ctypes doesn't
        # search by default. No effect on Linux/Docker.
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")
    try:
        from weasyprint import CSS, HTML
    except OSError as exc:
        raise RenderError(
            "WeasyPrint native libraries missing (on macOS: brew install pango)."
        ) from exc

    view, edu_meta = _prepare_for_template(tailored)
    html_string = _env.get_template(_template_filename(template)).render(
        r=view,
        contact_lines=_contact_lines(view.contact),
        edu_meta=edu_meta,
    )
    stylesheets = [
        CSS(string=DENSITY_CSS[density]),
        CSS(str(TEMPLATE_DIR / "print.css")),
    ]
    if template == "two_column":
        stylesheets.append(CSS(str(TEMPLATE_DIR / "print_two_column.css")))
    document = HTML(string=html_string).render(stylesheets=stylesheets)
    return document.write_pdf(), len(document.pages)


# ---------------------------------------------------------------------------
# Page fitting (step 7) — density ladder; never drop bullets
# ---------------------------------------------------------------------------


def _all_bullets(tailored: TailoredResume):
    for entry in tailored.experience:
        for bullet in entry.bullets:
            yield bullet
    for project in tailored.projects:
        for bullet in project.bullets:
            yield bullet


def _missing_before_keywords(
    tailored: TailoredResume,
    jd_keywords: list[JDKeyword],
    before_matched: set[str],
) -> list[JDKeyword]:
    segments = segments_from_tailored(tailored)
    missing = []
    for keyword in jd_keywords:
        if keyword.keyword not in before_matched:
            continue
        if match_keyword(keyword, segments).status != "matched":
            missing.append(keyword)
    return missing


def _append_skill_to_groups(tailored: TailoredResume, skill: str) -> None:
    """Place a repaired skill into its standard category group."""
    category = category_for_skill(skill)
    lower = skill.lower()
    for group in tailored.skill_groups:
        if any(i.lower() == lower for i in group.items):
            return
    for group in tailored.skill_groups:
        if group.category == category:
            group.items.append(skill)
            return
    # Create the category group if missing.
    tailored.skill_groups.append(SkillGroup(category=category, items=[skill]))


def _try_skill_repair(
    tailored: TailoredResume,
    original: ParsedResume | None,
    missing: list[JDKeyword],
) -> list[str]:
    if original is None:
        whitelist = {s.lower(): s for s in tailored.skills}
    else:
        whitelist = {s.lower(): s for s in skills_whitelist(original)}
    added: list[str] = []
    for keyword in missing:
        if keyword.in_dictionary and keyword.keyword in SKILL_SYNONYMS:
            group = [keyword.keyword, *SKILL_SYNONYMS[keyword.keyword]]
        else:
            group = [keyword.keyword, *keyword.aliases_matched]
        skill = next(
            (whitelist[a.lower()] for a in group if a.lower() in whitelist), None
        )
        if skill is not None and skill not in tailored.skills:
            tailored.skills.append(skill)
            _append_skill_to_groups(tailored, skill)
            added.append(skill)
    return added


def fit_to_pages(
    tailored: TailoredResume,
    jd_keywords: list[JDKeyword],
    target_pages: int,
    *,
    before_matched_keywords: list[str] | None = None,
    original: ParsedResume | None = None,
    template: TemplateName = "classic",
) -> tuple[TailoredResume, bytes, int, FitReport, list[str]]:
    """Render with density ladder; never drop bullets.

    Returns (final_content, pdf_bytes, page_count, fit_report, repairs).
    If dense still overflows, actual_pages may exceed requested_pages.
    """
    working = tailored.model_copy(deep=True)
    repairs: list[str] = []
    before_matched = set(before_matched_keywords or [])

    # Keyword non-regression repair (e.g. after verifier reverts) — no drops.
    if before_matched:
        missing = _missing_before_keywords(working, jd_keywords, before_matched)
        if missing:
            repairs.extend(_try_skill_repair(working, original, missing))

    pdf: bytes = b""
    pages = 0
    chosen_density: DensityStep = "normal"

    for density in DENSITY_STEPS:
        pdf, pages = render_pdf(working, density=density, template=template)
        chosen_density = density
        if pages <= target_pages:
            break
    # If still over target at densest, keep content and accept extra pages.

    fit = FitReport(
        density_step=chosen_density,
        requested_pages=target_pages,
        actual_pages=pages,
        template=template,
    )
    return working, pdf, pages, fit, list(dict.fromkeys(repairs))


# ---------------------------------------------------------------------------
# Round-trip self-check (step 8)
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower().strip()


def roundtrip_check(pdf_bytes: bytes, tailored: TailoredResume) -> RoundTripCheck:
    """Re-extract the PDF with pdfplumber and verify nothing was lost."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        extracted = "\n".join(page.extract_text() or "" for page in pdf.pages)
    haystack = _normalize(extracted)

    issues: list[str] = []

    contact = tailored.contact
    for label, value in [
        ("name", contact.name),
        ("email", contact.email),
        ("phone", contact.phone),
    ]:
        if value and _normalize(value) not in haystack:
            issues.append(f"contact field '{label}' missing from rendered PDF")

    expected_headings = []
    if tailored.summary:
        expected_headings.append("Summary")
    if tailored.skills or tailored.skill_groups:
        expected_headings.append("Skills")
    if tailored.experience:
        expected_headings.append("Experience")
    if tailored.projects:
        expected_headings.append("Projects")
    if tailored.education:
        expected_headings.append("Education")
    if tailored.certifications:
        expected_headings.append("Certifications")
    if tailored.awards:
        expected_headings.append("Awards")
    if tailored.publications:
        expected_headings.append("Publications")
    if tailored.languages:
        expected_headings.append("Languages")
    expected_headings.extend(s.heading_raw for s in tailored.other_sections)
    for heading in expected_headings:
        if _normalize(heading) not in haystack:
            issues.append(f"section heading '{heading}' missing from rendered PDF")

    for bullet in _all_bullets(tailored):
        if _normalize(bullet.text) not in haystack:
            issues.append(f"bullet {bullet.id} text missing from rendered PDF")

    # Skills should appear in PDF text for external ATS tools.
    for skill in tailored.skills:
        if skill and _normalize(skill) not in haystack:
            issues.append(f"skill '{skill}' missing from rendered PDF")

    return RoundTripCheck(passed=not issues, issues=issues)
