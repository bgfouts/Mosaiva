import json

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture, CoachSession, Evidence, Hypothesis, Intervention
from app.services.records import (
    assert_intervention_rules,
    clamp_probability,
    confidence_to_probability,
    next_hypothesis_position,
)
from app.settings import get_settings

URGENT_MESSAGE = (
    "This may need urgent care. Contact emergency services or your clinician now. "
    "Mosaiva cannot assess emergencies."
)

COACH_TOOLS = [
    {
        "type": "function",
        "name": "record_observation",
        "description": "Save a symptom or observation the patient described. It stays pending until they confirm.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "direction": {"type": "string", "enum": ["supports", "contradicts"]},
                "strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
                "hypothesis_id": {"type": ["integer", "null"]},
            },
            "required": ["text", "direction", "strength"],
        },
    },
    {
        "type": "function",
        "name": "log_checkin",
        "description": "Update benefit and side-effect burden for an intervention the patient is already using. Pending until they confirm.",
        "parameters": {
            "type": "object",
            "properties": {
                "intervention_id": {"type": "integer"},
                "benefit": {"type": "integer"},
                "side_effect_burden": {"type": "integer"},
                "notes": {"type": "string"},
            },
            "required": ["intervention_id", "benefit", "side_effect_burden"],
        },
    },
    {
        "type": "function",
        "name": "propose_hypothesis",
        "description": "Propose a new working hypothesis. It is not a diagnosis and stays pending until the patient confirms. Use a qualitative confidence label and a likely role, not a diagnosis.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "statement": {"type": "string"},
                "why_it_fits": {"type": "string"},
                "confidence": {"type": "string"},
                "likely_role": {"type": "string"},
                "domains": {"type": "array", "items": {"type": "string"}},
                "probability": {"type": "number"},
            },
            "required": ["title"],
        },
    },
    {
        "type": "function",
        "name": "propose_intervention",
        "description": "Propose a lifestyle, diet, or supplement change, or name a medicine to ask a clinician about. Never include a dose for a medicine. Pending until the patient confirms.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["medication", "lifestyle", "diet", "supplement", "therapy"],
                },
                "dose": {"type": "string"},
                "clinician_prescribed": {"type": "boolean"},
                "hypothesis_id": {"type": ["integer", "null"]},
            },
            "required": ["name", "category"],
        },
    },
    {
        "type": "function",
        "name": "flag_urgent",
        "description": "Call this immediately for chest pain, trouble breathing, fainting, suicidal thoughts, or rapidly worsening neurological symptoms.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
    },
    {
        "type": "function",
        "name": "confirm_latest_capture",
        "description": "Commit the newest pending capture only after the patient clearly says yes.",
        "parameters": {"type": "object", "properties": {}},
    },
]


LIVE_STYLE = """
You are the Mosaiva voice coach. Speak in short, plain sentences. This is voice only.
You do not diagnose, prescribe, or give doses.
Delegate to the backend when you need to record an observation, log how an intervention feels, propose a hypothesis or intervention, confirm a save, or flag an emergency.
Ask for a clear spoken yes before confirming a save. The patient can also confirm on screen.
If they mention chest pain, trouble breathing, fainting, suicidal thoughts, or rapidly worsening neurological symptoms, delegate flag_urgent immediately and stop coaching.
""".strip()


def _strict_tools() -> list[dict]:
    tools = []
    for tool in COACH_TOOLS:
        parameters = dict(tool["parameters"])
        parameters["additionalProperties"] = False
        tools.append({**tool, "parameters": parameters})
    return tools


def live_session_request(sdp: str, backend_instructions: str, live_model: str, reasoning_model: str) -> dict:
    return {
        "session": {
            "model": live_model,
            "instructions": LIVE_STYLE,
            "audio": {"output": {"voice": "marin"}},
            "delegation": {
                "type": "responses",
                "responses": {
                    "model": reasoning_model,
                    "instructions": backend_instructions,
                    "tools": _strict_tools(),
                    "tool_choice": "auto",
                },
            },
        },
        "transport": {"type": "webrtc", "sdp": sdp},
    }


