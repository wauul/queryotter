"""OAuth authorization-code clients, PKCE, browser-bound state and revocable sessions."""

import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlparse
import httpx
from authlib.integrations.httpx_client import OAuth2Client
from authlib.jose import JsonWebToken
from fastapi import HTTPException
from backend import store, workspaces


PROVIDERS = {
    "github": {
        "name": "GitHub",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "read:user user:email",
    },
    "google": {
        "name": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid profile email",
        "jwks": "https://www.googleapis.com/oauth2/v3/certs",
    },
    "microsoft": {
        "name": "Microsoft",
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "openid profile email",
        "jwks": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    },
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def providers():
    import json
    from pathlib import Path

    path = Path("public/auth-verification.json")
    evidence = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return [
        {
            "id": key,
            "name": p["name"],
            "configured": bool(
                os.environ.get(key.upper() + "_CLIENT_ID")
                and os.environ.get(key.upper() + "_CLIENT_SECRET")
            ),
            "status": (
                evidence.get("providers", {}).get(key, {}).get("status", "Configured; hosted verification pending")
                if evidence.get("origin") == os.environ.get("APP_ORIGIN")
                and evidence.get("providers", {}).get(key, {}).get("client_id") == os.environ.get(key.upper() + "_CLIENT_ID")
                else "Configured; hosted verification pending"
            ) if os.environ.get(key.upper() + "_CLIENT_ID") and os.environ.get(key.upper() + "_CLIENT_SECRET")
            else "Requires OAuth application credentials",
        }
        for key, p in PROVIDERS.items()
    ]


def canonical(request):
    origin = os.environ.get("APP_ORIGIN") or request.headers.get("x-app-origin")
    parsed = urlparse(origin or "")
    if (
        not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.scheme not in {"https", "http"}
    ):
        raise HTTPException(503, "The application origin is not configured.")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise HTTPException(503, "OAuth requires an HTTPS application origin.")
    return origin.rstrip("/")


def set_cookie(response, request, name, value, max_age):
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=canonical(request).startswith("https://"),
        samesite="lax",
        path="/",
    )


def issue_session(response, request, user_id, lifetime=604800):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with store.connect() as c:
        c.execute(
            "INSERT INTO q_sessions VALUES(?,?,?,?,?)",
            (digest(token), user_id, now, now + lifetime, now),
        )
    set_cookie(response, request, "qot_auth", token, lifetime)


def is_demo(user_id):
    with store.connect() as c:
        return bool(
            c.execute(
                "SELECT 1 FROM q_identities WHERE user_id=? AND provider='demo'",
                (user_id,),
            ).fetchone()
        )


def current(request, optional=False):
    token = request.cookies.get("qot_auth", "")
    with store.connect() as c:
        row = c.execute(
            "SELECT u.*,s.created AS authenticated_at,s.last_seen FROM q_users u JOIN q_sessions s ON s.user_id=u.id WHERE s.hash=? AND s.expires>? AND s.last_seen>? AND u.status='active'",
            (digest(token), time.time(), time.time() - 86400),
        ).fetchone()
        if row and row["last_seen"] < time.time() - 60:
            c.execute(
                "UPDATE q_sessions SET last_seen=? WHERE hash=?",
                (time.time(), digest(token)),
            )
    if row:
        return dict(row)
    if optional:
        return None
    raise HTTPException(401, "Sign in to use your personal workspace.")


def logout(request, response):
    with store.connect() as c:
        c.execute(
            "DELETE FROM q_sessions WHERE hash=?",
            (digest(request.cookies.get("qot_auth", "")),),
        )
    set_cookie(response, request, "qot_auth", "", 0)


