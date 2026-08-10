# Build Prompts — ATS Resume Tailor

Run these prompts one at a time, in order. Finish and verify each step before moving to the next.
Prompt 1 creates `SPEC.md`; every prompt after that tells the model to read it first, so you can
run each prompt in a fresh chat without losing context.

---

## Prompt 1 — Project spec

```
Create a file SPEC.md at the project root with exactly the following content, then read it back to me to confirm:

# ATS Resume Tailor — Spec

## Product
A website where a user uploads their resume (PDF or DOCX), pastes a job description (JD), and downloads a tailored, ATS-friendly resume PDF. The tool rephrases and re-emphasizes the user's REAL experience using JD terminology. It must NEVER invent experience, skills, numbers, companies, titles, or dates.

## Stack
- Backend: Python FastAPI. Owns parsing, NLP, scoring, verification, PDF generation.
- Frontend: Vite + React + TypeScript + Tailwind, built to static files and served by FastAPI (one service, no CORS).
- LLM: Google Gemini Flash. EXACTLY ONE API call per resume run (plus at most one retry on invalid JSON). Everything else is deterministic Python.
- PDF: WeasyPrint rendering a single-column HTML/CSS template. No headless browser.
- No database. Stateless. Shared access code via env var protects the API quota.
- Deploy target: single Docker container on Render/Railway.

## Pipeline (order matters)
1. Extract raw text locally: pdfplumber (PDF) / python-docx (DOCX). Heuristic section + bullet detection; number bullets B1, B2, ...
2. Extract JD keywords locally: spaCy en_core_web_sm + YAKE + curated skills dictionary with synonym groups (JS=JavaScript, K8s=Kubernetes...). Classify required vs nice-to-have.
3. Compute "before" ATS score locally: rapidfuzz exact+fuzzy+synonym keyword coverage, weighted by importance.
4. THE single Gemini call (temperature 0, JSON schema mode, Pydantic-validated). Input: numbered resume bullets + JD keywords + target page budget. Output ONLY: (a) rewritten bullet text keyed by source bullet ID, (b) summary paragraph, (c) skill selection/ordering from an enum whitelist of the user's ORIGINAL skills. Contact info, companies, titles, dates, education are NOT in the output schema — they are copied from the original programmatically. Unmapped bullets are discarded.
5. Deterministic groundedness verifier (no LLM): digit rule — every number in output must exist in original text; entity rule — spaCy NER entities in output must fuzzy-match original text. Failing bullets auto-revert to original wording and get flagged.
6. Keyword preservation: every JD keyword with evidence in the original resume must survive into the final output — if a revert removes it from a bullet, place it in the Skills section (whitelist-safe).
7. Page fitting: target pages = 1 if total experience <= 3 years else 2, user can override (including "same as original"). If render overflows, drop/trim lowest-JD-relevance bullets programmatically. Never drop a bullet that is the sole carrier of a matched keyword. No extra LLM calls.
8. Render PDF with WeasyPrint. Then round-trip self-check: re-extract text with pdfplumber and verify all sections, bullets, contact fields survived.
9. Compute "after" ATS score on the FINAL content (post-revert, post-trim). Display against a 70-80% required-keyword coverage band (green/yellow/red).

## UI (3 steps)
1. Input: drag-and-drop resume upload, JD paste box, page-count selector, access code.
2. Review: extracted text/sections shown for quick correction before tailoring.
3. Results: before/after score, keyword checklist (matched / added / still missing), side-by-side diff of changed bullets with per-bullet accept/reject and auto-revert flags, embedded PDF preview, download.

## Layout
- backend/main.py (FastAPI app, serves API + built frontend)
- backend/routes/ (parse, tailor, render endpoints)
- backend/schema.py (Pydantic models)
- backend/nlp/jd_keywords.py, backend/nlp/scoring.py, backend/nlp/verifier.py
- backend/llm/gemini.py
- backend/render/template.html + print.css
- frontend/ (Vite React app)
- Dockerfile, requirements.txt, README.md
```

---

## Prompt 2 — Scaffold

