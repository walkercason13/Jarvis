"""WHOOP API v2 access: OAuth authorization-code flow, rotating refresh tokens,
and today's recovery/sleep/strain. Endpoint paths verified against WHOOP's
official docs (developer.whoop.com/api) via Context7 — see the
whoop-integration skill for the non-negotiable rules this file follows.
"""

import os
import secrets
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

import db

load_dotenv()

CLIENT_ID = os.environ["WHOOP_CLIENT_ID"]
CLIENT_SECRET = os.environ["WHOOP_CLIENT_SECRET"]

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer/v2"

REDIRECT_URI = "http://localhost:8080/callback"
# Request every read scope now so later features (workouts, profile, body
# measurement) never need a second browser re-authorization.
SCOPES = "offline read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement"

# Refresh this long before actual expiry to avoid racing a request mid-call.
REFRESH_BUFFER = timedelta(minutes=5)


class TokenRefreshError(RuntimeError):
    """Raised loudly whenever a token refresh fails or WHOOP omits the
    rotated refresh token. Never swallow this — see whoop-integration skill
    non-negotiable #3."""


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        self.server.callback_params = {k: v[0] for k, v in params.items()}

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>Jarvis is connected to WHOOP. You can close this tab.</body></html>")

    def log_message(self, format, *args):
        pass  # keep terminal output clean during the OAuth handshake


def authorize():
    """One-time browser approval. Blocks until WHOOP redirects back to
    localhost:8080/callback, then exchanges the code and stores tokens."""
    state = secrets.token_urlsafe(16)

    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    server.callback_params = None

    auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    print("Opening browser for WHOOP authorization...")
    webbrowser.open(f"{AUTH_URL}?{urlencode(auth_params)}")

    server.handle_request()
    params = server.callback_params

    if params is None or "code" not in params:
        raise RuntimeError(f"WHOOP authorization callback did not return a code: {params}")
    if params.get("state") != state:
        raise RuntimeError("WHOOP authorization callback state mismatch — possible CSRF, aborting.")

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    resp.raise_for_status()
    _save_token_response(resp.json())
    print("WHOOP authorization complete.")


def _save_token_response(payload):
    if "refresh_token" not in payload:
        raise TokenRefreshError(f"WHOOP token response did not include a refresh_token: {payload}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload["expires_in"])
    db.save_tokens(payload["access_token"], payload["refresh_token"], expires_at)


def _refresh(refresh_token):
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": "offline",
            },
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TokenRefreshError(f"WHOOP token refresh request failed: {e}") from e

    _save_token_response(resp.json())


def get_access_token():
    """Returns a valid access token, refreshing (and rotating the refresh
    token) if the stored one is near expiry. Raises loudly on any failure —
    never falls back to a stale/expired token silently."""
    tokens = db.load_tokens()
    if tokens is None:
        raise RuntimeError("No WHOOP tokens stored yet — run whoop.authorize() first.")

    if datetime.now(timezone.utc) >= tokens["expires_at"] - REFRESH_BUFFER:
        _refresh(tokens["refresh_token"])
        tokens = db.load_tokens()

    return tokens["access_token"]


def _get(path, params=None):
    resp = requests.get(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {get_access_token()}"},
        params=params,
    )
    return resp


def get_today_cycle():
    """Latest physiological cycle, or None if the strap hasn't synced any
    cycle yet."""
    resp = _get("/cycle", params={"limit": 1})
    resp.raise_for_status()
    records = resp.json().get("records", [])
    return records[0] if records else None


def get_today_strain(cycle):
    """(state, strain) — state is 'ok', 'not_synced', or the cycle's
    score_state (e.g. PENDING_SCORE) when it exists but isn't scored yet."""
    if cycle is None:
        return "not_synced", None
    if cycle.get("score_state") != "SCORED":
        return cycle.get("score_state", "not_synced"), None
    return "ok", cycle["score"]["strain"]


def get_today_recovery(cycle_id):
    """(state, recovery) for the given cycle. A 404 means WHOOP hasn't
    synced recovery for this cycle yet — that's expected, not an error."""
    resp = _get(f"/cycle/{cycle_id}/recovery")
    if resp.status_code == 404:
        return "not_synced", None
    resp.raise_for_status()

    payload = resp.json()
    # WHOOP's docs are inconsistent on whether this is a bare object or a
    # {records: [...]} collection for a single cycle — handle both.
    if "records" in payload:
        records = payload["records"]
        if not records:
            return "not_synced", None
        recovery = records[0]
    else:
        recovery = payload

    if recovery.get("score_state") != "SCORED":
        return recovery.get("score_state", "not_synced"), None
    return "ok", recovery


def get_today_sleep():
    """(state, sleep) for the most recent sleep record."""
    resp = _get("/activity/sleep", params={"limit": 1})
    if resp.status_code == 404:
        return "not_synced", None
    resp.raise_for_status()

    records = resp.json().get("records", [])
    if not records:
        return "not_synced", None

    sleep = records[0]
    if sleep.get("score_state") != "SCORED":
        return sleep.get("score_state", "not_synced"), None
    return "ok", sleep
