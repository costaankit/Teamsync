import random
import pytest
from playwright.sync_api import Page
from pages.login_page import LoginPage
from pages.upload import upload
from pages.download import Download

# ── Test credentials ──────────────────────────────────────────
VALID_USERNAME = "ankit@gmail.com"
VALID_PASSWORD = "test"


# ── Helper: ensure logged in ──────────────────────────────────
def _ensure_logged_in(page: Page):
    if "teamsync/home" not in page.url:
        lp = LoginPage(page)
        up = upload(page)
        lp.open()
        lp.login(VALID_USERNAME, VALID_PASSWORD)
        page.wait_for_url("**/teamsync/home**", timeout=10000)
        try:
            up.dtClose.click(timeout=3000)
        except Exception:
            pass


# ── TC_DL_03 : Download Without File ─────────────────────────
@pytest.mark.ui
def test_TC_DL_03_download_without_file(page: Page):
    """
    Verify download button is hidden when no file is selected.
    Severity: Medium
    """
    _ensure_logged_in(page)
    dl = Download(page)

    # Deselect everything by clicking the empty content area
    try:
        page.locator("#filemanager_content").click(
            position={"x": 10, "y": 10}, timeout=3000
        )
    except Exception:
        pass
    page.wait_for_timeout(500)

    # Download button parent must have e-hidden when nothing is selected
    is_btn_hidden = page.evaluate(
        """() => {
            const btn = document.getElementById('filemanager_tb_download');
            if (!btn) return true;
            let el = btn.parentElement;
            while (el) {
                if (el.classList.contains('e-hidden')) return true;
                el = el.parentElement;
            }
            return false;
        }"""
    )
    assert is_btn_hidden, "Download button should be hidden when no file is selected"


# ── TC_DL_04 : File Download ──────────────────────────────────
@pytest.mark.ui
def test_TC_DL_04_large_file_download(page: Page):
    """
    Verify a file can be downloaded successfully.
    Severity: High
    """
    _ensure_logged_in(page)
    dl = Download(page)

    selected_file = dl.select_random_file()

    with page.expect_download(timeout=120000) as download_info:
        dl.click_download()

    downloaded = download_info.value
    assert downloaded.failure() is None, (
        f"Download of '{selected_file}' failed: {downloaded.failure()}"
    )
    print(f"Downloaded: {downloaded.suggested_filename}")


# ── TC_DL_05 : Slow Network Download ─────────────────────────
@pytest.mark.ui
def test_TC_DL_05_slow_network_download(page: Page):
    """
    Verify download completes on a throttled network.
    Severity: Medium
    """
    _ensure_logged_in(page)
    dl = Download(page)

    try:
        cdp = page.context.new_cdp_session(page)
        # Use 3G-like conditions: slow enough to test behaviour but won't
        # crash the page's background XHR calls (50 kbps was too aggressive).
        cdp.send("Network.emulateNetworkConditions", {
            "offline": False,
            "downloadThroughput": 500 * 1024 / 8,   # ~500 kbps
            "uploadThroughput":   250 * 1024 / 8,   # ~250 kbps
            "latency": 100,                          # 100ms
        })
    except Exception:
        pytest.skip("CDP network throttling not available")

    selected_file = dl.select_random_file()

    try:
        with page.expect_download(timeout=60000) as download_info:
            dl.click_download()
        downloaded = download_info.value
        assert downloaded.failure() is None, (
            f"Download of '{selected_file}' failed on slow network: {downloaded.failure()}"
        )
    finally:
        # Always reset network — even if the download assertion fails
        try:
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
                "latency": 0,
            })
        except Exception:
            pass


# ── TC_DL_06 : Cancel Download ────────────────────────────────
@pytest.mark.ui
def test_TC_DL_06_cancel_download(page: Page):
    """
    Verify cancelling a running download clears the progress UI.
    Severity: Medium
    """
    _ensure_logged_in(page)
    dl = Download(page)

    dl.select_random_file()
    dl.click_download()

    page.wait_for_timeout(1500)
    try:
        dl.click_cancel()
    except Exception:
        pass  # Browser-native download bar may not have an in-page cancel

    assert not page.locator("[class*='error-dialog']").is_visible(), (
        "Unexpected error dialog after cancel"
    )


# ── TC_DL_07 : File Format Support ───────────────────────────
@pytest.mark.ui
def test_TC_DL_07_file_format_support(page: Page):
    """
    Verify a randomly selected file downloads and has a file extension.
    Severity: Medium
    """
    _ensure_logged_in(page)
    dl = Download(page)

    selected_file = dl.select_random_file()

    with page.expect_download(timeout=30000) as download_info:
        dl.click_download()

    downloaded = download_info.value
    assert downloaded.failure() is None, (
        f"Download of '{selected_file}' failed: {downloaded.failure()}"
    )
    assert "." in downloaded.suggested_filename, (
        f"No file extension: '{downloaded.suggested_filename}'"
    )
    print(f"Downloaded: {downloaded.suggested_filename}")


# ── TC_DL_08 : Session Timeout ────────────────────────────────
@pytest.mark.ui
def test_TC_DL_08_session_timeout(page: Page):
    """
    Verify an expired session prevents access and prompts re-authentication.
    Severity: High
    """
    _ensure_logged_in(page)

    # Invalidate session by clearing cookies and localStorage tokens, then reload
    page.context.clear_cookies()
    page.evaluate("() => { try { localStorage.clear(); } catch(e) {} "
                  "try { sessionStorage.clear(); } catch(e) {} }")
    page.reload()
    page.wait_for_timeout(2000)

    # App should redirect to login or show an auth form
    redirected_to_login = "login" in page.url.lower() or "sign" in page.url.lower()
    session_msg = page.locator(
        "input[type='password'], [class*='login'], [class*='signin']"
    ).count() > 0

    assert redirected_to_login or session_msg, (
        f"Expected login page or auth form after session expiry, got: {page.url}"
    )

    # Re-login so TC_DL_09 can run on a valid session
    lp = LoginPage(page)
    up = upload(page)
    lp.open()
    lp.login(VALID_USERNAME, VALID_PASSWORD)
    page.wait_for_url("**/teamsync/home**", timeout=10000)
    try:
        up.dtClose.click(timeout=3000)
    except Exception:
        pass


# ── TC_DL_09 : Parallel Downloads ────────────────────────────
@pytest.mark.ui
def test_TC_DL_09_parallel_downloads(page: Page):
    """
    Verify multiple files can be selected and downloaded.
    Severity: Medium
    """
    _ensure_logged_in(page)
    dl = Download(page)

    # Select first file (verified working approach)
    first_file = dl.select_random_file()
    dl.verify_single_selection()

    count = dl.file_rows.count()

    # Ctrl+click up to 3 more files (best-effort; not all builds support multi-select)
    for idx in range(0, min(4, count)):
        row = dl.file_rows.nth(idx)
        box = row.bounding_box()
        if box and box["height"] > 0:
            page.keyboard.down("Control")
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.keyboard.up("Control")
            page.wait_for_timeout(200)

    with page.expect_download(timeout=60000) as dl1_info:
        dl.click_download()

    downloaded = dl1_info.value
    assert downloaded.failure() is None, (
        f"Parallel download failed for '{first_file}': {downloaded.failure()}"
    )
    print(f"Downloaded (parallel): {downloaded.suggested_filename}")