```
Read SPEC.md. Scaffold the project exactly per its Layout section: a FastAPI backend and a Vite + React + TypeScript + Tailwind frontend, where FastAPI serves the frontend's production build. Create requirements.txt (fastapi, uvicorn, pdfplumber, python-docx, spacy, yake, rapidfuzz, weasyprint, google-genai, pydantic, python-multipart) and package.json. Add a Dockerfile that builds the frontend, installs Python deps including the spaCy en_core_web_sm model, and runs uvicorn. Add a /api/health endpoint and a placeholder homepage. Give me the commands to run it locally in dev mode (backend + frontend) and verify both start.
```

---

## Prompt 3 — Resume parsing

```
Read SPEC.md. Implement pipeline step 1: resume text extraction in the backend. Accept PDF (pdfplumber) and DOCX (python-docx) uploads at POST /api/parse. Detect sections heuristically (Experience, Education, Skills, Projects, Summary — tolerate common variants like "Work History" or "Technical Skills"). Split experience entries into company/title/date headers and bullets; number every bullet B1, B2, ... Also extract contact info (name, email, phone, links) and a flat list of skills. Return it all as structured JSON (define the Pydantic models in backend/schema.py). Write a quick test using a sample resume text to prove section and bullet detection works.
```

---

## Prompt 4 — JD keyword extraction

```
Read SPEC.md. Implement pipeline step 2 in backend/nlp/jd_keywords.py: extract keywords from a pasted job description using spaCy + YAKE, cross-checked against a curated skills dictionary (create one covering common software/data/cloud skills with synonym groups, e.g. JS=JavaScript, K8s=Kubernetes, ML=Machine Learning). Classify each keyword as "required" or "nice-to-have" based on JD phrasing (must have / required vs nice to have / bonus / plus). Expose it inside POST /api/parse's response when a JD is provided. Show me the extracted keywords for a sample JD I can test with.
```

---

## Prompt 5 — ATS scoring engine

```
Read SPEC.md. Implement pipeline steps 3 and 9's scoring engine in backend/nlp/scoring.py: given resume content and the extracted JD keywords, compute keyword coverage using rapidfuzz (exact match, fuzzy match above a sane threshold, and synonym-group match), weighted so required keywords count more than nice-to-have. Return: overall score 0-100, and per-keyword status (matched / missing) with where it matched. Include the 70-80% green/yellow/red banding logic. Unit-test it with a resume that obviously matches and one that obviously doesn't.
```

---

## Prompt 6 — The single Gemini call

```
Read SPEC.md. Implement pipeline step 4 in backend/llm/gemini.py — this is the ONLY LLM call in the whole app, so follow the spec's constraints exactly: temperature 0, Gemini JSON schema mode, and an output schema containing ONLY rewritten bullets keyed by source bullet ID, a summary paragraph, and skills chosen from an enum whitelist of the user's original skills. Contact/companies/titles/dates/education must NOT be in the schema. The prompt must instruct: rephrase and re-emphasize using JD terminology, never invent experience/skills/numbers, keep each bullet grounded in its source bullet. Validate the response with Pydantic; retry once on invalid JSON, then fail gracefully. Merge the output with the programmatically-copied fact fields into a full tailored-resume object. API key from env var GEMINI_API_KEY. Wire it into POST /api/tailor.
```

---

## Prompt 7 — Groundedness verifier

```
Read SPEC.md. Implement pipeline steps 5 and 6 in backend/nlp/verifier.py, fully deterministic, no LLM: (1) digit rule — every number appearing in a rewritten bullet must appear somewhere in the original resume text, else revert that bullet to its original wording and flag it; (2) entity rule — run spaCy NER on rewritten bullets and fuzzy-match (rapidfuzz) each ORG/PRODUCT/proper-noun entity against the original text, revert+flag on failure; (3) keyword preservation — after reverts, any JD keyword that had evidence in the original resume but vanished from the output must be added to the Skills section (only if it's in the original-skills whitelist or synonym groups). Run this automatically after the Gemini call inside /api/tailor. Unit-test with a fabricated-metric bullet and a fabricated-technology bullet and show both get reverted.
```

---

## Prompt 8 — PDF template, page fitting, self-check

