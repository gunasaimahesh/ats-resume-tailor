"""Tests for pipeline step 1: section, bullet, contact, and skills detection."""

from backend.parsing import parse_resume_text

SAMPLE_RESUME = """\
JANE DOE
jane.doe@example.com | (555) 123-4567 | linkedin.com/in/janedoe | github.com/janedoe

Summary
Product-minded software engineer with 6 years of experience building
data-heavy web applications.

Work History
Senior Software Engineer — Acme Corp    Jan 2021 – Present
• Led migration of 12 services to Kubernetes, cutting deploy time by 40%
• Mentored 4 junior engineers across two teams
Software Engineer — Globex Inc    Jun 2018 – Dec 2020
• Built REST APIs in Python and FastAPI serving 2M requests per day
- Reduced p95 latency from 800ms to 200ms by adding Redis caching

Education
B.S. Computer Science, State University, 2018

Technical Skills
Languages: Python, TypeScript, SQL
Infrastructure: Docker, Kubernetes, AWS

Projects
Resume Tailor — side project
• Built an ATS resume tool with React and FastAPI

CERTIFICATIONS
AWS Certified Solutions Architect
"""


def test_contact_info():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert resume.contact.name == "JANE DOE"
    assert resume.contact.email == "jane.doe@example.com"
    assert resume.contact.phone is not None
    assert "555" in resume.contact.phone
    assert resume.contact.linkedin == "linkedin.com/in/janedoe"
    assert resume.contact.github == "github.com/janedoe"


def test_phone_formats_including_indian():
    formats = [
        "+91 9959562713",
        "919959562713",
        "+919959562713",
        "9959562713",
        "+91-99595-62713",
        "(+91) 9959562713",
        "(555) 123-4567",
    ]
    for phone in formats:
        text = f"JANE DOE\njane@example.com | {phone}\n\nExperience\nEngineer — Acme\n• Did things"
        resume = parse_resume_text(text)
        assert resume.contact.phone == phone, f"failed for {phone!r}"


def test_summary_detected():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert resume.summary is not None
    assert resume.summary.startswith("Product-minded software engineer")


def test_summary_fallback_from_header_prose():
    text = """\
JANE DOE
jane@example.com | (555) 123-4567
Seasoned backend engineer with deep experience in distributed systems and cloud platforms across multiple production environments.

Experience
Software Engineer — Acme  2020 – 2022
• Shipped APIs
"""
    resume = parse_resume_text(text)
    assert resume.summary is not None
    assert "distributed systems" in resume.summary


def test_experience_entries_and_headers():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert len(resume.experience) == 2

    first, second = resume.experience
    assert first.title == "Senior Software Engineer"
    assert first.company == "Acme Corp"
    assert first.dates == "Jan 2021 – Present"
    assert second.title == "Software Engineer"
    assert second.company == "Globex Inc"
    assert second.dates == "Jun 2018 – Dec 2020"


def test_bullets_numbered_sequentially():
    resume = parse_resume_text(SAMPLE_RESUME)
    all_bullets = [
        b for entry in resume.experience for b in entry.bullets
    ] + [b for project in resume.projects for b in project.bullets]

    assert [b.id for b in all_bullets] == ["B1", "B2", "B3", "B4", "B5"]
    assert all_bullets[0].text.startswith("Led migration of 12 services")
    # Both "•" and "-" markers are recognized:
    assert all_bullets[3].text.startswith("Reduced p95 latency")


def test_skills_flattened_without_category_prefixes():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert resume.skills == [
        "Python", "TypeScript", "SQL", "Docker", "Kubernetes", "AWS",
    ]
    assert len(resume.skill_groups) == 2
    assert resume.skill_groups[0].category == "Languages"
    assert resume.skill_groups[0].items == ["Python", "TypeScript", "SQL"]


def test_projects_detected():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert len(resume.projects) == 1
    assert resume.projects[0].name.startswith("Resume Tailor")
    assert len(resume.projects[0].bullets) == 1