def coach_instructions(db: Session) -> str:
    hypotheses = list(
        db.scalars(select(Hypothesis).order_by(Hypothesis.position.asc(), Hypothesis.id.asc())).all()
    )
    interventions = list(db.scalars(select(Intervention).order_by(Intervention.id)).all())
    hypothesis_lines = [
        (
            f"- id {item.id}: {item.title} — confidence {item.confidence or 'unset'}; "
            f"likely role {item.likely_role or 'unset'} "
            f"(internal estimate {item.probability:.0%}, {item.status})"
        )
        for item in hypotheses
    ] or ["- none yet"]
    intervention_lines = [
        f"- id {item.id}: {item.name} [{item.category}] status {item.status}, prescribed {item.clinician_prescribed}"
        for item in interventions
    ] or ["- none yet"]
    return f"""
You are the Mosaiva voice coach for one patient with a complicated, uncertain health picture.
Speak in plain spoken language. This is voice only.
You coach and gather history. You do not diagnose, prescribe, or give doses.
Hypotheses are working ideas, never diagnoses. Say that when you propose one.
If the patient mentions chest pain, trouble breathing, fainting, suicidal thoughts, or rapidly worsening neurological symptoms, call flag_urgent and stop coaching.
Use tools to record what you hear. Every tool except flag_urgent and confirm_latest_capture stays pending until the patient confirms.
After a tool call, ask for a clear spoken yes, then call confirm_latest_capture. They can also confirm on screen.
Never tell the patient to start or stop a medicine on their own. A medicine they are not taking can only be named as something to ask a clinician about, with no dose.
Prefer questions about timing, what they have already tried, what helped, and what caused side effects.

Working hypotheses:
{chr(10).join(hypothesis_lines)}

Interventions:
{chr(10).join(intervention_lines)}
""".strip()


def missing_key_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Voice coaching needs an OpenAI API key on this machine. There is no text fallback.",
    )


def create_live_session(db: Session, sdp: str) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        raise missing_key_error()
    request_body = live_session_request(
        sdp,
        coach_instructions(db),
        settings.openai_live_model,
        settings.openai_reasoning_model,
    )
    try:
        response = httpx.post(
            "https://api.openai.com/v1/live/sessions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=45,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="GPT-Live could not be reached.") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="GPT-Live could not be started.")
    body = response.json()
    answer = (body.get("transport") or {}).get("sdp")
    live_id = (body.get("session") or {}).get("id")
    if not answer:
        raise HTTPException(status_code=502, detail="GPT-Live did not return a connection answer.")
    session = CoachSession(status="active", transcript=[], urgent=False)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "live_session_id": live_id,
        "transport": {"type": "webrtc", "sdp": answer},
        "model": settings.openai_live_model,
    }


def append_event(db: Session, session: CoachSession, event) -> dict:
    urgent = False
    capture = None
    if event.kind == "transcript":
        if event.text is None or not event.role:
            raise HTTPException(status_code=422, detail="A transcript line needs a role and text.")
        transcript = [dict(line) for line in (session.transcript or [])]
        if transcript and transcript[-1].get("role") == event.role:
            transcript[-1]["text"] = f"{transcript[-1].get('text', '')}{event.text}"
        else:
            transcript.append({"role": event.role, "text": event.text})
        session.transcript = transcript
    elif event.kind == "tool":
        if not event.tool_name:
            raise HTTPException(status_code=422, detail="A tool event needs a tool name.")
        payload = event.payload or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        if event.tool_name == "confirm_latest_capture":
            capture = _latest_pending(db, session.id)
            if capture is None:
                raise HTTPException(status_code=404, detail="There is no pending capture to confirm.")
            commit_capture(db, capture)
            db.refresh(session)
            return {"capture": capture, "urgent": session.urgent, "urgent_message": URGENT_MESSAGE if session.urgent else None}
        if event.tool_name == "flag_urgent":
            session.urgent = True
            session.status = "urgent"
            urgent = True
            capture = Capture(
                session_id=session.id,
                tool_name="flag_urgent",
                payload={"reason": str(payload.get("reason") or ""), "message": URGENT_MESSAGE},
                status="committed",
            )
            db.add(capture)
        else:
            _validate_tool_payload(event.tool_name, payload)
            capture = Capture(
                session_id=session.id,
                tool_name=event.tool_name,
                payload=payload,
                status="pending",
            )
            db.add(capture)
    else:
        raise HTTPException(status_code=422, detail="Unknown event kind.")
    db.commit()
    if capture is not None:
        db.refresh(capture)
    db.refresh(session)
    return {
        "capture": capture,
        "urgent": urgent or session.urgent,
        "urgent_message": URGENT_MESSAGE if (urgent or session.urgent) else None,
    }


