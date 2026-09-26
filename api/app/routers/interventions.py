from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Intervention
from app.schemas import InterventionIn, InterventionPatch
from app.serialize import intervention_dict
from app.services.records import assert_intervention_rules, load_hypotheses

router = APIRouter(prefix="/interventions", tags=["interventions"])


def _get(db: Session, intervention_id: int) -> Intervention:
    item = db.scalar(
        select(Intervention)
        .options(selectinload(Intervention.hypotheses))
        .where(Intervention.id == intervention_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Intervention not found.")
    return item


@router.get("")
def list_interventions(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Intervention).options(selectinload(Intervention.hypotheses)).order_by(Intervention.updated_at.desc())
    ).all()
    return [intervention_dict(row) for row in rows]


@router.post("", status_code=201)
def create_intervention(body: InterventionIn, db: Session = Depends(get_db)):
    item = Intervention(
        name=body.name.strip(),
        category=body.category,
        dose=body.dose.strip(),
        schedule=body.schedule.strip(),
        clinician_prescribed=body.clinician_prescribed,
        status=body.status,
        start_date=body.start_date,
        stop_date=body.stop_date,
        benefit=body.benefit,
        side_effect_burden=body.side_effect_burden,
        side_effect_notes=body.side_effect_notes.strip(),
    )
    item.hypotheses = load_hypotheses(db, body.hypothesis_ids)
    assert_intervention_rules(item)
    db.add(item)
    db.commit()
    db.refresh(item)
    return intervention_dict(item)


@router.patch("/{intervention_id}")
def update_intervention(intervention_id: int, body: InterventionPatch, db: Session = Depends(get_db)):
    item = _get(db, intervention_id)
    data = body.model_dump(exclude_unset=True)
    for field in (
        "name",
        "category",
        "dose",
        "schedule",
        "clinician_prescribed",
        "status",
        "start_date",
        "stop_date",
        "benefit",
        "side_effect_burden",
        "side_effect_notes",
        "clinician_task",
    ):
        if field in data:
            value = data[field]
            if isinstance(value, str):
                value = value.strip()
            setattr(item, field, value)
    if "hypothesis_ids" in data:
        item.hypotheses = load_hypotheses(db, data["hypothesis_ids"])
    assert_intervention_rules(item)
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return intervention_dict(item)


@router.delete("/{intervention_id}", status_code=204)
def delete_intervention(intervention_id: int, db: Session = Depends(get_db)):
    item = _get(db, intervention_id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)