WRAPPED_RESUME = """\
GUNA MAHESH
guna@example.com | +91 9959562713

Experience
Senior Software Engineer  Enphase Energy Bangalore, India  06/2024 – 07/2026
• Developed backend services in Ruby on Rails for the installer platform, ramping up quickly on a large, unfamiliar
codebase.
• Worked closely with development, test, and product teams on production services to deliver
high-quality releases.
Software Development Engineer  Amazon Bangalore, India  09/2022 – 03/2024
• Designed distributed authorization workflows for subscription re-authorization, owning the feature
end-to-end and enabling QR-based authentication at scale.
• Developed backend payment-flow integrations for Credit Card Installments on Smart TVs in Brazil, supporting
2–12 month subscription plans and contributing
to 15k+ Prime subscription signups
"""


def test_wrapped_bullet_lines_do_not_create_fake_entries():
    resume = parse_resume_text(WRAPPED_RESUME)

    # Exactly the two real jobs — no ghost entries from wrapped fragments.
    assert len(resume.experience) == 2
    first, second = resume.experience

    assert first.title == "Senior Software Engineer"
    assert first.company == "Enphase Energy"
    assert second.title == "Software Development Engineer"
    assert second.company == "Amazon"

    # Continuation fragments were re-attached to their bullets.
    assert first.bullets[0].text.endswith("unfamiliar codebase.")
    assert first.bullets[1].text.endswith("deliver high-quality releases.")
    assert second.bullets[0].text.endswith("QR-based authentication at scale.")
    # Multi-line wrap (three lines) joins fully:
    assert second.bullets[1].text.endswith("15k+ Prime subscription signups")
    assert len(first.bullets) == 2
    assert len(second.bullets) == 2


def test_location_extracted_separately():
    resume = parse_resume_text(WRAPPED_RESUME)
    first, second = resume.experience

    assert first.location == "Bangalore, India"
    assert first.dates == "06/2024 – 07/2026"
    assert second.location == "Bangalore, India"
    assert second.dates == "09/2022 – 03/2024"


def test_glyphless_bullets_under_multiple_jobs():
    text = """\
GUNA MAHESH
guna@example.com

Experience
Senior Software Engineer  Enphase Energy Bangalore, India  06/2024 – 07/2026
Developed backend services in Ruby on Rails for the installer platform at scale.
Worked closely with development, test, and product teams on production services.
Software Development Engineer  Amazon Bangalore, India  09/2022 – 03/2024
Designed distributed authorization workflows for subscription re-authorization end-to-end.
Developed backend payment-flow integrations for Credit Card Installments on Smart TVs.
"""
    resume = parse_resume_text(text)
    assert len(resume.experience) == 2
    assert resume.experience[0].company == "Enphase Energy"
    assert resume.experience[1].company == "Amazon"
    assert len(resume.experience[0].bullets) == 2
    assert len(resume.experience[1].bullets) == 2
    assert resume.experience[0].bullets[0].text.startswith("Developed backend")


def test_multiword_city_location():
    text = (
        "JANE DOE\n\nExperience\n"
        "Software Engineer  Stripe  San Francisco, CA  2021 – 2023\n"
        "• Built payment APIs"
    )
    entry = parse_resume_text(text).experience[0]
    assert entry.company == "Stripe"
    assert entry.location == "San Francisco, CA"


def test_titlecase_other_sections_do_not_leak():
    text = (
        "JOHN DOE\n\nExperience\n"
        "Software Engineer  Acme  2020 – 2022\n"
        "• Shipped a payments service used by many teams to reduce page latency\n"
        "at scale.\n"
        "Publications\n"
        "eCharge: Deep RL Framework for EV Charging Route Planning — IEEE, 2025.\n"
        "Skills\n"
        "Distributed Systems & Backend: Microservices, Spring Boot\n"
        "Achievements\n"
        "• Max Codeforces Rating: 1607 (Expert)\n"
    )
    resume = parse_resume_text(text)

    # Publications did not get glued onto the last experience bullet.
    assert len(resume.experience) == 1
    assert resume.experience[0].bullets[-1].text.endswith("at scale.")

    assert resume.other_sections == []
    assert len(resume.publications) == 1
    assert "eCharge" in resume.publications[0].text

    # Achievements structured, not polluted into skills.
    assert resume.skills == ["Microservices", "Spring Boot"]
    assert len(resume.awards) == 1
    assert "Codeforces" in resume.awards[0].text


def test_education_structured_classic():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert len(resume.education) == 1
    edu = resume.education[0]
    assert edu.degree is not None and "Computer Science" in edu.degree
    assert edu.school is not None and "State University" in edu.school


