"""
TEAMSYNC — API Tests: Login Endpoint
App : IMIR (Intelligent Maintenance Information Repository)

API Details (from browser network inspection):
  Endpoint : POST /api/tenants/public/users/login
  Format   : multipart/form-data
  Auth     : password is sent encrypted by the browser
  Response : JWT access_token + refresh_token
"""

import pytest
from qase.pytest import qase
from config.api_config import (
    ENDPOINTS, DEFAULT_HEADERS,
    VALID_USERNAME, VALID_PASSWORD_ENCRYPTED, WRONG_PASSWORD_ENCRYPTED,
)

# ── Config ────────────────────────────────────────────────────
LOGIN_URL = ENDPOINTS["login"]
HEADERS   = DEFAULT_HEADERS


# ── TEAMSYNC-7: Valid API login ───────────────────────────────

@qase.title("API: Valid login returns 200 and access_token")
@pytest.mark.api
def test_api_valid_login(api_client):
    data = {
        "username": VALID_USERNAME,
        "password": VALID_PASSWORD_ENCRYPTED,
    }

    response = api_client.post(
        LOGIN_URL,
        files={k: (None, v) for k, v in data.items()},
        headers=HEADERS,
        verify=False
    )

    assert response.status_code == 200, \
        f"Expected 200 but got {response.status_code}. Body: {response.text}"

    body = api_client.parse_json(response)
    assert "access_token" in body, \
        f"access_token missing in response. Got: {list(body.keys())}"
    assert "token_type" in body, "token_type missing in response"
    assert body["token_type"] == "Bearer", \
        f"Expected Bearer token but got: {body['token_type']}"

    print(f"\nToken received: {body['access_token'][:50]}...")
    print(f"Expires in: {body['expires_in']} seconds")


# ── TEAMSYNC-8: Response contains all required fields ─────────

@qase.title("API: Login response has all required fields")
@pytest.mark.api
def test_api_response_fields(api_client):
    data = {
        "username": VALID_USERNAME,
        "password": VALID_PASSWORD_ENCRYPTED,
    }

    response = api_client.post(
        LOGIN_URL,
        files={k: (None, v) for k, v in data.items()},
        headers=HEADERS,
        verify=False
    )

    assert response.status_code == 200
    body = api_client.parse_json(response)

    required_fields = [
        "access_token",
        "refresh_token",
        "token_type",
        "expires_in",
        "refresh_expires_in",
        "session_state",
        "scope"
    ]

    for field in required_fields:
        assert field in body, f"Missing required field: '{field}' in response"


# ── TEAMSYNC-9: Invalid credentials return error ──────────────

@qase.title("API: Invalid login returns 401")
@pytest.mark.api
def test_api_invalid_login(api_client):
    data = {
        "username": "wronguser@test.com",
        "password": WRONG_PASSWORD_ENCRYPTED,
    }

    response = api_client.post(
        LOGIN_URL,
        files={k: (None, v) for k, v in data.items()},
        headers=HEADERS,
        verify=False
    )

    assert response.status_code in [401, 403, 404], \
        f"Expected 401/403 for invalid creds but got {response.status_code}"


# ── TEAMSYNC-10: API response time under 3 seconds ────────────

@qase.title("API: Login response time under 3 seconds")
@pytest.mark.api
def test_api_response_time(api_client):
    data = {
        "username": VALID_USERNAME,
        "password": VALID_PASSWORD_ENCRYPTED,
    }

    response = api_client.post(
        LOGIN_URL,
        files={k: (None, v) for k, v in data.items()},
        headers=HEADERS,
        verify=False
    )

    elapsed_ms = response.elapsed.total_seconds() * 1000
    assert elapsed_ms < 3000, \
        f"API too slow: {elapsed_ms:.0f}ms (limit: 3000ms)"
    print(f"\nResponse time: {elapsed_ms:.0f}ms")


# ── TEAMSYNC-11: Token is valid JWT format ────────────────────

@qase.title("API: access_token is valid JWT Bearer format")
@pytest.mark.api
def test_api_token_format(api_client):
    data = {
        "username": VALID_USERNAME,
        "password": VALID_PASSWORD_ENCRYPTED,
    }

    response = api_client.post(
        LOGIN_URL,
        files={k: (None, v) for k, v in data.items()},
        headers=HEADERS,
        verify=False
    )

    assert response.status_code == 200
    body = api_client.parse_json(response)
    token = body["access_token"]

    # JWT must have exactly 3 parts separated by dots
    parts = token.split(".")
    assert len(parts) == 3, \
        f"Invalid JWT format — expected 3 parts, got {len(parts)}"
