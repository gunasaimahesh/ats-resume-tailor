"""Pipeline step 1: local resume text extraction and structure detection.

PDF text comes from pdfplumber, DOCX from python-docx. Everything after that
is pure-text heuristics: section headings, experience/project entries, bullet
numbering (B1, B2, ...), contact info, structured education/certs/etc., and
categorized skills.

Comma rule: commas never start a new bullet/skill row. Only a sentence-ending
full stop (or a real bullet glyph) may.
"""

import io
import re
from itertools import count

from backend.schema import (
    AwardEntry,
    Bullet,
    CertificationEntry,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    LanguageEntry,
    ParsedResume,
    ProjectEntry,
    PublicationEntry,
    SectionBlock,
    SkillGroup,
)

# ---------------------------------------------------------------------------
# File extraction
# ---------------------------------------------------------------------------


def extract_text_from_pdf(data: bytes) -> tuple[str, int]:
    """Returns (text, page_count)."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            # Scale the word-gap threshold to each font's size; the fixed
            # default jams words together on tightly-kerned fonts.
            text = page.extract_text(x_tolerance_ratio=0.3) or ""
            pages.append(text)
    return "\n".join(pages), len(pages)


def extract_text_from_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # python-docx drops list glyphs; restore one so bullet detection works.
        style = (para.style.name if para.style else "").lower()
        if ("list" in style or "bullet" in style) and not _BULLET_RE.match(text):
            text = f"• {text}"
        lines.append(text)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_SECTION_VARIANTS: dict[str, set[str]] = {
    "summary": {
        "summary", "professional summary", "career summary", "executive summary",
        "profile", "professional profile", "objective", "career objective",
        "about", "about me",
    },
    "experience": {
        "experience", "work experience", "work history", "employment",
        "employment history", "professional experience", "relevant experience",
        "career history", "professional background",
    },
    "education": {
        "education", "academic background", "academics",
        "education and training",
    },
    "skills": {
        "skills", "technical skills", "core competencies", "key skills",
        "skills and tools", "technologies", "technical proficiencies",
        "tech stack", "core skills", "areas of expertise",
    },
    "projects": {
        "projects", "personal projects", "selected projects",
        "academic projects", "side projects", "key projects",
    },
    "certifications": {
        "certifications", "certificates", "licenses and certifications",
        "licenses", "professional certifications",
    },
    "awards": {
        "awards", "honors", "achievements", "accomplishments",
        "awards and honors", "honors and awards",
    },
    "publications": {
        "publications", "research publications", "papers",
        "selected publications",
    },
    "languages": {
        "languages", "language proficiency", "spoken languages",
    },
}

_OTHER_SECTION_HEADINGS: set[str] = {
    "courses", "coursework", "relevant coursework",
    "leadership", "activities", "extracurricular activities",
    "extracurriculars", "volunteering", "volunteer experience",
    "volunteer work", "interests", "hobbies", "research",
    "research experience", "positions of responsibility",
    "education and certifications",
}

_BULLET_RE = re.compile(r"^\s*(?:[•●▪◦‣·∙*–—-]|\d+[.)])\s+")

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_TOKEN = rf"(?:{_MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_DATE_RANGE_RE = re.compile(
    rf"{_DATE_TOKEN}\s*(?:[-–—~]|to|until)\s*(?:{_DATE_TOKEN}|present|current|now|ongoing)"
    rf"|{_DATE_TOKEN}",
    re.IGNORECASE,
)

_TITLE_KEYWORD_RE = re.compile(
    r"\b(engineer|developer|programmer|manager|analyst|intern|consultant|"
    r"architect|scientist|designer|lead|director|administrator|specialist|"
    r"head|officer|founder|president|cto|ceo|vp)\b",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"[+(]{0,2}\d[\d\s().-]{7,}\d")
_LINK_RE = re.compile(
    r"https?://\S+|(?:www\.)\S+|(?:linkedin\.com|github\.com|gitlab\.com)/\S+",
    re.IGNORECASE,
)

_GPA_RE = re.compile(
    r"(?:CGPA|GPA|C\.?G\.?P\.?A\.?)\s*[:=]?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    r"\b(?:B\.?\s?Tech|B\.?\s?E\.?|B\.?\s?S\.?|B\.?\s?A\.?|B\.?\s?Sc|"
    r"M\.?\s?Tech|M\.?\s?S\.?|M\.?\s?A\.?|M\.?\s?Sc|MBA|Ph\.?\s?D\.?|"
    r"Bachelor(?:'s)?|Master(?:'s)?|Doctorate|Associate)\b",
    re.IGNORECASE,
)
_SCHOOL_HINT_RE = re.compile(
    r"\b(?:University|Institute|College|School|IIT|NIT|IIIT|Polytechnic)\b",
    re.IGNORECASE,
)

_SENTENCE_END_RE = re.compile(r'[.!?]["\')\]]*\s*$')


def _ends_sentence(text: str) -> bool:
    """True if text ends with a sentence terminator (. ! ?), ignoring quotes."""
    return bool(_SENTENCE_END_RE.search(text.rstrip()))


def _normalize_heading(line: str) -> str:
    text = line.strip().rstrip(":").lower().replace("&", "and")
    text = re.sub(r"[^a-z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _match_section_heading(line: str) -> str | None:
    """Return the canonical section name if this line is a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 40 or _BULLET_RE.match(stripped):
        return None
    normalized = _normalize_heading(stripped)
    for name, variants in _SECTION_VARIANTS.items():
        if normalized in variants:
            return name
    if normalized in _OTHER_SECTION_HEADINGS:
        return "other"
    return None


