import json
import threading
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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
Wait for the instruction to speak first. Then ask how they are doing today and listen.
If that instruction says so, next ask how they have been since the last time you talked.
Ask clinical questions only after that check-in, one at a time. They are not diagnoses.
After 5 to 7 replies from the patient, say goodbye and say that is all you need for today.
Delegate to the backend when you need to record an observation, log how an intervention feels, propose a hypothesis or intervention, confirm a save, or flag an emergency.
Ask for a clear spoken yes before confirming a save. The patient can also confirm on screen.
If they mention chest pain, trouble breathing, fainting, suicidal thoughts, or rapidly worsening neurological symptoms, delegate flag_urgent immediately and stop coaching.

Backchannel policy: Use moderate backchannels. Acknowledge naturally without competing with the main response.

Interruption policy: Stop speaking when the user interrupts. Listen to what they say.

Delegation policy:
Backend tools:
- Record: save an observation, a check-in, or a proposed hypothesis or intervention for the patient to confirm.
- Urgent: flag chest pain, trouble breathing, fainting, suicidal thoughts, or rapidly worsening neurological symptoms.

Delegate to the backend when:
- The patient described something that should be saved, or clearly confirmed a save.
- They mention an emergency symptom.

Do not delegate to the backend when:
- You are only greeting them or asking how they are.
- You can ask the next short question from context you already have.

