"""ATS Resume Tailor — FastAPI app. Serves the API and the built frontend."""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

from backend.routes import parse, render, tailor  # noqa: E402

app = FastAPI(title="ATS Resume Tailor")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(parse.router, prefix="/api")
app.include_router(tailor.router, prefix="/api")
app.include_router(render.router, prefix="/api")

# Serve the frontend production build (frontend/dist) if it exists.
# In dev mode the Vite dev server runs separately and proxies /api here.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
