# ATS Resume Tailor

Upload a resume (PDF/DOCX), paste a job description, download a tailored,
ATS-friendly PDF. See `SPEC.md` for the full product spec and pipeline.

## Stack

- **Backend**: Python FastAPI (parsing, NLP, scoring, verification, WeasyPrint PDF generation)
- **Frontend**: Vite + React + TypeScript + Tailwind, built to static files and served by FastAPI
- **LLM**: Google Gemini Flash — exactly one API call per resume run

## Quick start (one command)

```bash
./run.sh
```

Sets up everything that's missing (Python venv, dependencies, spaCy model,
frontend node_modules) and starts both servers:

- App: http://localhost:5173
- API: http://localhost:8000/api/health

Press Ctrl+C once to stop both. Requires Pango for PDF generation
(`brew install pango` on macOS) — the script warns if it's missing.

## Manual setup (alternative)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn backend.main:app --reload --port 8000
```

Health check: http://localhost:8000/api/health

Note: WeasyPrint needs native libraries (Pango). On macOS: `brew install pango`.

### Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to the
backend on port 8000.

### Production build (single service)

```bash
cd frontend && npm run build && cd ..
uvicorn backend.main:app --port 8000
```

FastAPI serves the built frontend from `frontend/dist` at http://localhost:8000.

## Docker

```bash
docker build -t ats-resume-tailor .
docker run -p 8000:8000 -e GEMINI_API_KEY=... -e ACCESS_CODE=... ats-resume-tailor
```

## Environment variables

- `GEMINI_API_KEY` — Google Gemini API key
- `ACCESS_CODE` — shared access code protecting the API quota
