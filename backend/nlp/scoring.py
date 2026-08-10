"""ATS scoring (pipeline steps 3 and 9).

Coverage of JD keywords in the resume, checked in three tiers per keyword:
1. exact — the canonical name appears (word-boundary safe),
2. synonym — another alias from its synonym group appears (K8s for Kubernetes),
3. fuzzy — rapidfuzz similarity above a threshold, to survive typos and
   inflections. Guarded so short aliases can't false-positive ("Java" must
   never match "JavaScript").

The overall score weights required keywords double. The band reflects
required-keyword coverage against SPEC's 70-80% target: >= 80 green,
70-80 yellow, below 70 red.
"""

import re

from rapidfuzz import fuzz

from backend.nlp.jd_keywords import alias_pattern
from backend.nlp.skills_dict import SKILL_SYNONYMS
from backend.schema import (
    JDKeyword,
    KeywordMatch,
    ParsedResume,
    ScoreReport,
    TailoredResume,
)

REQUIRED_WEIGHT = 2.0
NICE_TO_HAVE_WEIGHT = 1.0
MENTIONED_WEIGHT = 0.25  # default; portal profile may override

_FUZZY_THRESHOLD = 87
_MIN_FUZZY_ALIAS_LEN = 5


def weight_for_importance(
    importance: str, mentioned_weight: float = MENTIONED_WEIGHT
) -> float:
    if importance == "required":
        return REQUIRED_WEIGHT
    if importance == "nice_to_have":
        return NICE_TO_HAVE_WEIGHT
    return mentioned_weight


def band_for(required_coverage: float) -> str:
    if required_coverage >= 80:
        return "green"
    if required_coverage >= 70:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------------
# Resume segments: (location label, text) pairs to search in
# ---------------------------------------------------------------------------


def _education_text(entry) -> str:
    return " ".join(
        part
        for part in [
            entry.school,
            entry.degree,
            entry.gpa,
            entry.location,
            entry.dates,
            *entry.raw_lines,
        ]
        if part
    )


def _structured_fact_segments(obj, *, include_skill_groups: bool = False) -> list[tuple[str, str]]:
    """Shared fact segments for ParsedResume / TailoredResume.

    Tailored resumes use the LLM-ordered `skills` list as the source of truth;
    original `skill_groups` must not be scored there or vanished keywords look
    present.
    """
    segments: list[tuple[str, str]] = []
    for entry in obj.experience:
        segments.append((f"experience header ({entry.company or '?'})", entry.header_raw))
        for bullet in entry.bullets:
            text = getattr(bullet, "text", None) or ""
            segments.append((f"experience {bullet.id}", text))
    for project in obj.projects:
        segments.append((f"project ({project.name})", project.name))
        if getattr(project, "tech", None):
            segments.append((f"project tech ({project.name})", project.tech))
        for bullet in project.bullets:
            segments.append((f"project {bullet.id}", bullet.text))
    for skill in obj.skills:
        segments.append(("skills", skill))
    if include_skill_groups:
        for group in getattr(obj, "skill_groups", []) or []:
            for item in group.items:
                segments.append(("skills", item))
    if getattr(obj, "headline", None):
        segments.append(("headline", obj.headline))
    if obj.summary:
        segments.append(("summary", obj.summary))
    for edu in obj.education:
        segments.append(("education", _education_text(edu)))
    for cert in getattr(obj, "certifications", []) or []:
        segments.append(("certifications", " ".join(p for p in [cert.name, cert.issuer, cert.date] if p)))
    for award in getattr(obj, "awards", []) or []:
        text = getattr(award, "text", None) or getattr(award, "title", None) or ""
        if text:
            segments.append(("awards", text))
    for pub in getattr(obj, "publications", []) or []:
        if pub.text:
            segments.append(("publications", pub.text))
    for lang in getattr(obj, "languages", []) or []:
        segments.append(
            ("languages", " ".join(p for p in [lang.language, lang.proficiency] if p))
        )
    for section in obj.other_sections:
        for line in section.lines:
            segments.append((section.heading_raw.lower(), line))
    return segments


def segments_from_tailored(tailored: TailoredResume) -> list[tuple[str, str]]:
    """Same as segments_from_resume, for post-tailoring content (steps 6/9)."""
    return _structured_fact_segments(tailored, include_skill_groups=False)


