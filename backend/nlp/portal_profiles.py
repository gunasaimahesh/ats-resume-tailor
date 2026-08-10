"""Portal / ATS family profiles — screening knobs by job portal.

When the user names a portal (Greenhouse, Workday, …), we resolve a
PortalProfile that tunes scoring weights, template safety, and Gemini tone.
Unknown / empty → generic (Workday-safe conservative default).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MatchMode = Literal["exact", "fuzzy", "semantic"]


@dataclass(frozen=True)
class PortalProfile:
    family: str
    display_name: str
    match_mode: MatchMode
    mentioned_weight: float
    force_classic_template: bool
    prefer_literal_jd_surface: bool
    emphasize_bullet_evidence: bool
    hint: str


_PROFILES: dict[str, PortalProfile] = {
    "workday": PortalProfile(
        family="workday",
        display_name="Workday",
        match_mode="exact",
        mentioned_weight=0.2,
        force_classic_template=True,
        prefer_literal_jd_surface=True,
        emphasize_bullet_evidence=False,
        hint="Workday: exact keywords + single-column template.",
    ),
    "taleo": PortalProfile(
        family="taleo",
        display_name="Taleo (Oracle)",
        match_mode="exact",
        mentioned_weight=0.2,
        force_classic_template=True,
        prefer_literal_jd_surface=True,
        emphasize_bullet_evidence=False,
        hint="Taleo: strictest exact keyword match; classic single-column layout.",
    ),
    "successfactors": PortalProfile(
        family="successfactors",
        display_name="SuccessFactors (SAP)",
        match_mode="exact",
        mentioned_weight=0.2,
        force_classic_template=True,
        prefer_literal_jd_surface=True,
        emphasize_bullet_evidence=False,
        hint="SuccessFactors: taxonomy + exact-ish match; classic template.",
    ),
    "icims": PortalProfile(
        family="icims",
        display_name="iCIMS",
        match_mode="fuzzy",
        mentioned_weight=0.25,
        force_classic_template=True,
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="iCIMS: fuzzy/semantic Role Fit; classic layout preferred.",
    ),
    "greenhouse": PortalProfile(
        family="greenhouse",
        display_name="Greenhouse",
        match_mode="semantic",
        mentioned_weight=0.15,
        force_classic_template=False,
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="Greenhouse: recruiter criteria/scorecards; quals-first + evidenced bullets.",
    ),
    "ashby": PortalProfile(
        family="ashby",
        display_name="Ashby",
        match_mode="semantic",
        mentioned_weight=0.15,
        force_classic_template=False,
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="Ashby: criteria Meets/Does-not-meet with resume citations.",
    ),
    "lever": PortalProfile(
        family="lever",
        display_name="Lever",
        match_mode="fuzzy",
        mentioned_weight=0.2,
        force_classic_template=True,  # sidebar skills often dropped
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="Lever: stemming search; avoid sidebar-only skills.",
    ),
    "linkedin": PortalProfile(
        family="linkedin",
        display_name="LinkedIn",
        match_mode="fuzzy",
        mentioned_weight=0.25,
        force_classic_template=True,
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="LinkedIn: often a funnel — optimize like a generic ATS unless you know the employer ATS.",
    ),
    "indeed": PortalProfile(
        family="indeed",
        display_name="Indeed",
        match_mode="fuzzy",
        mentioned_weight=0.25,
        force_classic_template=True,
        prefer_literal_jd_surface=False,
        emphasize_bullet_evidence=True,
        hint="Indeed: board funnel — often redirects to employer ATS; using safe generic knobs.",
    ),
    "generic": PortalProfile(
        family="generic",
        display_name="Generic / Other",
        match_mode="exact",
        mentioned_weight=0.25,
        force_classic_template=True,
        prefer_literal_jd_surface=True,
        emphasize_bullet_evidence=True,
        hint="Generic: quals-first + Workday-safe single-column.",
    ),
}

_ALIASES: list[tuple[str, str]] = [
    ("boards.greenhouse.io", "greenhouse"),
    ("greenhouse", "greenhouse"),
    ("ashbyhq", "ashby"),
    ("ashby", "ashby"),
    ("myworkdayjobs", "workday"),
    ("myworkday", "workday"),
    ("workday", "workday"),
    ("jobs.lever.co", "lever"),
    ("lever.co", "lever"),
    ("lever", "lever"),
    ("taleo", "taleo"),
    ("oracle cloud", "taleo"),
    ("icims", "icims"),
    ("successfactors", "successfactors"),
    ("success factors", "successfactors"),
    ("sap recruiting", "successfactors"),
    ("linkedin", "linkedin"),
    ("easy apply", "linkedin"),
    ("indeed", "indeed"),
    ("smartrecruiters", "generic"),
    ("jobvite", "generic"),
    ("workable", "generic"),
    ("jazzhr", "generic"),
    ("rippling", "generic"),
]


PORTAL_OPTIONS: list[tuple[str, str]] = [
    ("greenhouse", "Greenhouse"),
    ("ashby", "Ashby"),
    ("workday", "Workday"),
    ("lever", "Lever"),
    ("taleo", "Taleo (Oracle)"),
    ("icims", "iCIMS"),
    ("successfactors", "SuccessFactors (SAP)"),
    ("linkedin", "LinkedIn"),
    ("indeed", "Indeed"),
    ("generic", "Other / Unknown"),
]


def resolve_portal_profile(portal: str | None) -> PortalProfile:
    """Map free-text or dropdown value to a PortalProfile."""
    if not portal or not portal.strip():
        return _PROFILES["generic"]
    text = portal.strip().lower()
    if text in _PROFILES:
        return _PROFILES[text]
    for alias, family in _ALIASES:
        if alias in text:
            return _PROFILES[family]
    return _PROFILES["generic"]


def portal_prompt_instructions(profile: PortalProfile) -> str:
    """Deterministic Gemini tone / emphasis lines for this ATS family."""
    bits = [
        f"ATS family: {profile.display_name} ({profile.match_mode} matching).",
    ]
    if profile.prefer_literal_jd_surface:
        bits.append(
            "Prefer the JD's exact skill surface forms in rewrites (literal keyword ATS)."
        )
    if profile.emphasize_bullet_evidence:
        bits.append(
            "Keep concrete evidence in each bullet — criteria-based ATS cite resume text."
        )
    if profile.force_classic_template:
        bits.append("Resume will be single-column for parser safety.")
    return " ".join(bits)
