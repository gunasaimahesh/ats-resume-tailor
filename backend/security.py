"""Shared access code gate (SPEC: protects the API quota).

If the ACCESS_CODE env var is set, /api/tailor and /api/render require a
matching X-Access-Code header. When unset (local dev), everything is open.
"""

import os

from fastapi import Header, HTTPException


def require_access_code(x_access_code: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ACCESS_CODE")
    if expected and x_access_code != expected:
        raise HTTPException(status_code=401, detail="Invalid access code.")
