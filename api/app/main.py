from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db, open_session
from app.routers import coach, hypotheses, interventions, mosaic, research, settings
from app.services.seed import seed_hypotheses, seed_interventions
from app.settings import DATA_DIR, PAPERS_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    db = open_session()
    try:
        seed_hypotheses(db)
        seed_interventions(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Mosaiva", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(hypotheses.router, prefix="/api")
    app.include_router(interventions.router, prefix="/api")
    app.include_router(research.router, prefix="/api")
    app.include_router(coach.router, prefix="/api")
    app.include_router(mosaic.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
