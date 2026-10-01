from datetime import datetime, timedelta, timezone

from app.db import open_session
from app.models import CoachSession
from app.services.coach import (
    ask_since_last_checkin,
    fixture_questions,
    greeting_instruction,
    plan_session_questions,
)


def _say(client, session_id, role, text):
    response = client.post(
        f"/api/coach/sessions/{session_id}/events",
        json={"kind": "transcript", "role": role, "text": text},
    )
    assert response.status_code == 200
    return response.json()["visit"]


def test_greeting_asks_about_today_before_the_gap():
    today_only = greeting_instruction(False).lower()
    assert "how they are doing today" in today_only
    assert "since the last time" not in today_only
    assert "all you need for today" in today_only

    with_gap = greeting_instruction(True).lower()
    assert with_gap.index("how they are doing today") < with_gap.index("since the last time")


def test_since_last_question_depends_on_the_last_patient_checkin(client):
    db = open_session()
    now = datetime.now(timezone.utc)
    db.add(
        CoachSession(
            transcript=[{"role": "patient", "text": "I was tired."}],
            created_at=now - timedelta(days=2),
        )
    )
    db.commit()
    assert ask_since_last_checkin(db, now) is True

    db.add(
        CoachSession(
            transcript=[{"role": "coach", "text": "Hello."}],
            created_at=now - timedelta(hours=1),
        )
    )
    db.commit()
    assert ask_since_last_checkin(db, now) is True

    db.add(
        CoachSession(
            transcript=[{"role": "patient", "text": "Better today."}],
            created_at=now - timedelta(hours=20),
        )
    )
    db.commit()
    assert ask_since_last_checkin(db, now) is False
    db.close()


def test_no_prior_checkin_skips_the_gap_question(client):
    db = open_session()
    assert ask_since_last_checkin(db) is False
    db.close()


def test_goodbye_cue_starts_at_five_replies_and_closes_at_seven(client):
    db = open_session()
    session = CoachSession(status="active", transcript=[], urgent=False)
    db.add(session)
    db.commit()
    session_id = session.id
    db.close()

    for number in range(1, 5):
        visit = _say(client, session_id, "patient", f"Reply {number}.")
        assert visit["patient_turns"] == number
        assert visit["cue"] is None
        _say(client, session_id, "coach", "Tell me a little more.")

    fifth = _say(client, session_id, "patient", "Reply 5.")
    assert fifth["cue"] == "wind_down"
    assert "all you need for today" in fifth["cue_text"].lower()
    continued = _say(client, session_id, "patient", " still talking")
    assert continued["patient_turns"] == 5
    assert continued["cue"] == "wind_down"

    _say(client, session_id, "coach", "One more.")
    sixth = _say(client, session_id, "patient", "Reply 6.")
    assert sixth["cue"] == "wind_down"
    _say(client, session_id, "coach", "Okay.")
    seventh = _say(client, session_id, "patient", "Reply 7.")
    assert seventh["patient_turns"] == 7
    assert seventh["cue"] == "goodbye"
    assert "do not ask another question" in seventh["cue_text"].lower()
    assert "all you need for today" in seventh["cue_text"].lower()


def test_background_plan_uses_fixture_questions_without_a_dose(client):
    client.post(
        "/api/hypotheses",
        json={"title": "Fragmented sleep", "confidence": "Moderate", "statement": "Wake-ups."},
    )
    db = open_session()
    session = CoachSession(status="active", transcript=[], urgent=False, plan_status="pending")
    db.add(session)
    db.commit()
    session_id = session.id
    questions = fixture_questions(db)
    db.close()
    assert questions
    assert all("dose" not in question.lower() and "mg" not in question.lower() for question in questions)
    assert any("Fragmented sleep" in question for question in questions)

    plan_session_questions(session_id)
    saved = client.get(f"/api/coach/sessions/{session_id}").json()
    assert saved["visit"]["plan_status"] == "ready"
    assert saved["visit"]["questions"]
    assert saved["visit"]["questions_context"]
    assert "do not read this list aloud" in saved["visit"]["questions_context"].lower()
