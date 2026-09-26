import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models import Evidence, Hypothesis, Intervention, MosaicReview, ResearchItem, SettingsRow
from app.services.records import clamp_probability
from app.services.weeks import local_today, week_start
from app.settings import get_settings

MOSAIC_INSTRUCTIONS = """
You are the Mosaic agent inside Mosaiva, a personal wellness record for one patient.
Hypotheses are working estimates, not diagnoses. You do not prescribe and you do not invent doses.
Return a single JSON object with this shape:
{
  "hypothesis_updates": [
    {
      "hypothesis_id": 1,
      "probability": 0.42,
      "rationale": "short reason",
      "evidence_ids": [1],
      "paper_ids": [2]
    }
  ],
  "recommendation": {
    "action": "add" | "remove" | "hold",
    "intervention_id": null,
    "name": "",
    "category": "lifestyle" | "diet" | "supplement" | "medication" | "therapy" | null,
    "hypothesis_id": null,
    "rationale": "",
    "what_to_watch": "",
    "safety_note": "",
    "dose": ""
  }
}
Rules:
- Exactly one recommendation. Never return a list of recommendations.
- Probabilities are between 0.05 and 0.95.
- Cite only evidence_ids and paper_ids that appear in the snapshot.
- If any active intervention has benefit of 2 or less and side_effect_burden of 4 or more, the only legal action is remove, and intervention_id must be one of those items.
- A prescribed medicine removal must say to discuss stopping with the clinician. Do not tell the patient to stop it today.
- A self-directed lifestyle, diet, or supplement removal may be direct.
- Otherwise you may add one item. Prefer lifestyle or diet, then a supplement, then naming a medicine to ask a clinician about.
- A medication add must use category medication, an empty dose, and a safety_note that tells the patient to ask a clinician and not to start it alone.
- If neither a removal nor an addition is justified, action is hold.
- Do not invent clinical facts that are not in the snapshot.
""".strip()


class MosaicValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_review(snapshot: dict, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise MosaicValidationError("Review must be an object.")
    if isinstance(raw.get("recommendation"), list) or isinstance(raw.get("recommendations"), list):
        raise MosaicValidationError("Only one recommendation is allowed.")
    recommendation = raw.get("recommendation")
    updates = raw.get("hypothesis_updates")
    if not isinstance(recommendation, dict) or not isinstance(updates, list):
        raise MosaicValidationError("Review is missing recommendation or hypothesis updates.")
    if isinstance(recommendation.get("actions"), list):
        raise MosaicValidationError("Only one recommendation is allowed.")

    action = recommendation.get("action")
    if action not in {"add", "remove", "hold"}:
        raise MosaicValidationError("Action must be add, remove, or hold.")

    evidence_ids = {row["id"] for row in snapshot["evidence"]}
    paper_ids = {row["id"] for row in snapshot["papers"]}
    hypothesis_ids = {row["id"] for row in snapshot["hypotheses"]}
    cleaned_updates = []
    for item in updates:
        if not isinstance(item, dict):
            raise MosaicValidationError("Each hypothesis update must be an object.")
        hypothesis_id = item.get("hypothesis_id")
        if hypothesis_id not in hypothesis_ids:
            raise MosaicValidationError(f"Unknown hypothesis {hypothesis_id}.")
        for evidence_id in item.get("evidence_ids") or []:
            if evidence_id not in evidence_ids:
                raise MosaicValidationError(f"Unknown evidence {evidence_id}.")
        for paper_id in item.get("paper_ids") or []:
            if paper_id not in paper_ids:
                raise MosaicValidationError(f"Unknown paper {paper_id}.")
        probability = item.get("probability")
        if not isinstance(probability, (int, float)):
            raise MosaicValidationError("Probability must be a number.")
        cleaned_updates.append(
            {
                "hypothesis_id": hypothesis_id,
                "probability": clamp_probability(probability),
                "rationale": str(item.get("rationale") or ""),
                "evidence_ids": list(item.get("evidence_ids") or []),
                "paper_ids": list(item.get("paper_ids") or []),
            }
        )

    category = recommendation.get("category")
    dose = str(recommendation.get("dose") or "")
    if action == "add" and category == "medication" and dose.strip():
        raise MosaicValidationError("A medication suggestion cannot include a dose.")
    if action == "add" and category == "medication":
        note = str(recommendation.get("safety_note") or "").lower()
        if "clinician" not in note:
            raise MosaicValidationError("A medication suggestion must tell the patient to ask a clinician.")

    costly = _costly_interventions(snapshot["interventions"])
    if costly and action != "remove":
        raise MosaicValidationError(
            "A high-burden, low-benefit intervention must be the removal for this week."
        )
    if costly and recommendation.get("intervention_id") not in {row["id"] for row in costly}:
        raise MosaicValidationError("Removal must target a high-burden, low-benefit intervention.")

    if action == "remove":
        match = next(
            (row for row in snapshot["interventions"] if row["id"] == recommendation.get("intervention_id")),
            None,
        )
        if match is None:
            raise MosaicValidationError("Removal target does not exist.")
        if dose.strip():
            raise MosaicValidationError("A removal cannot include a dose.")
        if match.get("clinician_prescribed"):
            note = str(recommendation.get("safety_note") or "").lower()
            if "clinician" not in note:
                raise MosaicValidationError(
                    "Stopping a prescribed medicine must be framed as a clinician discussion."
                )

    if action == "add":
        if category not in {"medication", "lifestyle", "diet", "supplement", "therapy"}:
            raise MosaicValidationError("Add needs a category.")
        if not str(recommendation.get("name") or "").strip():
            raise MosaicValidationError("Add needs a name.")

    stored_dose = ""
    if action == "add" and category != "medication":
        stored_dose = dose
    return {
        "hypothesis_updates": cleaned_updates,
        "recommendation": {
            "action": action,
            "intervention_id": recommendation.get("intervention_id"),
            "name": str(recommendation.get("name") or ""),
            "category": category,
            "hypothesis_id": recommendation.get("hypothesis_id"),
            "rationale": str(recommendation.get("rationale") or ""),
            "what_to_watch": str(recommendation.get("what_to_watch") or ""),
            "safety_note": str(recommendation.get("safety_note") or ""),
            "dose": stored_dose,
        },
    }


def _costly_interventions(interventions: list[dict]) -> list[dict]:
    costly = []
    for item in interventions:
        benefit = item.get("benefit")
        burden = item.get("side_effect_burden")
        if item.get("status") != "active" or benefit is None or burden is None:
            continue
        if benefit <= 2 and burden >= 4:
            costly.append(item)
    return costly


def fixture_review(snapshot: dict) -> dict:
    updates = []
    for hypothesis in snapshot["hypotheses"]:
        evidence_ids = [
            row["id"] for row in snapshot["evidence"] if row.get("hypothesis_id") == hypothesis["id"]
        ]
        paper_ids = [
            row["id"]
            for row in snapshot["papers"]
            if hypothesis["id"] in (row.get("hypothesis_ids") or [])
        ]
        updates.append(
            {
                "hypothesis_id": hypothesis["id"],
                "probability": hypothesis["probability"],
                "rationale": "Working estimate held from the current record.",
                "evidence_ids": evidence_ids,
                "paper_ids": paper_ids,
            }
        )
    costly = _costly_interventions(snapshot["interventions"])
    if costly:
        target = costly[0]
        safety = (
            "Discuss stopping with your clinician before you change this medicine."
            if target.get("clinician_prescribed")
            else "This is self-directed, so you can stop it without starting a new prescription."
        )
        recommendation = {
            "action": "remove",
            "intervention_id": target["id"],
            "name": target["name"],
            "category": target["category"],
            "hypothesis_id": (target.get("hypothesis_ids") or [None])[0],
            "rationale": "Benefit is low and side-effect burden is high, so this week's only change is to take it away.",
            "what_to_watch": "Notice whether the side effects ease over the next week.",
            "safety_note": safety,
            "dose": "",
        }
    elif snapshot["hypotheses"]:
        top = max(snapshot["hypotheses"], key=lambda row: row["probability"])
        recommendation = {
            "action": "add",
            "intervention_id": None,
            "name": "Regular wake time",
            "category": "lifestyle",
            "hypothesis_id": top["id"],
            "rationale": f"A low-burden daily rhythm check for the working hypothesis “{top['title']}”.",
            "what_to_watch": "For seven days, notice energy and the symptom you care about most.",
            "safety_note": "Stop this experiment if it clearly makes you worse.",
            "dose": "",
        }
    else:
        recommendation = {
            "action": "hold",
            "intervention_id": None,
            "name": "",
            "category": None,
            "hypothesis_id": None,
            "rationale": "There is not enough in the record to justify a change this week.",
            "what_to_watch": "Add a hypothesis or note how an intervention feels before the next review.",
            "safety_note": "",
            "dose": "",
        }
    return {"hypothesis_updates": updates, "recommendation": recommendation}


def build_snapshot(db: Session) -> dict:
    hypotheses = list(
        db.scalars(select(Hypothesis).options(selectinload(Hypothesis.evidence)).order_by(Hypothesis.id)).all()
    )
    evidence = list(db.scalars(select(Evidence).order_by(Evidence.id)).all())
    interventions = list(
        db.scalars(select(Intervention).options(selectinload(Intervention.hypotheses)).order_by(Intervention.id)).all()
    )
    papers = list(
        db.scalars(
            select(ResearchItem)
            .options(selectinload(ResearchItem.hypotheses), selectinload(ResearchItem.interventions))
            .order_by(ResearchItem.id)
        ).all()
    )
    return {
        "hypotheses": [
            {
                "id": item.id,
                "title": item.title,
                "statement": item.statement,
                "domains": item.domains or [],
                "status": item.status,
                "probability": item.probability,
                "why_moved": item.why_moved,
            }
            for item in hypotheses
        ],
        "evidence": [
            {
                "id": item.id,
                "text": item.text,
                "direction": item.direction,
                "strength": item.strength,
                "hypothesis_id": item.hypothesis_id,
            }
            for item in evidence
        ],
        "interventions": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "dose": item.dose or "",
                "schedule": item.schedule or "",
                "clinician_prescribed": item.clinician_prescribed,
                "status": item.status,
                "benefit": item.benefit,
                "side_effect_burden": item.side_effect_burden,
                "side_effect_notes": item.side_effect_notes or "",
                "hypothesis_ids": [h.id for h in item.hypotheses],
            }
            for item in interventions
        ],
        "papers": [
            {
                "id": item.id,
                "title": item.title,
                "journal": item.journal,
                "year": item.year,
                "pdf_url": item.pdf_url,
                "excerpt": (item.excerpt or "")[:1500],
                "relevance_note": item.relevance_note,
                "hypothesis_ids": [h.id for h in item.hypotheses],
            }
            for item in papers
        ],
    }


