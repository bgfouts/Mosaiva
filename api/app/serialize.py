from app.models import Capture, CoachSession, Evidence, Hypothesis, Intervention, MosaicReview, ResearchItem, SettingsRow


def evidence_dict(item: Evidence) -> dict:
    return {
        "id": item.id,
        "text": item.text,
        "direction": item.direction,
        "strength": item.strength,
        "hypothesis_id": item.hypothesis_id,
        "session_id": item.session_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def hypothesis_dict(item: Hypothesis) -> dict:
    evidence = sorted(item.evidence or [], key=lambda row: row.created_at or 0)
    return {
        "id": item.id,
        "title": item.title,
        "statement": item.statement,
        "why_it_fits": item.why_it_fits or "",
        "confidence": item.confidence or "",
        "likely_role": item.likely_role or "",
        "position": item.position or 0,
        "domains": item.domains or [],
        "status": item.status,
        "probability": item.probability,
        "why_moved": item.why_moved,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "evidence": [evidence_dict(row) for row in evidence],
    }


def intervention_dict(item: Intervention) -> dict:
    benefit = item.benefit
    burden = item.side_effect_burden
    net = None if benefit is None or burden is None else benefit - burden
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "dose": item.dose or "",
        "schedule": item.schedule or "",
        "clinician_prescribed": item.clinician_prescribed,
        "status": item.status,
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "stop_date": item.stop_date.isoformat() if item.stop_date else None,
        "benefit": benefit,
        "side_effect_burden": burden,
        "net_value": net,
        "side_effect_notes": item.side_effect_notes or "",
        "clinician_task": item.clinician_task or "",
        "hypothesis_ids": [h.id for h in item.hypotheses],
        "hypotheses": [{"id": h.id, "title": h.title} for h in item.hypotheses],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def research_dict(item: ResearchItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "journal": item.journal,
        "year": item.year,
        "pdf_url": item.pdf_url,
        "excerpt": item.excerpt,
        "query": item.query,
        "relevance_note": item.relevance_note,
        "hypothesis_ids": [h.id for h in item.hypotheses],
        "intervention_ids": [i.id for i in item.interventions],
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def capture_dict(item: Capture) -> dict:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "tool_name": item.tool_name,
        "payload": item.payload or {},
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def session_dict(item: CoachSession) -> dict:
    captures = sorted(item.captures or [], key=lambda row: row.created_at or 0)
    return {
        "id": item.id,
        "status": item.status,
        "transcript": item.transcript or [],
        "urgent": item.urgent,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "captures": [capture_dict(row) for row in captures],
    }


def review_dict(item: MosaicReview, titles: dict[int, str] | None = None) -> dict:
    updates = []
    for row in item.hypothesis_updates or []:
        copied = dict(row)
        if titles is not None:
            copied["title"] = titles.get(copied.get("hypothesis_id"))
        updates.append(copied)
    return {
        "id": item.id,
        "week_start": item.week_start.isoformat(),
        "status": item.status,
        "hypothesis_updates": updates,
        "recommendation": item.recommendation or {},
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def settings_dict(item: SettingsRow) -> dict:
    return {"timezone": item.timezone, "display_name": item.display_name}
