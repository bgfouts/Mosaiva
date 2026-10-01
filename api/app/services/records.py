from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hypothesis, Intervention


_CONFIDENCE_PHRASES = (
    ("moderate-high", 0.70),
    ("low-moderate", 0.35),
    ("very low", 0.08),
    ("moderate", 0.55),
    ("high", 0.80),
    ("low", 0.20),
)


def clamp_probability(value: float) -> float:
    return max(0.05, min(0.95, float(value)))


def confidence_to_probability(text: str) -> float:
    """Turn a qualitative fit label into Mosaic's internal estimate.

    Longer phrases win, and every match in the label is averaged. "High for rash;
    Low–Moderate for sleepiness" is the mean of high and low-moderate.
    """
    normalized = (text or "").lower().replace("–", "-").replace("—", "-")
    values: list[float] = []
    index = 0
    while index < len(normalized):
        matched: tuple[int, float] | None = None
        for phrase, value in _CONFIDENCE_PHRASES:
            end = index + len(phrase)
            if not normalized.startswith(phrase, index):
                continue
            before_ok = index == 0 or not normalized[index - 1].isalpha()
            after_ok = end == len(normalized) or not normalized[end].isalpha()
            if before_ok and after_ok:
                matched = (end, value)
                break
        if matched is None:
            index += 1
            continue
        values.append(matched[1])
        index = matched[0]
    if not values:
        return clamp_probability(0.5)
    return clamp_probability(sum(values) / len(values))


def next_hypothesis_position(db: Session) -> int:
    from sqlalchemy import func

    current = db.scalar(select(func.max(Hypothesis.position))) or 0
    return int(current) + 1


def next_intervention_position(db: Session) -> int:
    from sqlalchemy import func

    current = db.scalar(select(func.max(Intervention.position))) or 0
    return int(current) + 1


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