def maybe_attach_research(db: Session, snapshot: dict) -> dict:
    active = [row for row in snapshot["hypotheses"] if row["status"] == "active"]
    if not active:
        return snapshot
    leading = max(active, key=lambda row: row["probability"])
    linked = [row for row in snapshot["papers"] if leading["id"] in row["hypothesis_ids"]]
    if linked:
        return snapshot
    settings = get_settings()
    if not settings.mosaiva_research_fixture and os.environ.get("MOSAIVA_DISABLE_LIVE_SEARCH") == "1":
        return snapshot
    from app.services.research import search_and_store

    try:
        search_and_store(
            db,
            query=leading["title"],
            hypothesis_ids=[leading["id"]],
            limit=5,
            keep=3,
        )
    except Exception:
        return snapshot
    return build_snapshot(db)


def apply_probability_updates(db: Session, validated: dict) -> dict:
    previous = {
        row.id: row.probability
        for row in db.scalars(select(Hypothesis).where(Hypothesis.id.in_(
            [item["hypothesis_id"] for item in validated["hypothesis_updates"]] or [-1]
        ))).all()
    }
    updates = []
    for item in validated["hypothesis_updates"]:
        hypothesis = db.get(Hypothesis, item["hypothesis_id"])
        if hypothesis is None:
            continue
        before = previous.get(hypothesis.id, hypothesis.probability)
        hypothesis.probability = item["probability"]
        hypothesis.why_moved = item["rationale"]
        hypothesis.updated_at = datetime.now().astimezone()
        stored = dict(item)
        stored["previous_probability"] = before
        updates.append(stored)
    validated["hypothesis_updates"] = updates
    return validated


