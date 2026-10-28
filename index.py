"""Vercel entrypoint. The FastAPI app lives in api/app so local runs and tests stay unchanged."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "api"))

from app.main import app  # noqa: E402,F401
