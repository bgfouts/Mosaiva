import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

CLIENT_ID = "test-client.apps.googleusercontent.com"
SECRET = "x" * 40


def _id_token(email: str, *, aud: str = CLIENT_ID, verified: bool = True) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {
        "iss": "https://accounts.google.com",
        "aud": aud,
        "exp": time.time() + 600,
        "email": email,
        "email_verified": verified,
    }
    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


@pytest.fixture()
def guarded(tmp_path, monkeypatch):
    monkeypatch.setenv("MOSAIVA_DATABASE_URL", f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MOSAIVA_SEED_HYPOTHESES", "0")
    monkeypatch.setenv("MOSAIVA_SEED_INTERVENTIONS", "0")
    monkeypatch.setenv("MOSAIVA_SEED_RESEARCH", "0")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("MOSAIVA_ALLOWED_EMAILS", "Patient@Example.com, partner@example.com")
    monkeypatch.setenv("MOSAIVA_SESSION_SECRET", SECRET)
    monkeypatch.setenv("MOSAIVA_PUBLIC_URL", "https://mosaiva.example")
    from app.db import reset_engine
    from app.settings import get_settings

    get_settings.cache_clear()
    reset_engine()
    from app.main import create_app

    with TestClient(create_app(), base_url="https://mosaiva.example") as client:
        yield client
    reset_engine()
    get_settings.cache_clear()


def _sign_in(client: TestClient, monkeypatch, email: str, **token_args):
    import app.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "exchange_code", lambda code, request: {"id_token": _id_token(email, **token_args)})
    started = client.get("/api/auth/login", follow_redirects=False)
    assert started.status_code == 303
    target = urlparse(started.headers["location"])
    assert target.netloc == "accounts.google.com"
    query = parse_qs(target.query)
    assert query["redirect_uri"] == ["https://mosaiva.example/api/auth/callback"]
    assert query["client_id"] == [CLIENT_ID]
    return client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": query["state"][0]},
        follow_redirects=False,
    )


def test_data_routes_need_a_signed_in_user(guarded):
    assert guarded.get("/api/health").status_code == 200
    assert guarded.get("/api/hypotheses").status_code == 401
    assert guarded.post("/api/hypotheses", json={"title": "x"}).status_code == 401
    assert guarded.get("/api/auth/me").status_code == 401


def test_allowed_email_signs_in_and_sees_the_record(guarded, monkeypatch):
    finished = _sign_in(guarded, monkeypatch, "partner@example.com")
    assert finished.status_code == 303
    assert finished.headers["location"] == "/"
    assert "mosaiva_session" in finished.cookies
    me = guarded.get("/api/auth/me")
    assert me.json() == {"auth_required": True, "email": "partner@example.com"}
    assert guarded.get("/api/hypotheses").status_code == 200
    guarded.post("/api/auth/logout")
    assert guarded.get("/api/hypotheses").status_code == 401


def test_allowlist_ignores_case(guarded, monkeypatch):
    finished = _sign_in(guarded, monkeypatch, "patient@example.com")
    assert finished.headers["location"] == "/"
    assert guarded.get("/api/hypotheses").status_code == 200


def test_other_google_accounts_are_refused(guarded, monkeypatch):
    finished = _sign_in(guarded, monkeypatch, "stranger@example.com")
    assert finished.headers["location"] == "/?auth_error=not_allowed"
    assert "mosaiva_session" not in finished.cookies
    assert guarded.get("/api/hypotheses").status_code == 401


def test_unverified_or_wrong_audience_tokens_are_refused(guarded, monkeypatch):
    assert _sign_in(guarded, monkeypatch, "patient@example.com", verified=False).headers["location"].endswith(
        "not_allowed"
    )
    assert _sign_in(guarded, monkeypatch, "patient@example.com", aud="someone-else").headers["location"].endswith(
        "not_allowed"
    )


def test_state_mismatch_is_refused(guarded):
    guarded.get("/api/auth/login", follow_redirects=False)
    finished = guarded.get("/api/auth/callback", params={"code": "abc", "state": "forged"}, follow_redirects=False)
    assert finished.headers["location"] == "/?auth_error=expired"


def test_forged_or_removed_session_cookie_is_refused(guarded, monkeypatch):
    from app.auth import sign

    guarded.cookies.set("mosaiva_session", "e30.not-a-real-signature")
    assert guarded.get("/api/hypotheses").status_code == 401
    guarded.cookies.set("mosaiva_session", sign({"email": "stranger@example.com", "exp": time.time() + 60}))
    assert guarded.get("/api/hypotheses").status_code == 401
    guarded.cookies.set("mosaiva_session", sign({"email": "partner@example.com", "exp": time.time() + 60}))
    assert guarded.get("/api/hypotheses").status_code == 200
    from app.settings import get_settings

    monkeypatch.setenv("MOSAIVA_ALLOWED_EMAILS", "patient@example.com")
    get_settings.cache_clear()
    assert guarded.get("/api/hypotheses").status_code == 401


def test_missing_configuration_fails_closed(guarded, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setenv("MOSAIVA_SESSION_SECRET", "short")
    get_settings.cache_clear()
    response = guarded.get("/api/hypotheses")
    assert response.status_code == 503
    assert "MOSAIVA_SESSION_SECRET" in response.json()["detail"]


def test_local_default_has_no_sign_in(client):
    assert client.get("/api/auth/me").json() == {"auth_required": False, "email": None}
    assert client.get("/api/hypotheses").status_code == 200


def test_database_url_accepts_neon_style_urls():
    from app.settings import Settings

    neon = Settings(MOSAIVA_DATABASE_URL="postgres://u:p@ep-x.neon.tech/db?sslmode=require")
    assert neon.database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
