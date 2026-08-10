# ATS Resume Tailor — Spec

## Product
A website where a user uploads their resume (PDF or DOCX), pastes a job description (JD), and downloads a tailored, ATS-friendly resume PDF. The tool rephrases and re-emphasizes the user's REAL experience using JD terminology. It must NEVER invent experience, skills, numbers, companies, titles, or dates. Optional company / job title / job portal fields may tune phrasing tone only.

## Stack
- Backend: Python FastAPI. Owns parsing, NLP, scoring, verification, PDF generation.
- Frontend: Vite + React + TypeScript + Tailwind, built to static files and served by FastAPI (one service, no CORS).
- LLM: Google Gemini Flash. EXACTLY ONE API call per resume run (plus at most one retry on invalid JSON). Everything else is deterministic Python — including the TailorPlan (skills order, bullet order, per-bullet keyword directives).
- PDF: WeasyPrint rendering HTML/CSS templates (classic single-column or compact two-column). No headless browser.
- No database. Stateless. Shared access code via env var protects the API quota.
- Deploy target: single Docker container on Render/Railway.

## Pipeline (order matters)
1. Extract raw text locally: pdfplumber (PDF) / python-docx (DOCX). Heuristic section + bullet detection (including glyph-less achievement lines); number bullets B1, B2, .... Commas never start a new bullet/skill row — only a sentence-ending full stop (or a real bullet glyph) may. Structure heading (name + optional professional headline), contact (email/phone/location/linkedin/github/website), summary (heading or header-prose fallback), skill groups (comma-separated within a category), experience, education (school keeps campus commas like "IIT, Roorkee"; degree/gpa/location/dates), projects, certifications, awards (plain lines), publications (plain lines), languages; unmatched sections stay in other_sections.
2. Extract JD keywords locally (before any Gemini call): spaCy en_core_web_sm + YAKE + curated skills dictionary with synonym groups (JS=JavaScript, K8s=Kubernetes...). Classify by JD section into required (Minimum/Required quals), nice_to_have (Preferred), or mentioned (About/Responsibilities/marketing — default before any heading). YAKE extras only from qualification sections. Only dictionary required/nice skills are claimable (`in_dictionary=true` and not `mentioned`). Optional job portal resolves an ATS family profile (Workday/Greenhouse/Ashby/…) that tunes scoring weights, dual acronym forms, template safety, and Gemini tone.
3. Compute parse-time "before" ATS score locally when a JD is provided (returned from POST /api/parse for the Review step): rapidfuzz exact+fuzzy+synonym keyword coverage, weighted by importance (mentioned uses a low portal-specific weight). Required-coverage band ignores mentioned keywords. The same scoring runs again after tailoring for the Results before/after comparison.
4. Deterministic TailorPlan (Python): per-bullet evidenced JD keywords, canonical synonym swaps, relevance scores, skills order (all whitelist skills, JD-matched first), within-job bullet reorder, summary must-include keywords, and unevidenced required-keyword gaps. Then THE single Gemini call (temperature 0, JSON schema mode, Pydantic-validated) — runs only after the user reviews/edits Step 2 and clicks Tailor. Input: TailorPlan directives + numbered source bullets + JD keyword lists + truncated JD excerpt + optional company/title/portal + target page budget. Output ONLY: (a) rewritten bullet text keyed by source bullet ID, (b) summary paragraph. Skills are NOT chosen by Gemini. Contact info, companies, titles, dates, education, certifications, awards, languages are NOT in the output schema — they are copied from the original programmatically. Every source bullet ID must be returned; if Gemini omits an ID, keep the original bullet text. Merge applies planned bullet order and deterministic skills / skill_groups.
5. Deterministic groundedness verifier (no LLM): metric preservation (source numbers must survive); digit rule — every number in output must exist in original text; entity rule — spaCy NER entities in output must fuzzy-match original text. Failing bullets auto-revert to original wording and get flagged. Summary is verified the same way; on failure fall back to original summary or a deterministic grounded summary.
6. Keyword preservation: every JD keyword with evidence in the original resume must survive into the final output — if a rewrite/revert removes it, place it in the Skills section (whitelist = original skills ∪ skill_groups).
7. Page fitting: when original page count is known, default target pages = same as original (user can override to 1/2/auto). NEVER drop experience bullets. If render overflows the target, re-render at progressively denser CSS presets (normal → compact → dense); if still over at densest, grow the page count. Keyword non-regression may append skills. No extra LLM calls.
8. Render PDF with WeasyPrint (classic single-column or two-column template; standard skill categories; multi-line contact; right-aligned dates; education raw_lines). Then round-trip self-check: re-extract text with pdfplumber and verify sections, bullets, contact fields, and skills survived.
9. Compute "after" ATS score on the FINAL content (post-revert, post-trim, post-repair). Display against a 70-80% required-keyword coverage band (green/yellow/red). Surface keyword gaps and repairs in the UI.

## UI (3 steps)
1. Input: drag-and-drop resume upload, JD paste box, page-count selector (default "same as original"), optional company / job title / job portal, access code.
2. Review: ATS fit panel from parse-time JD keywords + before score — matched chips, and checkboxes for missing **dictionary** skills the user can claim (adds to Skills before tailor; only check what they can defend). Plus structured labeled fields for every common section (heading/name/headline + contact, summary, skills, experience, education, projects, certifications, awards, publications, languages, other) for quick correction. Gemini has not been called yet.
3. Results: before/after score, keyword checklist (matched / added / still missing), gaps (unevidenced required keywords), preserved/repaired skills, side-by-side diff of changed bullets with per-bullet accept/reject and auto-revert flags, embedded PDF preview, and a download button that re-renders with only the accepted bullets.

## Layout
- backend/main.py (FastAPI app, serves API + built frontend)
- backend/routes/ (parse, tailor, render endpoints)
- backend/schema.py (Pydantic models)
- backend/nlp/jd_keywords.py, backend/nlp/scoring.py, backend/nlp/verifier.py, backend/nlp/tailor_plan.py
- backend/llm/gemini.py
- backend/render/template.html + print.css
- frontend/ (Vite React app)
- Dockerfile, requirements.txt, README.md
