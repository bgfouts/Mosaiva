import json

from pypdf import PdfWriter


def _write_pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)


def test_voice_session_without_a_key_is_an_error(client):
    response = client.post("/api/coach/session")
    assert response.status_code == 503
    assert "text fallback" in response.json()["detail"].lower()


def test_gpt_live_session_uses_terra_for_tools():
    from app.services.coach import live_session_request

    request = live_session_request("v=0\r\n", "Record what the patient says.", "gpt-live-1", "gpt-5.6-terra")
    assert request["session"]["model"] == "gpt-live-1"
    assert request["transport"] == {"type": "webrtc", "sdp": "v=0\r\n"}
    backend = request["session"]["delegation"]["responses"]
    assert backend["model"] == "gpt-5.6-terra"
    assert backend["tool_choice"] == "auto"
    names = {tool["name"] for tool in backend["tools"]}
    assert "record_observation" in names
    assert "flag_urgent" in names


def test_terra_response_text_is_read_from_output_items():
    from app.services.llm import response_output_text, responses_request

    body = responses_request("gpt-5.6-terra", "Return JSON.", {"question": "why"})
    assert body["model"] == "gpt-5.6-terra"
    assert body["text"]["format"]["type"] == "json_object"
    text = response_output_text(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"relevance_note":"Related."}'}],
                }
            ]
        }
    )
    assert "relevance_note" in text


def test_pending_capture_commits_only_after_confirmation(client):
    from app.db import SessionLocal
    from app.models import CoachSession

    assert SessionLocal is not None
    db = SessionLocal()
    session = CoachSession(status="active", transcript=[], urgent=False)
    db.add(session)
    db.commit()
    session_id = session.id
    db.close()

    event = client.post(
        f"/api/coach/sessions/{session_id}/events",
        json={
            "kind": "tool",
            "tool_name": "propose_hypothesis",
            "payload": {"title": "Orthostatic intolerance", "statement": "Standing sets off the symptoms.", "probability": 0.4},
        },
    )
    assert event.status_code == 200
    capture = event.json()["capture"]
    assert capture["status"] == "pending"
    assert client.get("/api/hypotheses").json() == []

    committed = client.post(f"/api/coach/captures/{capture['id']}/commit")
    assert committed.status_code == 200
    assert committed.json()["status"] == "committed"
    rows = client.get("/api/hypotheses").json()
    assert rows[0]["title"] == "Orthostatic intolerance"
    assert rows[0]["probability"] == 0.4


def test_research_search_keeps_an_allowed_fixture_pdf(client, tmp_path, monkeypatch):
    pdf_path = tmp_path / "sleep.pdf"
    _write_pdf(pdf_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "hits": [
                    {
                        "title": "Sleep restriction therapy review",
                        "journal": "BMJ",
                        "year": 2019,
                        "url": "https://www.bmj.com/content/open-access/sleep-restriction.pdf",
                        "pdf_file": "sleep.pdf",
                    },
                    {
                        "title": "Pirate copy",
                        "url": "https://sci-hub.se/paper.pdf",
                        "pdf_file": "sleep.pdf",
                    },
                    {
                        "title": "Blog pdf",
                        "url": "https://random-blog.example/note.pdf",
                        "pdf_file": "sleep.pdf",
                    },
                ]
            }
        )
    )
    monkeypatch.setenv("MOSAIVA_RESEARCH_FIXTURE", str(fixture))
    from app.settings import get_settings

    get_settings.cache_clear()
    hypothesis = client.post("/api/hypotheses", json={"title": "Fragmented sleep"}).json()
    result = client.post(
        "/api/research/search",
        json={"query": "sleep restriction", "hypothesis_ids": [hypothesis["id"]]},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["kept"] == 1
    assert body["items"][0]["journal"] == "BMJ"
    assert body["items"][0]["hypothesis_ids"] == [hypothesis["id"]]
    assert "sci-hub" not in body["items"][0]["pdf_url"]