def segments_from_resume(resume: ParsedResume) -> list[tuple[str, str]]:
    # Flat skills already covers groups from parse; groups are a fallback only.
    return _structured_fact_segments(resume, include_skill_groups=not resume.skills)


# ---------------------------------------------------------------------------
# Per-keyword matching
# ---------------------------------------------------------------------------


def _keyword_aliases(keyword: JDKeyword) -> list[str]:
    """The full synonym group for a keyword, canonical name first."""
    if keyword.in_dictionary and keyword.keyword in SKILL_SYNONYMS:
        candidates = [keyword.keyword, *SKILL_SYNONYMS[keyword.keyword]]
    else:
        candidates = [keyword.keyword, *keyword.aliases_matched]
    seen: set[str] = set()
    aliases: list[str] = []
    for alias in candidates:
        if alias.lower() not in seen:
            seen.add(alias.lower())
            aliases.append(alias)
    return aliases


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9+#./-]+", text)


def match_keyword(
    keyword: JDKeyword, segments: list[tuple[str, str]]
) -> KeywordMatch:
    aliases = _keyword_aliases(keyword)

    # Tier 1 + 2: exact / synonym-group match.
    for alias in aliases:
        pattern = alias_pattern(alias)
        for location, text in segments:
            found = pattern.search(text)
            if found:
                match_type = (
                    "exact" if alias.lower() == keyword.keyword.lower() else "synonym"
                )
                return KeywordMatch(
                    keyword=keyword.keyword,
                    importance=keyword.importance,
                    status="matched",
                    match_type=match_type,
                    matched_text=found.group(0),
                    location=location,
                )

    # Tier 3: fuzzy match, single tokens only, guarded by length + threshold
    # so e.g. "Java" (short) can never fuzzy-claim "JavaScript".
    best_score = 0.0
    best: tuple[str, str] | None = None  # (matched_text, location)
    for alias in aliases:
        lowered = alias.lower()
        if len(lowered) < _MIN_FUZZY_ALIAS_LEN:
            continue
        for location, text in segments:
            if " " in lowered:
                score = fuzz.partial_ratio(lowered, text.lower())
                if score > best_score:
                    best_score, best = score, (text, location)
            else:
                for token in _tokens(text):
                    score = fuzz.ratio(lowered, token.lower())
                    if score > best_score:
                        best_score, best = score, (token, location)

    if best is not None and best_score >= _FUZZY_THRESHOLD:
        return KeywordMatch(
            keyword=keyword.keyword,
            importance=keyword.importance,
            status="matched",
            match_type="fuzzy",
            matched_text=best[0],
            location=best[1],
        )

    return KeywordMatch(
        keyword=keyword.keyword, importance=keyword.importance, status="missing"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def score_resume(
    resume: ParsedResume,
    keywords: list[JDKeyword],
    *,
    mentioned_weight: float = MENTIONED_WEIGHT,
) -> ScoreReport:
    return score_segments(
        segments_from_resume(resume),
        keywords,
        mentioned_weight=mentioned_weight,
    )


def score_segments(
    segments: list[tuple[str, str]],
    keywords: list[JDKeyword],
    *,
    mentioned_weight: float = MENTIONED_WEIGHT,
) -> ScoreReport:
    matches: list[KeywordMatch] = []
    matched_weight = total_weight = 0.0
    required_total = required_matched = 0

    for keyword in keywords:
        weight = weight_for_importance(keyword.importance, mentioned_weight)
        total_weight += weight
        if keyword.importance == "required":
            required_total += 1

        result = match_keyword(keyword, segments)
        matches.append(result)
        if result.status == "matched":
            matched_weight += weight
            if keyword.importance == "required":
                required_matched += 1

    score = 100.0 if total_weight == 0 else matched_weight / total_weight * 100
    # Band is driven only by required quals — mentioned boilerplate cannot tank it.
    required_coverage = (
        100.0 if required_total == 0 else required_matched / required_total * 100
    )

    return ScoreReport(
        score=round(score, 1),
        required_coverage=round(required_coverage, 1),
        band=band_for(required_coverage),
        matches=matches,
    )