def create_review(db: Session, settings: SettingsRow, reasoner, now: datetime | None = None) -> MosaicReview:
    snapshot = maybe_attach_research(db, build_snapshot(db))
    raw = reasoner(snapshot)
    validated = validate_review(snapshot, raw)
    validated = apply_probability_updates(db, validated)
    review = MosaicReview(
        week_start=week_start(settings.timezone, now),
        hypothesis_updates=validated["hypothesis_updates"],
        recommendation=validated["recommendation"],
        status="proposed",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def apply_decision(db: Session, review: MosaicReview, settings: SettingsRow, body) -> MosaicReview:
    if review.status != "proposed":
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="This week's review has already been decided.")
    if body.decision == "dismiss":
        review.status = "dismissed"
        db.commit()
        db.refresh(review)
        return review

    recommendation = dict(review.recommendation or {})
    if body.name is not None:
        recommendation["name"] = body.name.strip()
    if body.safety_note is not None:
        recommendation["safety_note"] = body.safety_note
    if body.rationale is not None:
        recommendation["rationale"] = body.rationale
    action = recommendation.get("action")
    category = recommendation.get("category")
    if action == "add" and category == "medication" and str(recommendation.get("dose") or "").strip():
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="A medication suggestion cannot include a dose.")
    if action == "add" and category == "medication":
        note = str(recommendation.get("safety_note") or "").lower()
        if "clinician" not in note or not str(recommendation.get("name") or "").strip():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail="A medication suggestion must name the medicine and tell the patient to ask a clinician.",
            )

    if action == "add":
        status = "ask_clinician" if category == "medication" else "paused"
        intervention = Intervention(
            name=str(recommendation.get("name") or "").strip(),
            category=category,
            dose="" if category == "medication" else str(recommendation.get("dose") or ""),
            clinician_prescribed=False,
            status=status,
            side_effect_notes=str(recommendation.get("safety_note") or ""),
        )
        hypothesis_id = recommendation.get("hypothesis_id")
        if hypothesis_id:
            hypothesis = db.get(Hypothesis, hypothesis_id)
            if hypothesis is not None:
                intervention.hypotheses = [hypothesis]
        db.add(intervention)
    elif action == "remove":
        intervention = db.get(Intervention, recommendation.get("intervention_id"))
        if intervention is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="That intervention is no longer in the record.")
        if intervention.clinician_prescribed:
            note = str(recommendation.get("safety_note") or "")
            if "clinician" not in note.lower():
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=422,
                    detail="Stopping a prescribed medicine must be framed as a clinician discussion.",
                )
            intervention.clinician_task = note
        else:
            intervention.status = "stopped"
            intervention.stop_date = local_today(settings.timezone)

    review.recommendation = recommendation
    flag_modified(review, "recommendation")
    review.status = "accepted"
    db.commit()
    db.refresh(review)
    return review