def test_education_keeps_campus_comma_in_school():
    text = """\
GUNA SAI MAHESH ATLURI
gunasaimahesh@gmail.com

Education
Indian Institute of Technology, Roorkee
B.Tech in Computer Science and Engineering (CGPA : 8.582) 11/2020 - 05/2024

Experience
Software Engineer — Acme  2024 – Present
• Built things
"""
    resume = parse_resume_text(text)
    edu = resume.education[0]
    assert edu.school == "Indian Institute of Technology, Roorkee"
    # Must not peel campus into a bare location field as if it were a new line.
    assert edu.location != "Roorkee"
    assert edu.degree is not None and "B.Tech" in edu.degree
    assert edu.gpa == "8.582"
    # Structured fields already cover the block — no duplicate raw copy.
    assert edu.raw_lines == []


def test_education_iit_style_with_cgpa():
    text = """\
GUNA SAI MAHESH ATLURI
gunasaimahesh@gmail.com | +91 9959562713

Education
Indian Institute of Technology, Roorkee Roorkee, India
B.Tech in Computer Science and Engineering (CGPA : 8.582) 11/2020 - 05/2024

Experience
Software Engineer — Acme  2024 – Present
• Built things
"""
    resume = parse_resume_text(text)
    assert len(resume.education) == 1
    edu = resume.education[0]
    assert edu.school is not None
    assert "Indian Institute of Technology, Roorkee" in edu.school
    assert edu.degree is not None and "B.Tech" in edu.degree
    assert edu.gpa == "8.582"
    assert edu.dates is not None and "2020" in edu.dates and "2024" in edu.dates
    assert edu.raw_lines == []


def test_education_keeps_coursework_extra():
    text = """\
JANE DOE
jane@example.com

Education
State University
B.S. Computer Science, 2018
Coursework: Algorithms, Databases

Experience
Engineer — Acme  2020 – Present
• Built things
"""
    resume = parse_resume_text(text)
    edu = resume.education[0]
    assert any("Coursework" in line for line in edu.raw_lines)


def test_experience_comma_wrap_stays_one_bullet():
    text = """\
JANE DOE
jane@example.com

Experience
Software Engineer  Acme  2020 – 2022
• Developed backend services in Java, Spring Boot, and
Kafka for the installer platform.
• Mentored junior engineers on production systems.
"""
    resume = parse_resume_text(text)
    assert len(resume.experience) == 1
    bullets = resume.experience[0].bullets
    assert len(bullets) == 2
    assert "Java, Spring Boot, and Kafka" in bullets[0].text
    assert bullets[0].text.endswith("platform.")


def test_glyphless_comma_wrap_not_new_bullet():
    text = """\
JANE DOE
jane@example.com

Experience
Software Engineer  Acme Bangalore, India  2020 – 2022
Developed backend services in Java, Spring Boot, and
Kafka for the installer platform at production scale.
Mentored junior engineers across two product teams carefully.
"""
    resume = parse_resume_text(text)
    bullets = resume.experience[0].bullets
    assert len(bullets) == 2
    assert "Kafka" in bullets[0].text
    assert bullets[0].text.endswith("scale.")


def test_skills_rejoin_comma_wrap_one_group():
    text = """\
JANE DOE
jane@example.com

Skills
Languages: Java, C++, SQL,
JavaScript, TypeScript
"""
    resume = parse_resume_text(text)
    assert len(resume.skill_groups) == 1
    assert resume.skill_groups[0].category == "Languages"
    assert resume.skills == ["Java", "C++", "SQL", "JavaScript", "TypeScript"]


def test_headline_from_header():
    text = """\
JANE DOE
Senior Software Engineer
jane@example.com | (555) 123-4567

Experience
Engineer — Acme  2020 – 2021
• Did work
"""
    resume = parse_resume_text(text)
    assert resume.headline == "Senior Software Engineer"


def test_certifications_structured():
    resume = parse_resume_text(SAMPLE_RESUME)
    assert len(resume.certifications) == 1
    assert resume.certifications[0].name == "AWS Certified Solutions Architect"


def test_languages_structured():
    text = """\
JANE DOE
jane@example.com

Languages
English (Fluent), Hindi — Native

Experience
Engineer — Acme  2020 – 2021
• Did work
"""
    resume = parse_resume_text(text)
    assert len(resume.languages) >= 2
    names = {lang.language for lang in resume.languages}
    assert "English" in names
    assert "Hindi" in names
