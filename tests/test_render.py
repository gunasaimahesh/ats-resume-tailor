"""Tests for pipeline steps 7-8: page fitting, rendering, round-trip check."""

from datetime import date

from backend.render.renderer import (
    default_target_pages,
    fit_to_pages,
    render_pdf,
    resolve_target_pages,
    roundtrip_check,
)
from backend.schema import (
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    JDKeyword,
    SkillGroup,
    TailoredBullet,
    TailoredExperienceEntry,
    TailoredResume,
)

THIS_YEAR = date.today().year


def _bullet(bid: str, text: str) -> TailoredBullet:
    return TailoredBullet(id=bid, original=text, text=text, changed=False)


def _small_resume() -> TailoredResume:
    return TailoredResume(
        contact=ContactInfo(
            name="Jane Doe", email="jane@example.com", phone="(555) 123-4567"
        ),
        summary="Engineer with production Kubernetes experience.",
        skills=["Python", "Docker", "Kubernetes"],
        experience=[
            TailoredExperienceEntry(
                company="Acme Corp",
                title="Senior Engineer",
                dates=f"Jan {THIS_YEAR - 2} – Present",
                location="Remote",
                header_raw="Senior Engineer — Acme Corp",
                bullets=[
                    _bullet("B1", "Migrated 12 services to Kubernetes"),
                    _bullet("B2", "Mentored 4 junior engineers"),
                ],
            )
        ],
        education=[
            EducationEntry(
                school="State University",
                degree="B.S. Computer Science",
                dates="2018",
                gpa="3.8",
                raw_lines=["Coursework: Algorithms, Databases"],
            )
        ],
    )


def _overflowing_resume() -> TailoredResume:
    filler = (
        "Coordinated cross-team initiative covering planning, execution, "
        "rollout, documentation and retrospective analysis across quarters "
    )
    bullets = [_bullet("B1", "Migrated services to Kubernetes clusters in production")]
    bullets += [_bullet(f"B{i}", f"{filler}(iteration {i})") for i in range(2, 40)]
    resume = _small_resume()
    resume.experience[0].bullets = bullets
    # Ensure B1 is the SOLE carrier of "Kubernetes": scrub it from elsewhere.
    resume.summary = "Engineer with broad production experience."
    resume.skills = ["Python", "Docker"]
    return resume


def _count_bullets(resume: TailoredResume) -> int:
    return sum(len(e.bullets) for e in resume.experience) + sum(
        len(p.bullets) for p in resume.projects
    )


KUBERNETES = JDKeyword(keyword="Kubernetes", importance="required")


def test_default_target_pages_heuristic():
    junior = [ExperienceEntry(header_raw="x", dates=f"{THIS_YEAR - 2} – Present")]
    senior = [ExperienceEntry(header_raw="x", dates=f"{THIS_YEAR - 8} – Present")]
    assert default_target_pages(junior) == 1
    assert default_target_pages(senior) == 2
    assert default_target_pages([]) == 1


def test_resolve_target_pages_overrides():
    resume = _small_resume()
    assert resolve_target_pages(2, None, resume) == 2
    assert resolve_target_pages("same_as_original", 3, resume) == 3
    # None + original_pages known -> prefer original (safer default).
    assert resolve_target_pages(None, 2, resume) == 2
    # No override and no original -> heuristic (2 years experience -> 1 page).
    assert resolve_target_pages(None, None, resume) == 1


def test_render_produces_pdf():
    pdf_bytes, pages = render_pdf(_small_resume())
    assert pdf_bytes.startswith(b"%PDF")
    assert pages == 1


def test_roundtrip_check_passes_for_clean_render():
    resume = _small_resume()
    pdf_bytes, _ = render_pdf(resume)
    check = roundtrip_check(pdf_bytes, resume)
    assert check.passed is True
    assert check.issues == []


