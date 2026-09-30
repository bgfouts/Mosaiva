from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Hypothesis
from app.schemas import HypothesisIn, HypothesisPatch
from app.serialize import hypothesis_dict
from app.services.records import clamp_probability, confidence_to_probability, next_hypothesis_position

router = APIRouter(prefix="/hypotheses", tags=["hypotheses"])


def _get(db: Session, hypothesis_id: int) -> Hypothesis:
    item = db.scalar(
        select(Hypothesis).options(selectinload(Hypothesis.evidence)).where(Hypothesis.id == hypothesis_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found.")
    return item


@router.get("")
def list_hypotheses(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Hypothesis)
        .options(selectinload(Hypothesis.evidence))
        .order_by(Hypothesis.position.asc(), Hypothesis.id.asc())
    ).all()
    return [hypothesis_dict(row) for row in rows]


@router.post("", status_code=201)
def create_hypothesis(body: HypothesisIn, db: Session = Depends(get_db)):
    if body.probability is None:
        probability = confidence_to_probability(body.confidence) if body.confidence.strip() else 0.5
    else:
        probability = body.probability
    item = Hypothesis(
        title=body.title.strip(),
        statement=body.statement.strip(),
        why_it_fits=body.why_it_fits.strip(),
        confidence=body.confidence.strip(),
        likely_role=body.likely_role.strip(),
        position=next_hypothesis_position(db),
        domains=[domain.strip() for domain in body.domains if domain.strip()],
        status=body.status,
        probability=clamp_probability(probability),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@router.patch("/{hypothesis_id}")
def update_hypothesis(hypothesis_id: int, body: HypothesisPatch, db: Session = Depends(get_db)):
    item = _get(db, hypothesis_id)
    data = body.model_dump(exclude_unset=True)
    previous_confidence = item.confidence or ""
    if "title" in data:
        item.title = data["title"].strip()
    if "statement" in data:
        item.statement = data["statement"].strip()
    if "why_it_fits" in data:
        item.why_it_fits = data["why_it_fits"].strip()
    if "likely_role" in data:
        item.likely_role = data["likely_role"].strip()
    if "confidence" in data:
        item.confidence = data["confidence"].strip()
    if "domains" in data:
        item.domains = [domain.strip() for domain in data["domains"] if domain.strip()]
    if "status" in data:
        item.status = data["status"]
    if "probability" in data:
        item.probability = clamp_probability(data["probability"])
    elif "confidence" in data and item.confidence != previous_confidence and item.confidence:
        item.probability = confidence_to_probability(item.confidence)
    if "why_moved" in data:
        item.why_moved = data["why_moved"]
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return hypothesis_dict(item)


@router.delete("/{hypothesis_id}", status_code=204)
def delete_hypothesis(hypothesis_id: int, db: Session = Depends(get_db)):
    item = _get(db, hypothesis_id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)