def _is_generic_heading(line: str) -> bool:
    """An all-caps short line we treat as an unknown section heading."""
    stripped = line.strip().rstrip(":")
    return (
        3 <= len(stripped) <= 30
        and len(stripped.split()) <= 4
        and stripped.isupper()
        and not any(ch.isdigit() for ch in stripped)
        and not _BULLET_RE.match(line)
    )


def _split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """Split lines into a pre-section header block and (name, heading, lines) blocks."""
    header_block: list[str] = []
    blocks: list[tuple[str, str, list[str]]] = []
    current: list[str] | None = None

    for line in lines:
        if not line.strip():
            continue
        section = _match_section_heading(line)
        if section is None and blocks and _is_generic_heading(line):
            section = "other"
        if section is not None:
            current = []
            blocks.append((section, line.strip(), current))
        elif current is not None:
            current.append(line.strip())
        else:
            header_block.append(line.strip())
    return header_block, blocks


# ---------------------------------------------------------------------------
# Contact / headline / summary
# ---------------------------------------------------------------------------


def _classify_link(url: str) -> tuple[str, str]:
    cleaned = url.rstrip(".,;)")
    lower = cleaned.lower()
    if "linkedin.com" in lower:
        return "linkedin", cleaned
    if "github.com" in lower or "gitlab.com" in lower:
        return "github", cleaned
    if lower.startswith("http") or lower.startswith("www."):
        return "website", cleaned
    return "other", cleaned


def _is_contactish_line(line: str, contact: ContactInfo) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if contact.name and stripped == contact.name:
        return True
    if contact.email and contact.email in stripped:
        return True
    if contact.phone and contact.phone in stripped:
        return True
    if contact.location and stripped == contact.location:
        return True
    if _LINK_RE.search(stripped) or _EMAIL_RE.search(stripped):
        return True
    if _PHONE_RE.search(stripped) and sum(ch.isdigit() for ch in stripped) >= 9:
        return True
    return False


