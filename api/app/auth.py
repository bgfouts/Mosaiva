import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request

from app.settings import get_settings

SESSION_COOKIE = "mosaiva_session"
STATE_COOKIE = "mosaiva_oauth_state"
SESSION_SECONDS = 30 * 24 * 3600
STATE_SECONDS = 10 * 60
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


class AuthNotConfigured(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _secret() -> bytes:
    secret = get_settings().mosaiva_session_secret
    if len(secret) < 32:
        raise AuthNotConfigured("MOSAIVA_SESSION_SECRET must be at least 32 characters.")
    return secret.encode()


def sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def unsign(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, mac = token.rsplit(".", 1)
    expected = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or float(payload.get("exp") or 0) < time.time():
        return None
    return payload


def assert_configured() -> None:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("GOOGLE_CLIENT_ID", settings.google_client_id),
            ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
            ("MOSAIVA_ALLOWED_EMAILS", settings.mosaiva_allowed_emails),
            ("MOSAIVA_SESSION_SECRET", settings.mosaiva_session_secret),
        )
        if not value.strip()
    ]
    if missing:
        raise AuthNotConfigured("Sign-in is not configured. Missing: " + ", ".join(missing) + ".")
    _secret()


def is_allowed(email: str) -> bool:
    return email.strip().lower() in get_settings().allowed_emails


def current_email(request: Request) -> str | None:
    payload = unsign(request.cookies.get(SESSION_COOKIE))
    if not payload:
        return None
    email = str(payload.get("email") or "")
    # Re-check the allowlist on every request so removing an address takes effect at once.
    return email if is_allowed(email) else None


def require_user(request: Request) -> str | None:
    if not get_settings().auth_required:
        return None
    try:
        assert_configured()
    except AuthNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    email = current_email(request)
    if email is None:
        raise HTTPException(status_code=401, detail="Sign in with Google to continue.")
    return email


def public_base_url(request: Request) -> str:
    configured = get_settings().mosaiva_public_url.strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def redirect_uri(request: Request) -> str:
    return f"{public_base_url(request)}/api/auth/callback"


def is_secure(request: Request) -> bool:
    return public_base_url(request).startswith("https://")


def new_state() -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    return state, sign({"state": state, "exp": time.time() + STATE_SECONDS})


def authorize_url(request: Request, state: str) -> str:
    query = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(query)}"


def exchange_code(code: str, request: Request) -> dict:
    settings = get_settings()
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri(request),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def verified_email(token_response: dict) -> str | None:
    """Read the ID token returned straight from Google's token endpoint over TLS.

    OpenID Connect allows trusting that token without a signature check because it came
    from the token endpoint itself; the audience, issuer, expiry, and verified email still
    have to match.
    """
    raw = str(token_response.get("id_token") or "")
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    try:
        claims = json.loads(_unb64(parts[1]))
    except (ValueError, json.JSONDecodeError):
        return None
    if claims.get("aud") != get_settings().google_client_id:
        return None
    if claims.get("iss") not in GOOGLE_ISSUERS:
        return None
    if float(claims.get("exp") or 0) < time.time():
        return None
    if claims.get("email_verified") not in (True, "true"):
        return None
    email = str(claims.get("email") or "").strip().lower()
    return email or None


def session_token(email: str) -> str:
    return sign({"email": email, "exp": time.time() + SESSION_SECONDS})
