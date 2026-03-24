
"""
TEAMSYNC — UI Automation Tests: Login Page
App : IMIR (Intelligent Maintenance Information Repository)
URL : http://frontdms-teamsync.apps.lab.ocp.lan/
Maps to Qase project: TEAMSYNC
"""

import pytest
from playwright.sync_api import Page
from pages.login_page import LoginPage

# ── Test credentials ─────────────────────────────────────────
VALID_USERNAME = "ankit@gmail.com"
VALID_PASSWORD = "test"
WRONG_PASSWORD = "WrongPass@999"
WRONG_USERNAME = "invaliduser@test.com"

BASE_URL       = "http://frontdms-teamsync.apps.lab.ocp.lan/"


# ── TEAMSYNC-1: Valid login ───────────────────────────────────

@pytest.mark.ui
def test_valid_login(page: Page):
    lp = LoginPage(page)
    lp.open()
    assert lp.is_sign_in_button_visible(), "SIGN IN button not visible"
    lp.login(VALID_USERNAME, VALID_PASSWORD)

    # Wait for URL to change to dashboard
    page.wait_for_url("**/teamsync/home**", timeout=30000)

    # Confirm we are on dashboard
    assert "teamsync/home" in page.url, \
        f"Login failed. URL: {page.url}"


# ── TEAMSYNC-2: Wrong password ────────────────────────────────

@pytest.mark.ui
def test_wrong_password(page: Page):
    lp = LoginPage(page)
    lp.open()
    lp.login(VALID_USERNAME, WRONG_PASSWORD)
    page.wait_for_timeout(3000)
    assert page.url == BASE_URL, f"Should stay on login page. URL: {page.url}"


# ── TEAMSYNC-3: Empty username ────────────────────────────────

@pytest.mark.ui
def test_empty_username(page: Page):
    lp = LoginPage(page)
    lp.open()
    lp.login("", VALID_PASSWORD)
    page.wait_for_timeout(2000)
    assert page.url == BASE_URL, f"Should stay on login page. URL: {page.url}"


# ── TEAMSYNC-4: Empty both fields ────────────────────────────

@pytest.mark.ui
def test_empty_fields(page: Page):
    lp = LoginPage(page)
    lp.open()
    lp.login("", "")
    page.wait_for_timeout(2000)
    assert page.url == BASE_URL, f"Should stay on login page. URL: {page.url}"


# ── TEAMSYNC-5: Invalid username ──────────────────────────────

@pytest.mark.ui
def test_invalid_username(page: Page):
    lp = LoginPage(page)
    lp.open()
    lp.login(WRONG_USERNAME, VALID_PASSWORD)
    page.wait_for_timeout(3000)
    assert page.url == BASE_URL, f"Should stay on login page. URL: {page.url}"


# ── TEAMSYNC-6: Page loads correctly ─────────────────────────

@pytest.mark.ui
def test_page_loads(page: Page):
    lp = LoginPage(page)
    lp.open()
    assert lp.is_sign_in_button_visible(), "SIGN IN button not found"
    assert "frontdms-teamsync" in page.url, "Wrong URL loaded"