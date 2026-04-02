import pytest
from playwright.sync_api import Page
from pages.login_page import LoginPage
from pages.upload import upload

# ── Test credentials ─────────────────────────────────────────
VALID_USERNAME = "ankit@gmail.com"
VALID_PASSWORD = "test"

BASE_URL       = "http://frontdms-teamsync.apps.lab.ocp.lan/"


# ── TEAMSYNC-1: Valid login ───────────────────────────────────

@pytest.mark.ui
def test_valid_login(page: Page):
    lp = LoginPage(page)
    up = upload(page)
    lp.open()
    assert lp.is_sign_in_button_visible(), "SIGN IN button not visible"
    lp.login(VALID_USERNAME, VALID_PASSWORD)

    # Wait for URL to change to dashboard
    page.wait_for_url("**/teamsync/home**", timeout=10000)
    up.dtClose.click()
    up.uploadIcon.click()
    up.fileUploadOption.click()
    page.wait_for_url("**/teamsync/home**", timeout=30000)

    # Confirm we are on dashboard
    assert "teamsync/home" in page.url, \
        f"Login failed. URL: {page.url}"
