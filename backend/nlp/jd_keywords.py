"""JD keyword extraction (pipeline step 2).

Dictionary skills are matched against the JD, then classified by section:

- required — Minimum / Required qualifications
- nice_to_have — Preferred / Nice to have
- mentioned — About-the-job, Responsibilities, marketing, default before any heading

YAKE extras are taken only from qualification sections (never from About).
"""

from __future__ import annotations

import re
from bisect import bisect_right
from functools import lru_cache
from typing import Literal

from backend.nlp.skills_dict import (
    CASE_SENSITIVE_ALIASES,
    SKILL_SYNONYMS,
    category_for_skill,
)
from backend.schema import JDKeyword

SectionMode = Literal["required", "nice_to_have", "mentioned"]

_nlp = None


def get_nlp():
    """Lazily-loaded shared spaCy pipeline (en_core_web_sm)."""
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ---------------------------------------------------------------------------
# Required vs nice-to-have vs mentioned classification
# ---------------------------------------------------------------------------

_NICE_CUE_RE = re.compile(
    r"nice[ -]to[ -]have|bonus|a plus|plus if|preferred|preferably|"
    r"familiarity with|exposure to|good to have|desirable|would be great|"
    r"not required|optional",
    re.IGNORECASE,
)
_REQUIRED_CUE_RE = re.compile(
    r"must[ -]have|\brequired\b|\bessential\b|\bneed\b|proficien|expert",
    re.IGNORECASE,
)
_REQUIRED_SECTION_RE = re.compile(
    r"minimum qualifications?|basic qualifications?|required qualifications?|"
    r"requirements?|must[ -]haves?|what you.?ll need|"
    r"what we.?re looking for|about you|qualifications?",
    re.IGNORECASE,
)
_NICE_SECTION_RE = re.compile(
    r"preferred qualifications?|nice[ -]to[ -]have|bonus qualifications?|"
    r"good to have|optional qualifications?",
    re.IGNORECASE,
)
_MENTIONED_SECTION_RE = re.compile(
    r"about the (job|role|team|company|position)|about us|"
    r"responsibilities|what you.?ll do|what you will do|"
    r"benefits|compensation|equal opportunity|perks|"
    r"life at|our mission|who we are",
    re.IGNORECASE,
)

_IMPORTANCE_RANK = {"required": 0, "nice_to_have": 1, "mentioned": 2}


def _is_heading_like(stripped: str) -> bool:
    return 0 < len(stripped) <= 60 and (
        stripped.endswith(":") or len(stripped.split()) <= 6
    )


def _classify_lines(lines: list[str]) -> list[SectionMode]:
    """Return a section mode per line. Default before any heading: mentioned."""
    modes: list[SectionMode] = []
    section_mode: SectionMode = "mentioned"

    for line in lines:
        stripped = line.strip()
        if _is_heading_like(stripped):
            if _NICE_SECTION_RE.search(stripped) or (
                _NICE_CUE_RE.search(stripped)
                and not _REQUIRED_SECTION_RE.search(stripped)
            ):
                section_mode = "nice_to_have"
            elif _MENTIONED_SECTION_RE.search(stripped):
                section_mode = "mentioned"
            elif _REQUIRED_SECTION_RE.search(stripped):
                # "Qualifications" alone → required; Preferred already caught above.
                section_mode = "required"

        # Inline cues only promote/demote inside qualification sections.
        if section_mode in ("required", "nice_to_have"):
            if _NICE_CUE_RE.search(stripped):
                modes.append("nice_to_have")
            elif _REQUIRED_CUE_RE.search(stripped):
                modes.append("required")
            else:
                modes.append(section_mode)
        else:
            modes.append("mentioned")
    return modes


def _line_starts(text: str) -> list[int]:
    starts, pos = [], 0
    for line in text.splitlines(keepends=True):
        starts.append(pos)
        pos += len(line)
    return starts or [0]


# ---------------------------------------------------------------------------
# Dictionary matching
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1024)
def alias_pattern(alias: str) -> re.Pattern:
    """Word-boundary-safe pattern for a skill alias (shared with scoring)."""
    flags = 0 if alias in CASE_SENSITIVE_ALIASES else re.IGNORECASE
    return re.compile(
        rf"(?<![A-Za-z0-9_+#]){re.escape(alias)}(?![A-Za-z0-9_+#])", flags
    )


_ALIAS_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    canonical: [(alias, alias_pattern(alias)) for alias in aliases]
    for canonical, aliases in SKILL_SYNONYMS.items()
}


# ---------------------------------------------------------------------------
# YAKE extras
# ---------------------------------------------------------------------------

