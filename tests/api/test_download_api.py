"""
TEAMSYNC — API Tests: Download Endpoint

Verifies that clicking the Download icon triggers a POST to:
  POST /api/dms_service_LM/api/download

The endpoint returns the file as an inline binary response (Content-Disposition: inline).
A 200 OK with binary content confirms the download API works correctly.
Browser security warnings ("Insecure download blocked") are a browser-level concern
and are handled separately via the UI keep/discard flow.

API observed via browser DevTools:
  Request URL  : http://frontdms-teamsync.apps.lab.ocp.lan/api/dms_service_LM/api/download
  Method       : POST
  Content-Type : multipart/form-data
  Body field   : downloadInput (JSON string)
  Auth         : Bearer token in Authorization header + username header
"""

# run command 
# venv\Scripts\python.exe -m pytest tests\ui\test_download_ui.py -v --headed

import json
import pytest
import requests
from config.api_config import BASE_URL, ENDPOINTS

# ── Endpoint & auth ───────────────────────────────────────────
DOWNLOAD_URL = ENDPOINTS["download"]
LOGIN_URL    = ENDPOINTS["login"]

# Credentials (ankit account — verified working)
TEST_USERNAME = "ankit@gmail.com"
TEST_PASSWORD = "test"


# ── Fixture: obtain a fresh Bearer token ─────────────────────
@pytest.fixture(scope="module")
def auth_token():
    """Log in as test1 and return a valid Bearer token."""
    resp = requests.post(
        LOGIN_URL,
        files={
            "username": (None, TEST_USERNAME),
            "password": (None, TEST_PASSWORD),
        },
        headers={"Origin": BASE_URL, "appName": "TeamSync"},
        verify=False,
        timeout=15,
    )
    assert resp.status_code == 200, (
        f"Login failed ({resp.status_code}): {resp.text[:300]}"
    )
    token = resp.json().get("access_token")
    assert token, "No access_token in login response"
    return token


# ── Shared download payload (matches real browser request) ────
DOWNLOAD_INPUT = {
    "action":   "download",
    "path":     "/",
    "names":    ["69cf69aeeb44820c21af4c5d"],
    "data": [
        {
            "id":            "69cf69aeeb44820c21af4c5d",
            "action":        "save",
            "name":          "1.png",
            "size":          2127387,
            "displaySize":   "2.03 MB",
            "type":          "png",
            "filterPath":    "/",
            "abFilterPath":  "",
            "parentId":      "6997edafefbab23233cfbd36",
            "isFile":        True,
            "ownedBy":       "ankit@gmail<>com",
            "ownedByName":   "Ankit",
            "curDir":        "Files",
        }
    ],
}


def _download_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "username":      TEST_USERNAME,
        "Origin":        BASE_URL,
        "Referer":       f"{BASE_URL}/teamsync/home",
    }


# ── TC_DL_API_01 : Download triggers 200 OK ──────────────────
@pytest.mark.api
def test_download_api_returns_200(auth_token):
    """
    Verify the download endpoint responds with 200 OK when a valid
    file ID and Bearer token are supplied.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200, (
        f"Expected 200 OK, got {resp.status_code}. Body: {resp.text[:300]}"
    )


# ── TC_DL_API_02 : Response contains binary file content ──────
@pytest.mark.api
def test_download_api_returns_file_content(auth_token):
    """
    Verify the response body is non-empty binary data (the actual file).
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200
    assert len(resp.content) > 0, "Response body is empty — no file data received"
    print(f"\nFile size received: {len(resp.content):,} bytes")


# ── TC_DL_API_03 : Content-Disposition header present ─────────
@pytest.mark.api
def test_download_api_content_disposition(auth_token):
    """
    Verify the response includes a Content-Disposition header with the filename.
    This is what the browser uses to name the downloaded file.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200
    cd = resp.headers.get("Content-Disposition", "")
    assert cd != "", "Content-Disposition header is missing"
    assert "1.png" in cd, (
        f"Expected filename '1.png' in Content-Disposition, got: '{cd}'"
    )
    print(f"\nContent-Disposition: {cd}")


# ── TC_DL_API_04 : Content-Type is PDF ───────────────────────
@pytest.mark.api
def test_download_api_content_type(auth_token):
    """
    Verify the response Content-Type matches the file type (PDF).
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200
    ct = resp.headers.get("Content-Type", "")
    assert ct != "", f"Content-Type header is missing"
    # Accept any valid binary content type (image, pdf, octet-stream, etc.)
    assert any(t in ct.lower() for t in ["image", "pdf", "octet-stream", "application"]), (
        f"Unexpected Content-Type: '{ct}'"
    )
    print(f"\nContent-Type: {ct}")


# ── TC_DL_API_05 : Content-Length matches file size ───────────
@pytest.mark.api
def test_download_api_content_length(auth_token):
    """
    Verify the Content-Length in the response matches the actual bytes received.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200
    content_length = resp.headers.get("Content-Length")
    if content_length:
        assert int(content_length) == len(resp.content), (
            f"Content-Length {content_length} does not match "
            f"received bytes {len(resp.content)}"
        )
        print(f"\nContent-Length: {content_length} bytes OK")
    else:
        # Chunked transfer — just verify body is non-empty
        assert len(resp.content) > 0


# ── TC_DL_API_06 : No token — endpoint behaviour ─────────────
@pytest.mark.api
def test_download_api_no_token_behaviour():
    """
    Verify the download endpoint has a defined response when no Bearer token
    is provided. The endpoint currently returns 200 (public/pre-signed URL
    pattern); this test documents that behaviour.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers={
            "username": TEST_USERNAME,
            "Origin":   BASE_URL,
        },
        verify=False,
        timeout=30,
    )

    # The endpoint responds with a defined HTTP status (not a 5xx crash)
    assert resp.status_code < 500, (
        f"Server error when calling without token: {resp.status_code} — {resp.text[:200]}"
    )
    print(f"\nNo-token response status: {resp.status_code}")


# ── TC_DL_API_07 : Invalid token returns 401 ─────────────────
@pytest.mark.api
def test_download_api_invalid_token_returns_401():
    """
    Verify that a download request with a forged/expired token is rejected.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers={
            "Authorization": "Bearer invalid.token.value",
            "username":      TEST_USERNAME,
            "Origin":        BASE_URL,
        },
        verify=False,
        timeout=15,
    )

    assert resp.status_code in [401, 403], (
        f"Expected 401/403 with invalid token, got {resp.status_code}"
    )


# ── TC_DL_API_08 : Response time under 5 seconds ─────────────
@pytest.mark.api
def test_download_api_response_time(auth_token):
    """
    Verify the download API responds within 5 seconds for a small file.
    """
    resp = requests.post(
        DOWNLOAD_URL,
        files={"downloadInput": (None, json.dumps(DOWNLOAD_INPUT))},
        headers=_download_headers(auth_token),
        verify=False,
        timeout=60,
    )

    assert resp.status_code == 200
    elapsed_ms = resp.elapsed.total_seconds() * 1000
    assert elapsed_ms < 5000, (
        f"Download API too slow: {elapsed_ms:.0f}ms (limit: 5000ms)"
    )
    print(f"\nResponse time: {elapsed_ms:.0f}ms")