def _validate_tool_payload(tool_name: str, payload: dict) -> None:
    if tool_name == "record_observation":
        if not str(payload.get("text") or "").strip():
            raise HTTPException(status_code=422, detail="An observation needs text.")
        if payload.get("direction") not in {"supports", "contradicts"}:
            raise HTTPException(status_code=422, detail="Direction must support or contradict a hypothesis.")
        if payload.get("strength") not in {"weak", "moderate", "strong"}:
            raise HTTPException(status_code=422, detail="Strength must be weak, moderate, or strong.")
    elif tool_name == "log_checkin":
        for key in ("benefit", "side_effect_burden"):
            value = payload.get(key)
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise HTTPException(status_code=422, detail="Benefit and side-effect burden must be from 1 to 5.")
    elif tool_name == "propose_hypothesis":
        if not str(payload.get("title") or "").strip():
            raise HTTPException(status_code=422, detail="A hypothesis needs a title.")
    elif tool_name == "propose_intervention":
        if payload.get("category") not in {"medication", "lifestyle", "diet", "supplement", "therapy"}:
            raise HTTPException(status_code=422, detail="Unknown intervention category.")
        if not str(payload.get("name") or "").strip():
            raise HTTPException(status_code=422, detail="An intervention needs a name.")
        if payload.get("category") == "medication" and str(payload.get("dose") or "").strip():
            raise HTTPException(status_code=422, detail="A medicine to ask about cannot include a dose.")
    else:
        raise HTTPException(status_code=422, detail="Unknown tool.")


def _latest_pending(db: Session, session_id: int) -> Capture | None:
    return db.scalar(
        select(Capture)
        .where(Capture.session_id == session_id, Capture.status == "pending")
        .order_by(Capture.id.desc())
    )


def commit_capture(db: Session, capture: Capture) -> Capture:
    if capture.status != "pending":
        raise HTTPException(status_code=409, detail="This capture is no longer pending.")
    payload = capture.payload or {}
    if capture.tool_name == "record_observation":
        hypothesis_id = payload.get("hypothesis_id")
        if hypothesis_id is not None and db.get(Hypothesis, hypothesis_id) is None:
            raise HTTPException(status_code=422, detail="That hypothesis is not in the record.")
        db.add(
            Evidence(
                text=str(payload["text"]).strip(),
                direction=payload["direction"],
                strength=payload["strength"],
                hypothesis_id=hypothesis_id,
                session_id=capture.session_id,
            )
        )
    elif capture.tool_name == "log_checkin":
        intervention = db.get(Intervention, payload.get("intervention_id"))
        if intervention is None:
            raise HTTPException(status_code=422, detail="That intervention is not in the record.")
        intervention.benefit = int(payload["benefit"])
        intervention.side_effect_burden = int(payload["side_effect_burden"])
        notes = str(payload.get("notes") or "").strip()
        if notes:
            intervention.side_effect_notes = notes
    elif capture.tool_name == "propose_hypothesis":
        confidence = str(payload.get("confidence") or "").strip()
        raw_probability = payload.get("probability")
        if raw_probability is None or raw_probability == "":
            probability = confidence_to_probability(confidence) if confidence else 0.5
        else:
            try:
                probability = float(raw_probability)
            except (TypeError, ValueError):
                probability = 0.5
        db.add(
            Hypothesis(
                title=str(payload["title"]).strip(),
                statement=str(payload.get("statement") or ""),
                why_it_fits=str(payload.get("why_it_fits") or "").strip(),
                confidence=confidence,
                likely_role=str(payload.get("likely_role") or "").strip(),
                position=next_hypothesis_position(db),
                domains=list(payload.get("domains") or []),
                status="active",
                probability=clamp_probability(probability),
            )
        )
    elif capture.tool_name == "propose_intervention":
        category = payload["category"]
        status = "ask_clinician" if category == "medication" else "paused"
        intervention = Intervention(
            name=str(payload["name"]).strip(),
            category=category,
            dose="" if category == "medication" else str(payload.get("dose") or ""),
            clinician_prescribed=bool(payload.get("clinician_prescribed") or False) and category != "medication",
            status=status,
        )
        if category == "medication":
            intervention.clinician_prescribed = False
            intervention.side_effect_notes = "Ask your clinician before starting this. Do not start it on your own."
        hypothesis_id = payload.get("hypothesis_id")
        if hypothesis_id is not None:
            hypothesis = db.get(Hypothesis, hypothesis_id)
            if hypothesis is not None:
                intervention.hypotheses = [hypothesis]
        assert_intervention_rules(intervention)
        db.add(intervention)
    else:
        raise HTTPException(status_code=422, detail="This capture cannot be committed.")
    capture.status = "committed"
    db.commit()
    db.refresh(capture)
    return capture


def discard_capture(db: Session, capture: Capture) -> Capture:
    if capture.status != "pending":
        raise HTTPException(status_code=409, detail="This capture is no longer pending.")
    capture.status = "discarded"
    db.commit()
    db.refresh(capture)
    return capture