def _parse_contact(header_lines: list[str]) -> ContactInfo:
    contact = ContactInfo()
    joined = "\n".join(header_lines)

    if match := _EMAIL_RE.search(joined):
        contact.email = match.group(0)

    for match in _PHONE_RE.finditer(joined):
        candidate = match.group(0)
        if sum(ch.isdigit() for ch in candidate) >= 9:
            contact.phone = candidate.strip()
            break

    leftovers: list[str] = []
    for link in _LINK_RE.findall(joined):
        kind, cleaned = _classify_link(link)
        if kind == "linkedin" and not contact.linkedin:
            contact.linkedin = cleaned
        elif kind == "github" and not contact.github:
            contact.github = cleaned
        elif kind == "website" and not contact.website:
            contact.website = cleaned
        else:
            leftovers.append(cleaned)
    contact.links = leftovers

    for line in header_lines[:5]:
        words = line.split()
        if (
            1 < len(words) <= 5
            and not any(ch.isdigit() for ch in line)
            and "@" not in line
            and not _LINK_RE.search(line)
            and all(re.fullmatch(r"[A-Za-z.'-]+", w) for w in words)
        ):
            contact.name = line.strip()
            break

    for line in header_lines:
        loc, rest = _split_location(line.strip())
        if loc and (rest is None or rest == "" or len((rest or "").split()) <= 2):
            if rest is None or not rest.strip() or (
                len(line.split()) <= 6 and not _EMAIL_RE.search(line)
            ):
                if not contact.location and "," in line and not _LINK_RE.search(line):
                    if _COUNTRY_RE.search(line) and len(line.split()) <= 6:
                        contact.location = loc
                        break

    return contact


def _headline_from_header(header_lines: list[str], contact: ContactInfo) -> str | None:
    """Short professional title under the name (not long prose summary)."""
    for line in header_lines:
        stripped = line.strip()
        if _is_contactish_line(stripped, contact):
            continue
        words = stripped.split()
        if not words or not stripped[0].isalpha():
            continue
        # Headline: short title-like line; longer prose is summary fallback.
        if 1 <= len(words) <= 12 and not _ends_sentence(stripped):
            return stripped
    return None


def _summary_from_header(
    header_lines: list[str], contact: ContactInfo, headline: str | None
) -> str | None:
    prose: list[str] = []
    for line in header_lines:
        stripped = line.strip()
        if _is_contactish_line(stripped, contact):
            continue
        if headline and stripped == headline:
            continue
        words = stripped.split()
        if len(words) >= 8 and stripped[0].isalpha():
            prose.append(stripped)
    if not prose:
        return None
    return " ".join(prose).strip() or None


# ---------------------------------------------------------------------------
# Experience / projects
# ---------------------------------------------------------------------------


def _extract_dates(text: str) -> tuple[str | None, str]:
    match = _DATE_RANGE_RE.search(text)
    if not match:
        return None, text
    remainder = text[: match.start()] + text[match.end() :]
    return match.group(0).strip(), remainder


_HEADER_SPLIT_RE = re.compile(r"\s*\|\s*|\s+[–—]\s+|\s+-\s+|\t+| {2,}|\s+at\s+")

_COUNTRY_RE = re.compile(
    r"India|USA|US|U\.S\.A?\.?|United States|UK|U\.K\.|United Kingdom|Canada|"
    r"Germany|France|Spain|Italy|Netherlands|Poland|Ireland|Sweden|"
    r"Switzerland|Singapore|Australia|Japan|China|Brazil|Mexico|UAE|Israel|"
    r"Remote|[A-Z]{2}"
)

_CITY_PREFIXES = {"new", "san", "los", "las", "st", "st.", "sao", "são", "rio",
                  "hong", "ho", "tel", "salt", "kansas", "mexico", "cape",
                  "port", "abu", "navi"}


def _split_location(part: str) -> tuple[str | None, str | None]:
    """Split a trailing 'City, Country' off a header part (jobs, not schools)."""
    if "," not in part:
        return None, part
    head, tail = part.rsplit(",", 1)
    tail = tail.strip().rstrip(".")
    if not _COUNTRY_RE.fullmatch(tail):
        return None, part
    words = head.split()
    if not words or not words[-1][:1].isupper():
        return None, part
    take = 2 if len(words) >= 2 and words[-2].lower() in _CITY_PREFIXES else 1
    city = " ".join(words[-take:])
    rest = " ".join(words[:-take]).strip(" ,;-–—|")
    return f"{city}, {tail}", rest or None


