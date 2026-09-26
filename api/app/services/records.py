from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hypothesis, Intervention


def clamp_probability(value: float) -> float:
    return max(0.05, min(0.95, float(value)))


def assert_intervention_rules(item: Intervention) -> None:
    if item.status == "ask_clinician" and (item.dose or "").strip():
        raise HTTPException(
            status_code=422,
            detail="A medicine you are not taking cannot include a dose.",
        )


def load_hypotheses(db: Session, ids: list[int]) -> list[Hypothesis]:
    if not ids:
        return []
    rows = list(db.scalars(select(Hypothesis).where(Hypothesis.id.in_(ids))).all())
    found = {row.id for row in rows}
    missing = [item for item in ids if item not in found]
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown hypothesis ids: {missing}")
    return rows


def load_interventions(db: Session, ids: list[int]) -> list[Intervention]:
    if not ids:
        return []
    rows = list(db.scalars(select(Intervention).where(Intervention.id.in_(ids))).all())
    found = {row.id for row in rows}
    missing = [item for item in ids if item not in found]
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown intervention ids: {missing}")
    return rows
