from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Hypothesis, MosaicReview
from app.routers.settings import ensure_settings
from app.schemas import MosaicDecisionIn
from app.serialize import review_dict
from app.services.llm import OpenAIReasoner
from app.services.mosaic import (
    MOSAIC_INSTRUCTIONS,
    MosaicValidationError,
    apply_decision,
    create_review,
    fixture_review,
)
from app.services.weeks import week_start
from app.settings import get_settings

router = APIRouter(prefix="/mosaic", tags=["mosaic"])


def _titles(db: Session) -> dict[int, str]:
    return {row.id: row.title for row in db.scalars(select(Hypothesis)).all()}


def _review_out(db: Session, review: MosaicReview) -> dict:
    return review_dict(review, _titles(db))


@router.get("")
def read_mosaic(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    current = week_start(settings.timezone)
    review = db.scalar(select(MosaicReview).where(MosaicReview.week_start == current))
    history = db.scalars(select(MosaicReview).order_by(MosaicReview.week_start.desc())).all()
    titles = _titles(db)
    return {
        "week_start": current.isoformat(),
        "timezone": settings.timezone,
        "review": review_dict(review, titles) if review else None,
        "history": [review_dict(item, titles) for item in history],
    }


@router.post("/run")
def run_mosaic(db: Session = Depends(get_db)):
    settings = ensure_settings(db)
    current = week_start(settings.timezone)
    existing = db.scalar(select(MosaicReview).where(MosaicReview.week_start == current))
    if existing:
        return _review_out(db, existing)

    app_settings = get_settings()

    def reasoner(snapshot: dict) -> dict:
        if app_settings.mosaiva_mosaic_fixture:
            return fixture_review(snapshot)
        if not app_settings.openai_api_key:
            raise HTTPException(
                status_code=503,
                detail="Mosaic needs an OpenAI API key on this machine to read the record.",
            )
        try:
            return OpenAIReasoner().complete_json(MOSAIC_INSTRUCTIONS, snapshot)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Mosaic could not complete a review.") from exc

    try:
        review = create_review(db, settings, reasoner)
    except HTTPException:
        raise
    except MosaicValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(MosaicReview).where(MosaicReview.week_start == current))
        if raced:
            return _review_out(db, raced)
        raise
    return _review_out(db, review)


@router.post("/{review_id}/decision")
def decide(review_id: int, body: MosaicDecisionIn, db: Session = Depends(get_db)):
    review = db.get(MosaicReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    settings = ensure_settings(db)
    review = apply_decision(db, review, settings, body)
    return _review_out(db, review)