Delegate before claiming something was saved.
Do not guess the result while waiting.
""".strip()

MIN_VISIT_TURNS = 5
MAX_VISIT_TURNS = 7


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


def greeting_instruction(ask_since_last: bool) -> str:
    since = ""
    if ask_since_last:
        since = (
            " After they answer, ask how they have been since the last time you talked. Then wait again."
        )
    return (
        "Speak English. Speak first now, then listen. "
        "Ask how they are doing today, in one short question."
        f"{since} "
        "Do not ask a clinical question until those check-ins are answered. "
        "Questions may arrive in the background while you listen. Use them only after the check-in, one at a time. "
        "They are not diagnoses. Do not give a dose or tell them to start, stop, or change a medicine. "
        "After they have replied 5 to 7 times, say goodbye. Say that is all you need for today. "
        "Do not add another question in the goodbye."
    )


def cue_instruction(cue: str | None, turns: int) -> str:
    if cue == "goodbye" or turns >= MAX_VISIT_TURNS:
        return (
            "Stop. Say goodbye now in one or two sentences. "
            "Say that is all you need for today. Do not ask another question."
        )
    if cue == "wind_down":
        return (
            f"They have replied {turns} times. You may ask one last useful question, or say goodbye now. "
            "By 7 replies you must stop. When you say goodbye, say that is all you need for today."
        )
    return ""


def visit_cue(turns: int) -> str | None:
    if turns >= MAX_VISIT_TURNS:
        return "goodbye"
    if turns >= MIN_VISIT_TURNS:
        return "wind_down"
    return None


def patient_turn_count(transcript: list) -> int:
    return sum(
        1
        for line in transcript or []
        if line.get("role") == "patient" and str(line.get("text") or "").strip()
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def last_patient_checkin(db: Session) -> datetime | None:
    sessions = db.scalars(select(CoachSession).order_by(CoachSession.id.desc())).all()
    for session in sessions:
        if patient_turn_count(session.transcript or []):
            return session.created_at
    return None


def ask_since_last_checkin(db: Session, now: datetime | None = None) -> bool:
    moment = last_patient_checkin(db)
    if moment is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current - _as_utc(moment) > timedelta(days=1)


def questions_context(questions: list[str]) -> str:
    if not questions:
        return ""
    lines = "\n".join(f"- {question}" for question in questions)
    return (
        "Clinically useful questions to ask after the check-in, one at a time, and only while the visit is still open. "
        "Do not read this list aloud.\n"
        f"{lines}"
    )


def visit_state(session: CoachSession) -> dict:
    turns = patient_turn_count(session.transcript or [])
    cue = visit_cue(turns)
    raw_questions = session.planned_questions or []
    if isinstance(raw_questions, str):
        try:
            raw_questions = json.loads(raw_questions)
        except json.JSONDecodeError:
            raw_questions = []
    questions = [str(question) for question in raw_questions if str(question).strip()]
    ready = session.plan_status == "ready"
    return {
        "ask_since_last": bool(session.ask_since_last),
        "greeting": greeting_instruction(bool(session.ask_since_last)),
        "patient_turns": turns,
        "cue": cue,
        "cue_text": cue_instruction(cue, turns),
        "plan_status": session.plan_status or "pending",
        "questions": questions,
        "questions_context": questions_context(questions) if ready else "",
    }


def _usable_question(text: str) -> bool:
    cleaned = " ".join(text.split())
    if not cleaned:
        return False
    lowered = cleaned.lower()
    blocked = ("mg", "milligram", "dosage", "dose")
    return not any(word in lowered for word in blocked)


def fixture_questions(db: Session) -> list[str]:
    hypotheses = list(
        db.scalars(
            select(Hypothesis)
            .options(selectinload(Hypothesis.evidence))
            .order_by(Hypothesis.position.asc(), Hypothesis.id.asc())
        ).all()
    )
    questions: list[str] = []
    for item in hypotheses:
        if item.status != "active" or item.evidence:
            continue
        questions.append(f"What have you noticed lately that seems to come with {item.title}?")
        if len(questions) == 3:
            break
    interventions = list(db.scalars(select(Intervention).order_by(Intervention.position.asc(), Intervention.id.asc())).all())
    for item in interventions:
        if item.status == "potential" and item.category != "medication":
            questions.append(f"Have you already tried {item.name}, or is that still only an idea?")
            break
    if not questions:
        questions.append("What feels most different today from a usual day?")
    return [question for question in questions if _usable_question(question)][:4]


def terra_questions(db: Session) -> list[str]:
    from app.services.llm import OpenAIReasoner

    payload = {
        "hypotheses": [
            {
                "title": item.title,
                "confidence": item.confidence,
                "likely_role": item.likely_role,
                "status": item.status,
            }
            for item in db.scalars(select(Hypothesis).order_by(Hypothesis.position.asc())).all()
        ],
        "interventions": [
            {"name": item.name, "category": item.category, "status": item.status}
            for item in db.scalars(select(Intervention).order_by(Intervention.position.asc())).all()
        ],
    }
    raw = OpenAIReasoner().complete_json(
        (
            "Prepare spoken questions for a wellness coach. Return JSON with a questions array of 3 or 4 short questions. "
            "Each question should help tell which working idea fits, or how a routine has felt. "
            "Do not diagnose. Do not include a dose. Do not tell the patient to start, stop, or change a medicine."
        ),
        payload,
    )
    questions = raw.get("questions") if isinstance(raw, dict) else None
    if not isinstance(questions, list):
        return []
    return [cleaned for question in questions if _usable_question(cleaned := " ".join(str(question).split()))][:4]


def build_question_plan(db: Session) -> list[str]:
    settings = get_settings()
    if settings.mosaiva_coach_plan_fixture or not settings.openai_api_key:
        return fixture_questions(db)
    try:
        planned = terra_questions(db)
    except (RuntimeError, json.JSONDecodeError, TypeError, ValueError):
        planned = []
    return planned or fixture_questions(db)


def plan_session_questions(session_id: int) -> None:
    from app.db import open_session

    db = open_session()
    try:
        session = db.get(CoachSession, session_id)
        if session is None:
            return
        session.planned_questions = build_question_plan(db)
        session.plan_status = "ready"
        db.commit()
    except Exception:
        db.rollback()
        session = db.get(CoachSession, session_id)
        if session is not None:
            session.planned_questions = fixture_questions(db)
            session.plan_status = "ready"
            db.commit()
    finally:
        db.close()


def start_question_plan(session_id: int) -> None:
    threading.Thread(
        target=plan_session_questions,
        args=(session_id,),
        name=f"coach-plan-{session_id}",
        daemon=True,
    ).start()


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
    session = CoachSession(
        status="active",
        transcript=[],
        urgent=False,
        ask_since_last=ask_since_last_checkin(db),
        plan_status="pending",
        planned_questions=[],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    start_question_plan(session.id)
    return {
        "session_id": session.id,
        "live_session_id": live_id,
        "transport": {"type": "webrtc", "sdp": answer},
        "model": settings.openai_live_model,
        "visit": visit_state(session),
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
            return {
                "capture": capture,
                "urgent": session.urgent,
                "urgent_message": URGENT_MESSAGE if session.urgent else None,
                "visit": visit_state(session),
            }
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
        "visit": visit_state(session),
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
