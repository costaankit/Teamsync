"""
TEAMSYNC — Shared API Configuration
All base URLs, endpoints, and headers used across API tests.
"""

# ── Base URL ──────────────────────────────────────────────────
BASE_URL = "http://frontdms-teamsync.apps.lab.ocp.lan"

# ── Endpoints ─────────────────────────────────────────────────
ENDPOINTS = {
    "login": f"{BASE_URL}/api/tenants/public/users/login",
}

# ── Headers ───────────────────────────────────────────────────
DEFAULT_HEADERS = {
    "appName": "TeamSync",
    "Origin": BASE_URL,
}

# ── Credentials ───────────────────────────────────────────────
VALID_USERNAME           = "ankit@gmail.com"
VALID_PASSWORD_ENCRYPTED = "test"
WRONG_PASSWORD_ENCRYPTED = "test1"
