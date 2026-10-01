from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ResearchItem
from app.schemas import ResearchPatch, ResearchSearchIn
from app.serialize import research_dict
from app.services.records import load_hypotheses, load_interventions
from app.services.research import search_and_store

router = APIRouter(prefix="/research", tags=["research"])


def _get(db: Session, research_id: int) -> ResearchItem:
    item = db.scalar(
        select(ResearchItem)
        .options(selectinload(ResearchItem.hypotheses), selectinload(ResearchItem.interventions))
        .where(ResearchItem.id == research_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Research item not found.")
    return item


@router.get("")
def list_research(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ResearchItem)
        .options(selectinload(ResearchItem.hypotheses), selectinload(ResearchItem.interventions))
        .order_by(ResearchItem.created_at.desc())
    ).all()
    return [research_dict(row) for row in rows]


@router.post("/search")
def search_research(body: ResearchSearchIn, db: Session = Depends(get_db)):
    try:
        result = search_and_store(db, body.query.strip(), body.hypothesis_ids, body.intervention_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "items": [research_dict(item) for item in result["items"]],
        "considered": result["considered"],
        "kept": result["kept"],
        "skipped": result["skipped"],
        "message": result["message"],
    }


@router.patch("/{research_id}")
def link_research(research_id: int, body: ResearchPatch, db: Session = Depends(get_db)):
    item = _get(db, research_id)
    data = body.model_dump(exclude_unset=True)
    if "hypothesis_ids" in data:
        item.hypotheses = load_hypotheses(db, data["hypothesis_ids"])
    if "intervention_ids" in data:
        item.interventions = load_interventions(db, data["intervention_ids"])
    db.commit()
    db.refresh(item)
    return research_dict(item)
