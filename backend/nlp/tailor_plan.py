"""Deterministic rewrite plan (Python decides; Gemini executes).

Builds per-bullet keyword evidence, canonical synonym swaps, relevance scores,
deterministic skills ordering, within-job bullet order, summary must-include
keywords, and unevidenced required-keyword gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.nlp.scoring import (
    MENTIONED_WEIGHT,
    match_keyword,
    segments_from_resume,
    weight_for_importance,
)
from backend.nlp.skills_dict import (
    CATEGORY_ORDER,
    SKILL_SYNONYMS,
    category_for_skill,
)
from backend.schema import JDKeyword, ParsedResume


@dataclass
class BulletPlan:
    bullet_id: str
    source_text: str
    context_label: str  # e.g. "Senior Engineer @ Acme" or "Project: Foo"
    evidenced_keywords: list[str] = field(default_factory=list)
    canonical_swaps: list[tuple[str, str]] = field(default_factory=list)  # (from, to)
    lead_with: str | None = None
    relevance_score: float = 0.0


@dataclass
class TailorPlan:
    bullet_plans: dict[str, BulletPlan]
    # Ordered bullet IDs within each experience/project entry (by entry index).
    experience_bullet_order: list[list[str]]
    project_bullet_order: list[list[str]]
    skills_order: list[str]
    skill_groups: list[tuple[str | None, list[str]]]  # (category, ordered items)
    summary_must_include: list[str]
    keyword_gaps: list[str]  # required keywords with no evidence anywhere
    required_keywords: list[str]
    nice_keywords: list[str]


def skills_whitelist(resume: ParsedResume) -> list[str]:
    """Flat original skills; fall back to skill_groups when skills is empty."""
    if resume.skills:
        return list(resume.skills)
    flat: list[str] = []
    for group in resume.skill_groups:
        flat.extend(group.items)
    return list(dict.fromkeys(flat))


def _keyword_aliases(keyword: JDKeyword) -> list[str]:
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


def _surface_in_text(text: str, aliases: list[str]) -> str | None:
    """Return the alias surface form found in text, if any (case-preserved from text via match)."""
    from backend.nlp.jd_keywords import alias_pattern

    for alias in aliases:
        found = alias_pattern(alias).search(text)
        if found:
            return found.group(0)
    return None


def _canonical_swap(
    keyword: JDKeyword, text: str
) -> tuple[str, str] | None:
    """If text uses a non-canonical alias and JD wants the canonical, propose a swap."""
    aliases = _keyword_aliases(keyword)
    if len(aliases) < 2:
        return None
    canonical = aliases[0]
    surface = _surface_in_text(text, aliases)
    if surface is None:
        return None
    if surface.lower() == canonical.lower():
        return None
    # Only swap when the JD keyword itself is the canonical (or close).
    if keyword.keyword.lower() != canonical.lower():
        # Prefer the JD's preferred surface if it differs from what's in the bullet.
        preferred = keyword.keyword
        if surface.lower() != preferred.lower():
            return (surface, preferred)
        return None
    return (surface, canonical)


def _weight(keyword: JDKeyword) -> float:
    return weight_for_importance(keyword.importance, MENTIONED_WEIGHT)


def _order_skills(whitelist: list[str], jd_keywords: list[JDKeyword]) -> list[str]:
    """JD-matched skills first (required then nice), then remaining original order."""
    segments = [("skills", s) for s in whitelist]
    required_hit: list[str] = []
    nice_hit: list[str] = []
    matched_lower: set[str] = set()

    for keyword in jd_keywords:
        result = match_keyword(keyword, segments)
        if result.status != "matched":
            continue
        aliases = {a.lower() for a in _keyword_aliases(keyword)}
        for skill in whitelist:
            if skill.lower() in aliases and skill.lower() not in matched_lower:
                matched_lower.add(skill.lower())
                if keyword.importance == "required":
                    required_hit.append(skill)
                else:
                    nice_hit.append(skill)

    rest = [s for s in whitelist if s.lower() not in matched_lower]
    return list(dict.fromkeys(required_hit + nice_hit + rest))


def build_standard_skill_groups(
    whitelist: list[str], skills_order: list[str]
) -> list[tuple[str | None, list[str]]]:
    """Rebuild skill groups using standard categories (not original resume style).

    Within each category, JD-matched skills come first via skills_order ranking.
    Unrecognized skills land in 'Other'. Empty categories are omitted.
    """
    buckets: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}
    seen: set[str] = set()
    for skill in skills_order:
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        buckets[category_for_skill(skill)].append(skill)
    # Any whitelist skill not already in skills_order (shouldn't happen, but safe).
    for skill in whitelist:
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        buckets[category_for_skill(skill)].append(skill)

    groups: list[tuple[str | None, list[str]]] = []
    for category in CATEGORY_ORDER:
        items = buckets.get(category) or []
        if items:
            groups.append((category, items))
    return groups


def build_tailor_plan(
    resume: ParsedResume, jd_keywords: list[JDKeyword]
) -> TailorPlan:
    whitelist = skills_whitelist(resume)
    resume_segments = segments_from_resume(resume)

    # Global evidence / gaps
    keyword_gaps: list[str] = []
    evidenced_anywhere: set[str] = set()
    for keyword in jd_keywords:
        if match_keyword(keyword, resume_segments).status == "matched":
            evidenced_anywhere.add(keyword.keyword)
        elif keyword.importance == "required":
            keyword_gaps.append(keyword.keyword)

    required_keywords = [
        k.keyword for k in jd_keywords if k.importance == "required"
    ]
    nice_keywords = [
        k.keyword for k in jd_keywords if k.importance == "nice_to_have"
    ]

    skills_order = _order_skills(whitelist, jd_keywords)
    skill_groups = build_standard_skill_groups(whitelist, skills_order)

    bullet_plans: dict[str, BulletPlan] = {}
    experience_bullet_order: list[list[str]] = []
    project_bullet_order: list[list[str]] = []

    def plan_bullets(
        bullets, context_label: str, extra_context: str = ""
    ) -> list[str]:
        scored: list[tuple[float, int, str]] = []
        for index, bullet in enumerate(bullets):
            search_text = f"{extra_context} {bullet.text}".strip()
            segments = [("bullet", search_text)]
            evidenced: list[str] = []
            swaps: list[tuple[str, str]] = []
            relevance = 0.0
            for keyword in jd_keywords:
                if match_keyword(keyword, segments).status == "matched":
                    evidenced.append(keyword.keyword)
                    relevance += _weight(keyword)
                    swap = _canonical_swap(keyword, bullet.text)
                    if swap is not None:
                        swaps.append(swap)
            lead = evidenced[0] if evidenced else None
            bullet_plans[bullet.id] = BulletPlan(
                bullet_id=bullet.id,
                source_text=bullet.text,
                context_label=context_label,
                evidenced_keywords=evidenced,
                canonical_swaps=swaps,
                lead_with=lead,
                relevance_score=relevance,
            )
            scored.append((relevance, index, bullet.id))
        # Higher relevance first; stable for ties (lower original index wins).
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [bid for _, _, bid in scored]

    for entry in resume.experience:
        context = " @ ".join(p for p in [entry.title, entry.company] if p)
        label = context or entry.header_raw
        extra = " ".join(
            p for p in [entry.title, entry.company, entry.header_raw] if p
        )
        experience_bullet_order.append(
            plan_bullets(entry.bullets, label, extra)
        )

    for project in resume.projects:
        label = f"Project: {project.name}"
        extra = " ".join(p for p in [project.name, project.tech or ""] if p)
        project_bullet_order.append(plan_bullets(project.bullets, label, extra))

    # Summary must-include: evidenced required keywords, prefer skills then top bullets.
    must: list[str] = []
    for keyword in jd_keywords:
        if keyword.importance != "required":
            continue
        if keyword.keyword not in evidenced_anywhere:
            continue
        must.append(keyword.keyword)
        if len(must) >= 8:
            break
    # Prefer skills-side keywords first for natural summary weaving.
    skill_lower = {s.lower() for s in skills_order}
    must.sort(
        key=lambda k: (
            0
            if any(
                a.lower() in skill_lower
                for a in _keyword_aliases(
                    next(x for x in jd_keywords if x.keyword == k)
                )
            )
            else 1
        )
    )
    summary_must_include = must[:8]

    return TailorPlan(
        bullet_plans=bullet_plans,
        experience_bullet_order=experience_bullet_order,
        project_bullet_order=project_bullet_order,
        skills_order=skills_order,
        skill_groups=skill_groups,
        summary_must_include=summary_must_include,
        keyword_gaps=keyword_gaps,
        required_keywords=required_keywords,
        nice_keywords=nice_keywords,
    )


def fallback_summary(resume: ParsedResume, plan: TailorPlan) -> str:
    """Deterministic summary when LLM summary fails verification."""
    if resume.summary and resume.summary.strip():
        return resume.summary.strip()
    titles = [e.title for e in resume.experience if e.title][:2]
    skills = plan.summary_must_include or plan.skills_order[:5]
    parts: list[str] = []
    if titles:
        parts.append(
            f"Professional with experience as {' and '.join(titles)}."
        )
    else:
        parts.append("Results-oriented professional.")
    if skills:
        parts.append(
            "Strengths include " + ", ".join(skills[:6]) + "."
        )
    return " ".join(parts)
