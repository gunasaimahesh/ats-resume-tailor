"""Deterministic groundedness verifier (pipeline steps 5-6). No LLM.

Step 5 — per rewritten bullet / summary:
  * metric preservation: every number from the source must survive in the rewrite;
  * digit rule: every number in the rewritten text must appear somewhere in
    the original resume text;
  * entity rule: every ORG/PRODUCT/GPE/PERSON entity and proper noun in the
    rewritten text must be grounded in the original — by substring, by
    synonym group (so "Kubernetes" is fine when the original says "K8s"),
    or by rapidfuzz fuzzy match.
  Any failure reverts the bullet to its original wording and flags it.
  Summary failures fall back to the original or a deterministic summary.

Step 6 — keyword preservation: any JD keyword that had evidence in the
original resume but vanished from the tailored output is added to Skills
when a whitelist synonym exists (skills ∪ skill_groups).
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from backend.nlp.jd_keywords import alias_pattern, get_nlp
from backend.nlp.scoring import (
    match_keyword,
    segments_from_resume,
    segments_from_tailored,
)
from backend.nlp.skills_dict import SKILL_SYNONYMS
from backend.nlp.tailor_plan import TailorPlan, fallback_summary, skills_whitelist
from backend.schema import JDKeyword, ParsedResume, TailoredResume

# Digits not preceded by a letter — so "12" and "40%" count, but the "8" in
# "K8s" does not (otherwise K8s→Kubernetes falsely fails metric preservation).
_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*")
_FUZZY_THRESHOLD = 87

# spaCy NER labels we treat as fact-bearing entities.
_ENTITY_LABELS = {"ORG", "PRODUCT", "GPE", "PERSON", "NORP", "FAC"}


def _numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "") for m in _NUMBER_RE.finditer(text)}


def _entities(text: str) -> list[str]:
    """NER entities plus standalone proper nouns from the rewritten text."""
    doc = get_nlp()(text)
    terms: list[str] = []
    covered: set[int] = set()
    for ent in doc.ents:
        if ent.label_ in _ENTITY_LABELS:
            terms.append(ent.text)
            covered.update(range(ent.start, ent.end))
    for token in doc:
        if token.pos_ == "PROPN" and token.i not in covered and len(token.text) >= 3:
            terms.append(token.text)
    seen: set[str] = set()
    unique = []
    for term in terms:
        if term.lower() not in seen:
            seen.add(term.lower())
            unique.append(term)
    return unique


def _grounded(term: str, original_text: str, original_tokens: set[str]) -> bool:
    lowered = term.lower()
    if lowered in original_text.lower():
        return True

    # Synonym group: the LLM is allowed to canonicalize ("K8s" -> "Kubernetes"),
    # so the term passes if any alias of its group appears in the original.
    for canonical, aliases in SKILL_SYNONYMS.items():
        group = [canonical, *aliases]
        if any(alias.lower() == lowered for alias in group):
            if any(alias_pattern(alias).search(original_text) for alias in group):
                return True
            break

    # Fuzzy: survive inflections/typos, not whole new words.
    if " " in lowered:
        if fuzz.partial_ratio(lowered, original_text.lower()) >= _FUZZY_THRESHOLD:
            return True
        # NER sometimes over-groups ("Led Kubernetes" as one entity): the
        # whole span passes if every constituent word is grounded on its own.
        parts = [p for p in re.findall(r"[a-z0-9+#./-]+", lowered) if len(p) >= 3]
        return bool(parts) and all(
            _grounded(part, original_text, original_tokens) for part in parts
        )
    return any(fuzz.ratio(lowered, tok) >= _FUZZY_THRESHOLD for tok in original_tokens)


def _groundedness_problems(
    text: str, original_text: str, original_numbers: set[str], original_tokens: set[str]
) -> list[str]:
    problems: list[str] = []
    for number in _numbers(text):
        if number not in original_numbers:
            problems.append(
                f"digit rule: '{number}' does not appear in the original resume"
            )
    for term in _entities(text):
        if not _grounded(term, original_text, original_tokens):
            problems.append(
                f"entity rule: '{term}' is not grounded in the original resume"
            )
    return problems


def verify_bullets(tailored: TailoredResume, original_text: str) -> TailoredResume:
    """Step 5: revert + flag any rewritten bullet that fails a groundedness rule."""
    original_numbers = _numbers(original_text)
    original_tokens = set(re.findall(r"[a-z0-9+#./-]+", original_text.lower()))

    all_bullets = [
        b for entry in tailored.experience for b in entry.bullets
    ] + [b for project in tailored.projects for b in project.bullets]

    for bullet in all_bullets:
        if not bullet.changed:
            continue
        problems: list[str] = []

        # Metric preservation: source digits must survive the rewrite.
        source_nums = _numbers(bullet.original)
        rewrite_nums = _numbers(bullet.text)
        lost = source_nums - rewrite_nums
        if lost:
            problems.append(
                "metric preservation: missing number(s) "
                + ", ".join(sorted(lost))
                + " from source bullet"
            )

        problems.extend(
            _groundedness_problems(
                bullet.text, original_text, original_numbers, original_tokens
            )
        )
        if problems:
            bullet.text = bullet.original
            bullet.changed = False
            bullet.reverted = True
            bullet.flags = problems
    return tailored


def verify_summary(
    tailored: TailoredResume,
    original: ParsedResume,
    plan: TailorPlan,
) -> list[str]:
    """Verify the summary; on failure fall back to original or deterministic text.

    Returns flag strings describing what happened (empty if summary kept).
    """
    flags: list[str] = []
    summary = (tailored.summary or "").strip()
    if not summary:
        tailored.summary = fallback_summary(original, plan)
        return ["summary empty — used deterministic fallback"]

    original_text = original.raw_text
    original_numbers = _numbers(original_text)
    original_tokens = set(re.findall(r"[a-z0-9+#./-]+", original_text.lower()))
    problems = _groundedness_problems(
        summary, original_text, original_numbers, original_tokens
    )
    if problems:
        if original.summary and original.summary.strip():
            tailored.summary = original.summary.strip()
            flags.append("summary reverted to original: " + "; ".join(problems))
        else:
            tailored.summary = fallback_summary(original, plan)
            flags.append("summary replaced with fallback: " + "; ".join(problems))
    return flags


def preserve_keywords(
    tailored: TailoredResume,
    original: ParsedResume,
    jd_keywords: list[JDKeyword],
) -> list[str]:
    """Step 6: re-add vanished, evidence-backed JD keywords to Skills.

    Returns the list of skills that were added (whitelist strings)."""
    original_segments = segments_from_resume(original)
    tailored_segments = segments_from_tailored(tailored)
    whitelist = {skill.lower(): skill for skill in skills_whitelist(original)}

    added: list[str] = []
    for keyword in jd_keywords:
        if match_keyword(keyword, original_segments).status != "matched":
            continue  # no evidence in the original: nothing to preserve
        if match_keyword(keyword, tailored_segments).status == "matched":
            continue  # still present in the output
        if keyword.in_dictionary and keyword.keyword in SKILL_SYNONYMS:
            group = [keyword.keyword, *SKILL_SYNONYMS[keyword.keyword]]
        else:
            group = [keyword.keyword, *keyword.aliases_matched]
        skill = next(
            (whitelist[a.lower()] for a in group if a.lower() in whitelist), None
        )
        if skill is not None and skill not in tailored.skills:
            tailored.skills.append(skill)
            added.append(skill)
            # Keep skill_groups in sync when possible.
            _append_to_skill_groups(tailored, skill)
    return added


def _append_to_skill_groups(tailored: TailoredResume, skill: str) -> None:
    from backend.nlp.skills_dict import category_for_skill
    from backend.schema import SkillGroup

    lower = skill.lower()
    for group in tailored.skill_groups:
        if any(i.lower() == lower for i in group.items):
            return
    category = category_for_skill(skill)
    for group in tailored.skill_groups:
        if group.category == category:
            group.items.append(skill)
            return
    tailored.skill_groups.append(SkillGroup(category=category, items=[skill]))


def repair_matched_keywords(
    tailored: TailoredResume,
    original: ParsedResume,
    jd_keywords: list[JDKeyword],
    before_matched: list[str],
) -> list[str]:
    """Ensure every previously-matched keyword still matches; append Skills if needed.

    Returns repair notes (skill names added).
    """
    if not before_matched:
        return []
    matched_set = set(before_matched)
    keywords = [k for k in jd_keywords if k.keyword in matched_set]
    return preserve_keywords(tailored, original, keywords)