```
Read SPEC.md. Implement pipeline steps 7 and 8: create backend/render/template.html + print.css — a clean, single-column, ATS-friendly resume template (standard section headings, standard fonts, no tables/columns/images/headers/footers) rendered by WeasyPrint at POST /api/render. Page-count logic: default 1 page if total experience <= 3 years (computed from resume dates) else 2, with an override parameter including "same as original". If the render overflows the target, drop/trim the lowest-JD-relevance bullets and re-render — but never drop a bullet that is the sole carrier of a matched keyword. After rendering, run the round-trip self-check: re-extract text with pdfplumber and verify sections, bullets, and contact fields all survived; include the check result in the response. Generate a sample PDF so I can look at it.
```

---

## Prompt 9 — Frontend flow

```
Read SPEC.md. Build the full 3-step frontend flow per its UI section, calling the existing /api/parse, /api/tailor, /api/render endpoints. Step 1: drag-and-drop resume upload, JD paste box, page-count selector, access code field. Step 2: show extracted sections/bullets for quick correction before tailoring. Step 3: before/after ATS score with green/yellow/red band, keyword checklist (matched / added / still missing), side-by-side diff of every changed bullet with per-bullet accept/reject toggles and auto-revert flags, embedded PDF preview, and a download button that re-renders with only the accepted bullets. Make it look modern and clean. Show loading states for each pipeline stage.
```

---

## Prompt 10 — Access gate, polish, deploy

```
Read SPEC.md. Finish the app: (1) enforce the shared access code on all API endpoints via env var ACCESS_CODE, returning 401 otherwise; (2) add sensible error handling for unreadable files, empty JDs, and Gemini failures, surfaced as friendly messages in the UI; (3) verify the Dockerfile builds and the container serves both the frontend and API; (4) write README.md with local setup, env vars (GEMINI_API_KEY, ACCESS_CODE), and step-by-step deployment instructions for Render's free tier. Then walk me through deploying it.
```

---

## Prompt 11 — Extraction hardening + full structured Review fields

```
Read SPEC.md and the current extraction pipeline before changing anything.

When Gemini runs (do not change this UX):
- POST /api/parse is local only and feeds Step 2 Review.
- Gemini runs ONLY on POST /api/tailor after the user edits Review and clicks "Tailor my resume".
- Do NOT add a Gemini call for extraction.

Bugs from Review after PDF upload:
1. summary empty
2. only one job with no bullets; other jobs missing
3. education is unstructured lines — need school / degree / gpa / location / dates
4. other common sections are raw/confusing — structure them too

Architecture constraints:
- Extraction = pdfplumber + python-docx + heuristics in backend/parsing.py only.
- Exactly one Gemini tailor call: rewrite bullets + summary + skill order from whitelist.
- Contact, companies, titles, dates, education, projects metadata, certs, awards, languages are copied programmatically — never invented.

Required structured schema (Review must show labeled fields):
- ContactInfo: name, email, phone, location, linkedin, github, website, leftover links[]
- summary: str | null (with header-prose fallback)
- skill_groups: [{ category | null, items: string[] }] + flat skills list for Gemini whitelist
- ExperienceEntry: title, company, location, dates, bullets[{id,text}], header_raw
- EducationEntry: school, degree, gpa, location, dates, raw_lines
- ProjectEntry: name, dates, url?, tech?, bullets[]
- CertificationEntry: name, issuer?, date?, url?
- AwardEntry: title, date?, description?
- LanguageEntry: language, proficiency?
- other_sections: fallback raw blocks

Work:
A) Update schema, frontend types, ReviewStep, template, scoring, merge_tailored, tests.
B) Harden parsing.py: summary fallback; multi-job + glyph-less bullets; education/certs/awards/languages parsers; contact link classification; skill categories.
C) Review UX: labeled fields + add/remove entries and bullets.
D) Gemini: return every bullet_id once; merge keeps original if omitted; summary from bullets when original missing.
E) Tests + update SPEC.md to match.
```

---

## Tips

- Verify each step works before moving on (each prompt asks for a runnable proof — actually run it).
- If a chat drifts from the architecture, say: "Re-read SPEC.md and fix this to match it."
- If something in the spec needs to change mid-build, update SPEC.md first, then continue — it is the single source of truth.