_GENERIC_WORDS = {
    "experience", "experienced", "years", "year", "team", "teams", "work",
    "working", "ability", "strong", "knowledge", "understanding", "degree",
    "bachelor", "bachelors", "master", "masters", "plus", "bonus", "excellent",
    "communication", "skills", "skill", "engineer", "engineers", "developer",
    "developers", "engineering", "job", "role", "company", "candidate",
    "ideal", "looking", "hands", "production", "building", "build", "written",
    "develop", "developing", "development", "solutions", "tools", "modern",
    "technologies", "stack", "environment", "background", "familiarity",
    "exposure", "proficiency", "proficient", "senior", "junior", "including",
    "related", "field", "equivalent", "successful", "day", "best", "practices",
    "platform", "platforms", "backend", "frontend", "running", "using",
    "minimum", "maximum", "qualifications", "qualification", "requirements",
    "requirement", "preferred", "responsibilities", "responsibility", "about",
    "equal", "opportunity", "benefits", "salary", "location", "remote",
    "hybrid", "full", "time", "part", "basic", "additional", "other",
    "description", "overview", "summary", "position", "apply", "joining",
}

_HEADING_PHRASES = {
    "minimum qualifications",
    "preferred qualifications",
    "basic qualifications",
    "required qualifications",
    "additional qualifications",
    "job description",
    "about the role",
    "about you",
    "what you will do",
    "what you'll do",
    "equal opportunity",
}

_MAX_YAKE_EXTRAS = 8


def is_claimable_keyword(keyword: JDKeyword) -> bool:
    """True if safe to offer as a Review-step skill checkbox.

    Dictionary skills only; never YAKE extras, headings, or 'mentioned' tier.
    """
    if not keyword.in_dictionary:
        return False
    if keyword.importance == "mentioned":
        return False
    lowered = keyword.keyword.lower().strip()
    if lowered in _HEADING_PHRASES:
        return False
    tokens = lowered.split()
    if tokens and all(t in _GENERIC_WORDS for t in tokens):
        return False
    return True


def _better_importance(a: SectionMode, b: SectionMode) -> SectionMode:
    return a if _IMPORTANCE_RANK[a] <= _IMPORTANCE_RANK[b] else b


def _yake_extras(
    jd_text: str,
    taken_positions: set[str],
    mode_at,
) -> list[tuple[str, int, SectionMode]]:
    """Non-dictionary keyphrases from qualification sections only."""
    import yake

    doc = get_nlp()(jd_text)
    noun_chunks = {chunk.text.lower().strip() for chunk in doc.noun_chunks}

    extractor = yake.KeywordExtractor(lan="en", n=3, top=30)
    extras: list[tuple[str, int, SectionMode]] = []
    kept: set[str] = set()
    for phrase, _score in extractor.extract_keywords(jd_text):
        lowered = phrase.lower().strip()
        tokens = lowered.split()
        if len(tokens) < 2 or any(t in _GENERIC_WORDS for t in tokens):
            continue
        if lowered in _HEADING_PHRASES:
            continue
        if any(
            pattern.search(phrase)
            for pats in _ALIAS_PATTERNS.values()
            for _alias, pattern in pats
        ):
            continue
        if not any(lowered in nc or nc in lowered for nc in noun_chunks):
            continue
        if lowered in taken_positions:
            continue
        if any(lowered in k or k in lowered for k in kept):
            continue
        match = re.search(re.escape(phrase), jd_text, re.IGNORECASE)
        if not match:
            continue
        mode = mode_at(match.start())
        if mode == "mentioned":
            continue  # quals-only YAKE
        kept.add(lowered)
        extras.append((phrase, match.start(), mode))
        if len(extras) >= _MAX_YAKE_EXTRAS:
            break
    return extras


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def extract_keywords(jd_text: str) -> list[JDKeyword]:
    lines = jd_text.splitlines()
    line_modes = _classify_lines(lines)
    starts = _line_starts(jd_text)

    def mode_at(offset: int) -> SectionMode:
        idx = bisect_right(starts, offset) - 1
        return line_modes[idx] if 0 <= idx < len(line_modes) else "mentioned"

    found: list[tuple[JDKeyword, int]] = []

    for canonical, patterns in _ALIAS_PATTERNS.items():
        aliases_matched: list[str] = []
        importance: SectionMode | None = None
        first_pos: int | None = None
        for alias, pattern in patterns:
            for match in pattern.finditer(jd_text):
                if alias not in aliases_matched:
                    aliases_matched.append(alias)
                mode = mode_at(match.start())
                if importance is None:
                    importance = mode
                else:
                    importance = _better_importance(importance, mode)
                if first_pos is None or match.start() < first_pos:
                    first_pos = match.start()
        if aliases_matched:
            found.append(
                (
                    JDKeyword(
                        keyword=canonical,
                        importance=importance or "mentioned",
                        aliases_matched=aliases_matched,
                        in_dictionary=True,
                        category=category_for_skill(canonical),
                    ),
                    first_pos or 0,
                )
            )

    taken = {kw.keyword.lower() for kw, _ in found}
    for phrase, pos, mode in _yake_extras(jd_text, taken, mode_at):
        found.append(
            (
                JDKeyword(
                    keyword=phrase,
                    importance=mode,
                    aliases_matched=[phrase],
                    in_dictionary=False,
                ),
                pos,
            )
        )

    found.sort(
        key=lambda item: (_IMPORTANCE_RANK.get(item[0].importance, 9), item[1])
    )
    return [kw for kw, _ in found]
