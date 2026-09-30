import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hypothesis
from app.services.records import confidence_to_probability
from app.settings import get_settings

THEORIES_PATH = Path(__file__).resolve().parent.parent / "data" / "health_theories.json"

SHEET_TITLE = "Health Differential / Theories Discussed"
CONFIDENCE_NOTE = (
    "Confidence reflects how well each theory currently fits the reported pattern; "
    "it is not a diagnosis or a calculated probability."
)
SHEET_FOOTER = (
    "Important: This workbook summarizes hypotheses discussed in conversation. "
    "It is intended for organizing questions and patterns, not for self-diagnosis or replacing medical evaluation."
)


def load_theories() -> list[dict]:
    return json.loads(THEORIES_PATH.read_text(encoding="utf-8"))


def seed_hypotheses(db: Session) -> int:
    if not get_settings().mosaiva_seed_hypotheses:
        return 0
    theories = load_theories()
    existing = set(db.scalars(select(Hypothesis.title)).all())
    added = 0
    for index, theory in enumerate(theories, start=1):
        title = str(theory["title"]).strip()
        if title in existing:
            continue
        confidence = str(theory.get("confidence") or "").strip()
        db.add(
            Hypothesis(
                title=title,
                statement=str(theory.get("description") or "").strip(),
                why_it_fits=str(theory.get("why_it_fits") or "").strip(),
                confidence=confidence,
                likely_role=str(theory.get("likely_role") or "").strip(),
                position=index,
                domains=[],
                status="active",
                probability=confidence_to_probability(confidence),
            )
        )
        existing.add(title)
        added += 1
    if added:
        db.commit()
    return added