def test_render_includes_skill_groups_and_education_raw_lines():
    resume = _small_resume()
    resume.skill_groups = [
        SkillGroup(category="Cloud & DevOps", items=["Kubernetes", "Docker"]),
        SkillGroup(category="Languages", items=["Python"]),
    ]
    pdf_bytes, _ = render_pdf(resume)
    import pdfplumber
    import io

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Cloud & DevOps" in text
    assert "Kubernetes" in text
    assert "Coursework: Algorithms, Databases" in text
    assert "GPA:" in text
    assert "jane@example.com" in text
    assert "State University" in text
    assert "B.S. Computer Science" in text
    # Skills must not get dual-form brackets.
    assert "(CPP)" not in text
    assert "(JS)" not in text


def test_education_not_duplicated_in_pdf():
    resume = _small_resume()
    # Simulate bad Review/edit state: raw_lines still hold the full block.
    resume.education[0].raw_lines = [
        "State University",
        "B.S. Computer Science — GPA: 3.8 2018",
        "Coursework: Algorithms, Databases",
    ]
    pdf_bytes, _ = render_pdf(resume)
    import pdfplumber
    import io

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert text.count("State University") == 1
    assert text.count("B.S. Computer Science") == 1
    assert "Coursework: Algorithms, Databases" in text
    assert "GPA: 3.8" in text


def test_fit_never_drops_bullets_uses_density_or_extra_pages():
    resume = _overflowing_resume()
    before_count = _count_bullets(resume)

    _, unfitted_pages = render_pdf(resume)
    assert unfitted_pages > 1

    final, pdf_bytes, pages, fit, repairs = fit_to_pages(
        resume, [KUBERNETES], 1
    )

    assert _count_bullets(final) == before_count
    remaining_ids = [b.id for e in final.experience for b in e.bullets]
    assert "B1" in remaining_ids
    assert len(remaining_ids) == before_count
    assert fit.requested_pages == 1
    assert fit.actual_pages == pages
    assert fit.density_step in ("normal", "compact", "dense")
    # May need extra pages; never drop content.
    assert pages >= 1
    check = roundtrip_check(pdf_bytes, final)
    assert check.passed is True


def test_two_column_template_renders_and_keeps_content():
    resume = _small_resume()
    resume.skill_groups = [
        SkillGroup(category="Languages", items=["Python"]),
        SkillGroup(category="Cloud & DevOps", items=["Docker", "Kubernetes"]),
    ]
    final, pdf_bytes, pages, fit, _repairs = fit_to_pages(
        resume, [KUBERNETES], 1, template="two_column"
    )
    assert fit.template == "two_column"
    assert _count_bullets(final) == _count_bullets(resume)
    assert pdf_bytes.startswith(b"%PDF")
    check = roundtrip_check(pdf_bytes, final)
    assert check.passed is True
    assert pages >= 1


def test_fit_preserves_sole_keyword_carrier_without_drops():
    """Overflow fitting must keep every bullet, including sole keyword carriers."""
    resume = _overflowing_resume()
    resume.experience[0].bullets[0] = _bullet(
        "B1", "Migrated services to Kubernetess clusters in production"
    )
    resume.summary = "Engineer with broad production experience."
    resume.skills = ["Python", "Docker"]
    before_count = _count_bullets(resume)

    final, _pdf, pages, fit, _repairs = fit_to_pages(
        resume,
        [KUBERNETES],
        1,
        before_matched_keywords=["Kubernetes"],
    )
    remaining_ids = [b.id for e in final.experience for b in e.bullets]
    assert "B1" in remaining_ids
    assert len(remaining_ids) == before_count
    assert fit.actual_pages == pages


def test_roundtrip_check_reports_missing_content():
    resume = _small_resume()
    pdf_bytes, _ = render_pdf(resume)
    resume.experience[0].bullets.append(
        _bullet("B99", "This text is definitely not in the rendered document")
    )
    check = roundtrip_check(pdf_bytes, resume)
    assert check.passed is False
    assert any("B99" in issue for issue in check.issues)