def _looks_like_entry_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or not stripped[0].isupper():
        return False
    if _DATE_RANGE_RE.search(stripped) or _TITLE_KEYWORD_RE.search(stripped):
        return True
    words = stripped.split()
    if len(words) > 8:
        return False
    capitalized = sum(1 for w in words if w[:1].isupper())
    return capitalized >= max(2, round(len(words) * 0.6))


def _looks_like_bullet_prose(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _BULLET_RE.match(stripped) or _looks_like_entry_header(stripped):
        return False
    words = stripped.split()
    if len(words) < 5:
        return False
    if not stripped[0].isalpha():
        return False
    return True


def _parse_entry_header(header_lines: list[str]) -> ExperienceEntry:
    dates: str | None = None
    location: str | None = None
    parts: list[str] = []
    for line in header_lines:
        found, remainder = _extract_dates(line)
        if found and dates is None:
            dates = found
        for part in _HEADER_SPLIT_RE.split(remainder):
            part = part.strip(" ,;-–—|")
            if not part:
                continue
            loc, rest = _split_location(part)
            if loc and location is None:
                location = loc
            if rest:
                parts.append(rest)

    title = company = None
    remaining: list[str] = []
    for part in parts:
        if title is None and _TITLE_KEYWORD_RE.search(part):
            title = part
        else:
            remaining.append(part)
    if remaining:
        company = remaining[0]
    if title is None and len(remaining) > 1:
        title = remaining[1]

    return ExperienceEntry(
        company=company,
        title=title,
        dates=dates,
        location=location,
        header_raw=" / ".join(header_lines),
    )


def _parse_experience(lines: list[str], bullet_ids: "count[int]") -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    pending_header: list[str] = []
    current: ExperienceEntry | None = None

    def flush_current() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    def ensure_current() -> None:
        nonlocal current, pending_header
        if current is None:
            current = _parse_entry_header(pending_header)
            pending_header = []

    def add_bullet(text: str) -> None:
        ensure_current()
        assert current is not None
        current.bullets.append(Bullet(id=f"B{next(bullet_ids)}", text=text))

    def append_or_new_glyphless(stripped: str) -> None:
        """Join wraps; new glyph-less bullet only after a full stop."""
        assert current is not None and current.bullets
        prev = current.bullets[-1].text
        if _ends_sentence(prev) and _looks_like_bullet_prose(stripped):
            add_bullet(stripped)
        else:
            current.bullets[-1].text = (prev + " " + stripped).strip()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if _BULLET_RE.match(stripped):
            add_bullet(_BULLET_RE.sub("", stripped).strip())
            continue

        if current is not None and current.bullets and not _looks_like_entry_header(stripped):
            append_or_new_glyphless(stripped)
            continue

        if current is not None and current.bullets and _looks_like_entry_header(stripped):
            flush_current()
            pending_header = [stripped]
            continue

        if pending_header and _looks_like_bullet_prose(stripped):
            add_bullet(stripped)
            continue

        if current is not None and current.bullets:
            append_or_new_glyphless(stripped)
            continue

        if current is not None and _looks_like_bullet_prose(stripped):
            add_bullet(stripped)
            continue

        if current is not None:
            flush_current()
        pending_header.append(stripped)

    if current is not None:
        entries.append(current)
    elif pending_header:
        entries.append(_parse_entry_header(pending_header))
    return entries


def _parse_projects(lines: list[str], bullet_ids: "count[int]") -> list[ProjectEntry]:
    projects: list[ProjectEntry] = []
    current: ProjectEntry | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _BULLET_RE.match(stripped):
            if current is not None:
                text = _BULLET_RE.sub("", stripped).strip()
                current.bullets.append(Bullet(id=f"B{next(bullet_ids)}", text=text))
            continue
        if current is not None and current.bullets and not _looks_like_entry_header(stripped):
            prev = current.bullets[-1].text
            if _ends_sentence(prev) and _looks_like_bullet_prose(stripped):
                current.bullets.append(Bullet(id=f"B{next(bullet_ids)}", text=stripped))
            else:
                current.bullets[-1].text = (prev + " " + stripped).strip()
            continue

        dates, remainder = _extract_dates(stripped)
        url = None
        if link := _LINK_RE.search(remainder):
            url = link.group(0).rstrip(".,;)")
            remainder = (remainder[: link.start()] + remainder[link.end() :]).strip()

        tech = None
        tech_split = re.split(r"\s+[|•]\s+", remainder, maxsplit=1)
        name = tech_split[0].strip(" ,;-–—|")
        if len(tech_split) > 1 and not _DEGREE_RE.search(tech_split[1]):
            tech = tech_split[1].strip()

        current = ProjectEntry(name=name or stripped, dates=dates, url=url, tech=tech)
        projects.append(current)
    return projects


# ---------------------------------------------------------------------------
# Skills — rejoin comma wraps; one group per category
# ---------------------------------------------------------------------------


def _rejoin_skill_lines(lines: list[str]) -> list[str]:
    """Merge soft-wrapped skill lines broken after a comma into one logical line."""
    rejoined: list[str] = []
    buf = ""
    for raw in lines:
        line = _BULLET_RE.sub("", raw).strip()
        if not line:
            continue
        if not buf:
            buf = line
            continue
        # New category line (has "Label:") starts a fresh buffer.
        if ":" in line and len(line.split(":", 1)[0].split()) <= 5:
            rejoined.append(buf)
            buf = line
            continue
        # Previous line looks mid-list (ends with comma / separator) → join.
        if buf.rstrip().endswith((",", ";", "|", "•", "·")):
            buf = buf.rstrip() + " " + line
        else:
            rejoined.append(buf)
            buf = line
    if buf:
        rejoined.append(buf)
    return rejoined


def _parse_skills(lines: list[str]) -> tuple[list[SkillGroup], list[str]]:
    groups: list[SkillGroup] = []
    flat: list[str] = []
    seen: set[str] = set()

    def add_items(category: str | None, items: list[str]) -> None:
        cleaned = []
        for token in items:
            token = token.strip(" .")
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(token)
            flat.append(token)
        if cleaned:
            groups.append(SkillGroup(category=category, items=cleaned))

    for line in _rejoin_skill_lines(lines):
        category: str | None = None
        body = line
        if ":" in line:
            prefix, rest = line.split(":", 1)
            if len(prefix.split()) <= 5:
                category = prefix.strip()
                body = rest
        items = [t.strip(" .") for t in re.split(r"[,;|•·]", body) if t.strip(" .")]
        add_items(category, items)

    return groups, flat


# ---------------------------------------------------------------------------
# Education — keep campus commas inside school name
# ---------------------------------------------------------------------------


def _strip_trailing_country(text: str) -> tuple[str, str | None]:
    """If text ends with ', Country', return (remainder, 'City?, Country') location.

    Does not peel an intermediate campus city from school names like
    'Indian Institute of Technology, Roorkee'.
    """
    if "," not in text:
        return text, None
    head, tail = text.rsplit(",", 1)
    tail = tail.strip().rstrip(".")
    if not _COUNTRY_RE.fullmatch(tail):
        return text, None
    head = head.strip()
    # If head already looks like a complete school (has Institute/University
    # and may contain its own campus comma), keep head intact as school and
    # only record the country (optionally with a trailing city word).
    if _SCHOOL_HINT_RE.search(head):
        words = head.split()
        # "… Roorkee" before ", India" → location "Roorkee, India", school loses
        # only that trailing city if it is duplicated; otherwise keep school full
        # including campus comma.
        if words and words[-1][:1].isupper() and not _SCHOOL_HINT_RE.search(words[-1]):
            # Trailing city before country — but if school already has ", City"
            # keep the campus in school and set location to "City, Country".
            city = words[-1]
            if f", {city}" in head or f",{city}" in head.replace(" ", ""):
                return head, f"{city}, {tail}"
            # "IIT Roorkee, India" without comma before city
            school = " ".join(words[:-1]).strip(" ,")
            if school and _SCHOOL_HINT_RE.search(school):
                return school, f"{city}, {tail}"
        return head, tail
    return text, None


def _parse_one_education_block(block_lines: list[str]) -> EducationEntry:
    raw = list(block_lines)
    school = degree = gpa = location = dates = None

    school_lines: list[str] = []
    degree_lines: list[str] = []

    for line in block_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Prefer school-hint lines as whole school names (commas kept).
        if _SCHOOL_HINT_RE.search(stripped) and not _DEGREE_RE.search(stripped):
            cleaned = _GPA_RE.sub("", stripped)
            found_dates, cleaned = _extract_dates(cleaned)
            if found_dates and dates is None:
                dates = found_dates
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;-–—|")
            school_part, loc = _strip_trailing_country(cleaned)
            if loc and location is None:
                location = loc if "," in loc else None
                # If loc is bare country, still ok as location
                if location is None and _COUNTRY_RE.fullmatch(loc or ""):
                    location = loc
            school_lines.append(school_part)
            continue

        found_dates, rem = _extract_dates(stripped)
        if found_dates and dates is None:
            dates = found_dates
        if gpa_match := _GPA_RE.search(rem):
            gpa = gpa_match.group(1)
            rem = rem[: gpa_match.start()] + rem[gpa_match.end() :]
        rem = re.sub(r"[()]", " ", rem)
        rem = re.sub(r"\s+", " ", rem).strip(" ,;-–—|")
        if not rem:
            continue
        if _DEGREE_RE.search(rem):
            degree_lines.append(rem)
        elif _SCHOOL_HINT_RE.search(rem):
            school_part, loc = _strip_trailing_country(rem)
            if loc and location is None:
                location = loc if "," in (loc or "") else loc
            school_lines.append(school_part)
        else:
            # Ambiguous short line — attach to degree if we have one, else school.
            if degree_lines or _DEGREE_RE.search(rem):
                degree_lines.append(rem)
            else:
                school_lines.append(rem)

    if school_lines:
        school = " ".join(school_lines).strip()
        # De-dupe "Roorkee Roorkee" when location also has the city.
        if location:
            city = location.split(",")[0].strip()
            if city:
                school = re.sub(
                    rf"\b{re.escape(city)}\s+{re.escape(city)}\b", city, school, flags=re.I
                ).strip()

    if degree_lines:
        degree = " ".join(degree_lines).strip()

    # Classic single-line: "B.S. Computer Science, State University, 2018"
    if school is None and degree and "," in degree and _DEGREE_RE.search(degree):
        left, right = degree.split(",", 1)
        left, right = left.strip(), right.strip(" ,;-–—|")
        right = re.sub(r",?\s*\d{4}\s*$", "", right).strip(" ,")
        if _DEGREE_RE.search(left) and right and _SCHOOL_HINT_RE.search(right):
            degree, school = left, right
        elif _DEGREE_RE.search(left) and right and school is None:
            degree, school = left, right

    if school is None and degree is None and block_lines:
        joined = " ".join(block_lines)
        found_dates, rem = _extract_dates(joined)
        dates = dates or found_dates
        if gpa_match := _GPA_RE.search(rem):
            gpa = gpa_match.group(1)
            rem = rem[: gpa_match.start()] + rem[gpa_match.end() :]
        rem = re.sub(r"[()]", " ", rem)
        rem = re.sub(r"\s+", " ", rem).strip(" ,;-–—|")
        if _DEGREE_RE.search(rem) and "," in rem:
            left, right = rem.split(",", 1)
            if _DEGREE_RE.search(left.strip()):
                degree = left.strip()
                school = right.strip(" ,;-–—|")
                school = re.sub(r",?\s*\d{4}\s*$", "", school).strip(" ,")
        elif rem:
            school = rem

    school = school or None
    degree = degree or None
    extras = _education_extra_lines(
        block_lines,
        school=school,
        degree=degree,
        gpa=gpa,
        location=location,
        dates=dates,
    )
    return EducationEntry(
        school=school,
        degree=degree,
        gpa=gpa,
        location=location,
        dates=dates,
        raw_lines=extras,
    )


_EDU_EXTRA_HINT_RE = re.compile(
    r"coursework|relevant courses|thesis|dissertation|honors?|awards?|"
    r"concentration|minor|capstone|dean.?s list|activities",
    re.IGNORECASE,
)


def _normalize_edu_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower().strip(" ,;-–—|()")


def _education_extra_lines(
    block_lines: list[str],
    *,
    school: str | None,
    degree: str | None,
    gpa: str | None,
    location: str | None,
    dates: str | None,
) -> list[str]:
    """Keep only lines that add info beyond structured school/degree/gpa/dates."""
    structured_bits = [
        _normalize_edu_text(p)
        for p in [school, degree, gpa, location, dates]
        if p
    ]
    structured_blob = " ".join(structured_bits)

    extras: list[str] = []
    for line in block_lines:
        stripped = line.strip()
        if not stripped:
            continue
        norm = _normalize_edu_text(stripped)
        if not norm:
            continue
        if _EDU_EXTRA_HINT_RE.search(stripped):
            extras.append(stripped)
            continue
        # Drop if this line is essentially covered by structured fields.
        # Require most tokens from the line to appear in the structured blob.
        tokens = [t for t in re.findall(r"[a-z0-9.]+", norm) if len(t) > 1]
        if not tokens:
            continue
        covered = sum(1 for t in tokens if t in structured_blob)
        if covered / len(tokens) >= 0.7:
            continue
        # Uncovered leftover that isn't a pure date/gpa fragment → keep.
        if dates and _normalize_edu_text(dates) == norm:
            continue
        if gpa and gpa.lower() in norm and len(tokens) <= 3:
            continue
        extras.append(stripped)
    return extras


def _parse_education(lines: list[str]) -> list[EducationEntry]:
    if not lines:
        return []
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        starts_new = bool(
            current
            and (
                _SCHOOL_HINT_RE.search(stripped)
                or (
                    _DEGREE_RE.search(stripped)
                    and _SCHOOL_HINT_RE.search(" ".join(current))
                )
            )
        )
        if starts_new and (
            _DATE_RANGE_RE.search(" ".join(current)) or len(current) >= 2
        ):
            blocks.append(current)
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        blocks.append(current)
    return [_parse_one_education_block(block) for block in blocks]


def _parse_certifications(lines: list[str]) -> list[CertificationEntry]:
    certs: list[CertificationEntry] = []
    for line in lines:
        stripped = _BULLET_RE.sub("", line).strip()
        if not stripped:
            continue
        dates, remainder = _extract_dates(stripped)
        url = None
        if link := _LINK_RE.search(remainder):
            url = link.group(0).rstrip(".,;)")
            remainder = (remainder[: link.start()] + remainder[link.end() :]).strip()
        issuer = None
        name = remainder.strip(" ,;-–—|")
        for sep in (" — ", " – ", " - ", " | "):
            if sep in name:
                left, right = name.split(sep, 1)
                if left.strip() and right.strip() and len(right.split()) <= 6:
                    name, issuer = left.strip(), right.strip()
                break
        if name:
            certs.append(
                CertificationEntry(name=name, issuer=issuer, date=dates, url=url)
            )
    return certs


def _parse_line_items(lines: list[str]) -> list[str]:
    """One text item per bullet/line; join wraps that aren't new bullets."""
    items: list[str] = []
    for line in lines:
        stripped = _BULLET_RE.sub("", line).strip()
        if not stripped:
            continue
        if items and not _BULLET_RE.match(line) and not _ends_sentence(items[-1]):
            # Continuation after comma wrap, etc.
            if not _looks_like_entry_header(stripped) or not stripped[0].isupper():
                items[-1] = (items[-1] + " " + stripped).strip()
                continue
            if not _ends_sentence(items[-1]) and len(stripped.split()) < 8:
                items[-1] = (items[-1] + " " + stripped).strip()
                continue
        items.append(stripped)
    return items


def _parse_awards(lines: list[str]) -> list[AwardEntry]:
    return [AwardEntry(text=t) for t in _parse_line_items(lines)]


def _parse_publications(lines: list[str]) -> list[PublicationEntry]:
    return [PublicationEntry(text=t) for t in _parse_line_items(lines)]


def _parse_languages(lines: list[str]) -> list[LanguageEntry]:
    languages: list[LanguageEntry] = []
    for line in lines:
        stripped = _BULLET_RE.sub("", line).strip()
        if not stripped:
            continue
        chunks = re.split(r"[,;|]", stripped)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            proficiency = None
            language = chunk
            paren = re.match(r"^(.+?)\s*[\(\—\-–:]\s*(.+?)\)?$", chunk)
            if paren:
                language = paren.group(1).strip()
                proficiency = paren.group(2).strip(" )")
            else:
                parts = re.split(r"\s+[—–-:]\s+", chunk, maxsplit=1)
                if len(parts) == 2 and len(parts[1].split()) <= 3:
                    language, proficiency = parts[0].strip(), parts[1].strip()
            if language:
                languages.append(
                    LanguageEntry(language=language, proficiency=proficiency)
                )
    return languages


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_resume_text(raw_text: str) -> ParsedResume:
    lines = raw_text.splitlines()
    header_block, blocks = _split_sections(lines)
    bullet_ids = count(1)

    contact = _parse_contact(header_block)
    headline = _headline_from_header(header_block, contact)
    resume = ParsedResume(raw_text=raw_text, contact=contact, headline=headline)

    for name, heading_raw, section_lines in blocks:
        if name == "summary":
            resume.summary = " ".join(
                _BULLET_RE.sub("", line).strip() for line in section_lines
            ).strip() or None
        elif name == "experience":
            resume.experience.extend(_parse_experience(section_lines, bullet_ids))
        elif name == "education":
            resume.education.extend(_parse_education(section_lines))
        elif name == "skills":
            groups, flat = _parse_skills(section_lines)
            resume.skill_groups.extend(groups)
            resume.skills.extend(flat)
        elif name == "projects":
            resume.projects.extend(_parse_projects(section_lines, bullet_ids))
        elif name == "certifications":
            resume.certifications.extend(_parse_certifications(section_lines))
        elif name == "awards":
            resume.awards.extend(_parse_awards(section_lines))
        elif name == "publications":
            resume.publications.extend(_parse_publications(section_lines))
        elif name == "languages":
            resume.languages.extend(_parse_languages(section_lines))
        else:
            normalized = _normalize_heading(heading_raw)
            if normalized in _SECTION_VARIANTS.get("certifications", set()):
                resume.certifications.extend(_parse_certifications(section_lines))
            elif normalized in _SECTION_VARIANTS.get("awards", set()):
                resume.awards.extend(_parse_awards(section_lines))
            elif normalized in _SECTION_VARIANTS.get("publications", set()):
                resume.publications.extend(_parse_publications(section_lines))
            elif normalized in _SECTION_VARIANTS.get("languages", set()):
                resume.languages.extend(_parse_languages(section_lines))
            else:
                resume.other_sections.append(
                    SectionBlock(name=name, heading_raw=heading_raw, lines=section_lines)
                )

    if not resume.summary:
        resume.summary = _summary_from_header(header_block, contact, headline)

    resume.skills = list(dict.fromkeys(resume.skills))
    return resume
