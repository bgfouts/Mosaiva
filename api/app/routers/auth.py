import hmac

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import (
    SESSION_COOKIE,
    SESSION_SECONDS,
    STATE_COOKIE,
    STATE_SECONDS,
    AuthNotConfigured,
    assert_configured,
    authorize_url,
    current_email,
    exchange_code,
    is_allowed,
    is_secure,
    new_state,
    session_token,
    unsign,
    verified_email,
)
from app.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _configured_or_503() -> None:
    try:
        assert_configured()
    except AuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _home(error: str = "") -> RedirectResponse:
    response = RedirectResponse("/" + (f"?auth_error={error}" if error else ""), status_code=303)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    return response


@router.get("/me")
def me(request: Request):
    settings = get_settings()
    if not settings.auth_required:
        return {"auth_required": False, "email": None}
    _configured_or_503()
    email = current_email(request)
    if email is None:
        return JSONResponse({"auth_required": True, "email": None}, status_code=401)
    return {"auth_required": True, "email": email}


@router.get("/login")
def login(request: Request):
    _configured_or_503()
    state, signed = new_state()
    response = RedirectResponse(authorize_url(request, state), status_code=303)
    response.set_cookie(
        STATE_COOKIE,
        signed,
        max_age=STATE_SECONDS,
        httponly=True,
        secure=is_secure(request),
        samesite="lax",
        path="/api/auth",
    )
    return response


@router.get("/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    _configured_or_503()
    if error or not code:
        return _home("cancelled")
    saved = unsign(request.cookies.get(STATE_COOKIE))
    if not saved or not state or not hmac.compare_digest(str(saved.get("state") or ""), state):
        return _home("expired")
    try:
        email = verified_email(exchange_code(code, request))
    except httpx.HTTPError:
        return _home("google")
    if email is None or not is_allowed(email):
        return _home("not_allowed")
    response = _home()
    response.set_cookie(
        SESSION_COOKIE,
        session_token(email),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=is_secure(request),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
