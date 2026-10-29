from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import require_user
from app.db import init_db, open_session, startup_lock
from app.routers import auth, coach, hypotheses, interventions, mosaic, research, settings
from app.services.seed import seed_hypotheses, seed_interventions, seed_research
from app.settings import DATA_DIR, ON_VERCEL, WEB_BUILD_DIR, get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().database_url.startswith("sqlite"):
        if ON_VERCEL:
            raise RuntimeError("DATABASE_URL is not set. Connect a Neon database to this Vercel project.")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    with startup_lock():
        init_db()
        db = open_session()
        try:
            seed_hypotheses(db)
            seed_interventions(db)
            seed_research(db)
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Mosaiva", version="0.1.0", lifespan=lifespan)
    if not ON_VERCEL:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    signed_in = [Depends(require_user)]
    app.include_router(auth.router, prefix="/api")
    app.include_router(hypotheses.router, prefix="/api", dependencies=signed_in)
    app.include_router(interventions.router, prefix="/api", dependencies=signed_in)
    app.include_router(research.router, prefix="/api", dependencies=signed_in)
    app.include_router(coach.router, prefix="/api", dependencies=signed_in)
    app.include_router(mosaic.router, prefix="/api", dependencies=signed_in)
    app.include_router(settings.router, prefix="/api", dependencies=signed_in)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    # Vercel's FastAPI preset does not publish static files created by the build command, so the
    # function serves the built web app itself.
    if ON_VERCEL and WEB_BUILD_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_BUILD_DIR, html=True), name="web")

    return app


app = create_app()