def start(provider, request, response):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown sign-in provider.")
    cid = os.environ.get(provider.upper() + "_CLIENT_ID")
    secret = os.environ.get(provider.upper() + "_CLIENT_SECRET")
    if not cid or not secret:
        raise HTTPException(
            503,
            "This sign-in provider needs OAuth application credentials. It is not enabled yet.",
        )
    state = secrets.token_urlsafe(32)
    browser = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    redirect = canonical(request) + "/api/assistant/auth/" + provider + "/callback"
    with store.connect() as c:
        c.execute("DELETE FROM q_oauth WHERE expires<?", (time.time(),))
        c.execute(
            "INSERT INTO q_oauth VALUES(?,?,?,?,?)",
            (
                state,
                provider,
                digest(browser),
                workspaces.encrypt(
                    {"verifier": verifier, "nonce": nonce, "redirect": redirect}
                ),
                time.time() + 600,
            ),
        )
    p = PROVIDERS[provider]
    with OAuth2Client(
        cid,
        secret,
        scope=p["scope"],
        redirect_uri=redirect,
        code_challenge_method="S256",
    ) as oauth:
        url, _ = oauth.create_authorization_url(
            p["authorize"], state=state, code_verifier=verifier, nonce=nonce
        )
    set_cookie(response, request, "qot_oauth_browser", browser, 600)
    return {"url": url}


def consume_state(provider, state, browser):
    with store.connect() as c:
        # Claim exactly once even when duplicate callback requests overlap.
        row = c.execute(
            "DELETE FROM q_oauth WHERE state=? AND provider=? AND browser_hash=? AND expires>? RETURNING secret",
            (state, provider, digest(browser), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(
            400, "Sign-in state expired or could not be verified. Start sign-in again."
        )
    return workspaces.decrypt(row["secret"])


def verify_oidc(provider, id_token, client_id, nonce, jwks):
    jwt = JsonWebToken(["RS256"])
    claims = jwt.decode(
        id_token,
        jwks,
        claims_options={
            "aud": {"essential": True, "value": client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
            "sub": {"essential": True},
            "iss": {"essential": True},
            "nonce": {"essential": True, "value": nonce},
        },
    )
    claims.validate(leeway=60)
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("nonce")
    issuer = claims.get("iss", "")
    if provider == "google" and issuer not in {
        "https://accounts.google.com",
        "accounts.google.com",
    }:
        raise ValueError("issuer")
    if provider == "microsoft":
        import re

        tid = claims.get("tid", "")
        if (
            not re.fullmatch(r"[a-fA-F0-9-]{36}", tid)
            or issuer != "https://login.microsoftonline.com/" + tid + "/v2.0"
        ):
            raise ValueError("issuer")
    return dict(claims)


def callback(provider, request, response):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown sign-in provider.")
    state = request.query_params.get("state", "")
    browser = request.cookies.get("qot_oauth_browser", "")
    context = consume_state(provider, state, browser)
    if request.query_params.get("error") or not request.query_params.get("code"):
        raise HTTPException(400, "Sign-in was cancelled or denied. You can try again.")
    p = PROVIDERS[provider]
    cid = os.environ[provider.upper() + "_CLIENT_ID"]
    secret = os.environ[provider.upper() + "_CLIENT_SECRET"]
    try:
        with OAuth2Client(
            cid,
            secret,
            redirect_uri=context["redirect"],
            token_endpoint_auth_method="client_secret_post",
            timeout=15,
        ) as oauth:
            token = oauth.fetch_token(
                p["token"],
                grant_type="authorization_code",
                code=request.query_params["code"],
                code_verifier=context["verifier"],
                headers={"Accept": "application/json"},
            )
        if provider == "github":
            with httpx.Client(
                timeout=10,
                headers={
                    "Authorization": "Bearer " + token["access_token"],
                    "Accept": "application/vnd.github+json",
                },
            ) as client:
                r = client.get("https://api.github.com/user")
                r.raise_for_status()
                profile = r.json()
                subject = str(profile["id"])
                name = profile.get("name") or profile["login"]
                email = profile.get("email")
        else:
            keys = httpx.get(p["jwks"], timeout=10)
            keys.raise_for_status()
            profile = verify_oidc(
                provider, token["id_token"], cid, context["nonce"], keys.json()
            )
            subject = profile["sub"]
            name = profile.get("name") or "QueryOtter member"
            email = profile.get("email")
        user = workspaces.user_for_identity(provider, subject, name, email)
    except Exception:
        raise HTTPException(
            400,
            "The identity provider response could not be verified. Start sign-in again; no provider secrets are logged.",
        ) from None
    issue_session(response, request, user["id"])
    set_cookie(response, request, "qot_oauth_browser", "", 0)
    return user
