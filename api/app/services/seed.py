import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Hypothesis, Intervention, ResearchItem, utcnow
from app.services.records import assert_intervention_rules, confidence_to_probability
from app.settings import PAPERS_DIR, get_settings

THEORIES_PATH = Path(__file__).resolve().parent.parent / "data" / "health_theories.json"
INTERVENTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "potential_interventions.json"
SEED_PAPERS_DIR = Path(__file__).resolve().parent.parent / "data" / "seed_papers"
SEED_PAPERS_MANIFEST = SEED_PAPERS_DIR / "manifest.json"

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


def load_potential_interventions() -> list[dict]:
    return json.loads(INTERVENTIONS_PATH.read_text(encoding="utf-8"))


def seed_interventions(db: Session) -> int:
    if not get_settings().mosaiva_seed_interventions:
        return 0
    items = load_potential_interventions()
    existing = set(db.scalars(select(Intervention.name)).all())
    hypotheses = {row.title: row for row in db.scalars(select(Hypothesis)).all()}
    added = 0
    for index, item in enumerate(items, start=1):
        name = str(item["name"]).strip()
        if name in existing:
            continue
        row = Intervention(
            name=name,
            category=str(item["category"]),
            dose="",
            schedule=str(item.get("schedule") or "").strip(),
            clinician_prescribed=bool(item.get("clinician_prescribed") or False),
            status=str(item.get("status") or "potential"),
            side_effect_notes=str(item.get("side_effect_notes") or "").strip(),
            clinician_task=str(item.get("clinician_task") or "").strip(),
            position=index,
        )
        linked = [
            hypotheses[title]
            for title in item.get("hypothesis_titles") or []
            if title in hypotheses
        ]
        row.hypotheses = linked
        assert_intervention_rules(row)
        db.add(row)
        existing.add(name)
        added += 1
    if added:
        db.commit()
    return added


def load_seed_papers() -> list[dict]:
    return json.loads(SEED_PAPERS_MANIFEST.read_text(encoding="utf-8"))


def seed_research(db: Session) -> int:
    if not get_settings().mosaiva_seed_research:
        return 0
    from app.services.research import assess_candidate, extract_pdf_text

    papers = load_seed_papers()
    existing_titles = set(db.scalars(select(ResearchItem.title)).all())
    existing_urls = set(db.scalars(select(ResearchItem.pdf_url)).all())
    hypotheses = {row.title: row for row in db.scalars(select(Hypothesis)).all()}
    interventions = {row.name: row for row in db.scalars(select(Intervention)).all()}
    added = 0
    stamped = utcnow()
    for index, paper in enumerate(papers):
        title = str(paper["title"]).strip()
        url = str(paper["pdf_url"]).strip()
        if title in existing_titles or url in existing_urls:
            continue
        body = (SEED_PAPERS_DIR / str(paper["file"])).read_bytes()
        reason = assess_candidate(url, "application/pdf", body)
        if reason:
            raise RuntimeError(f"Seed paper {paper.get('pmcid')} was rejected: {reason}")
        PAPERS_DIR.mkdir(parents=True, exist_ok=True)
        path = PAPERS_DIR / f"seed-{paper['pmcid']}.pdf"
        path.write_bytes(body)
        try:
            excerpt = extract_pdf_text(path)
        except Exception:
            excerpt = ""
        item = ResearchItem(
            title=title[:500],
            journal=str(paper.get("journal") or "")[:200],
            year=int(paper["year"]) if paper.get("year") is not None else None,
            pdf_url=url,
            local_path=str(path),
            excerpt=excerpt,
            query=f"seed:{paper['pmcid']}",
            relevance_note=str(paper.get("relevance_note") or "").strip(),
            created_at=stamped + timedelta(seconds=len(papers) - index),
        )
        item.hypotheses = [hypotheses[name] for name in paper.get("hypothesis_titles") or [] if name in hypotheses]
        item.interventions = [
            interventions[name] for name in paper.get("intervention_names") or [] if name in interventions
        ]
        db.add(item)
        existing_titles.add(title)
        existing_urls.add(url)
        added += 1
    if added:
        db.commit()
    return added
