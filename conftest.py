"""
conftest.py — TEAMSYNC Project
Configures Playwright browser, report generation, and base settings.
"""

import os
import pytest
import requests
from datetime import datetime

from utils.excel_reporter import ExcelReporter, api_tracker


# ── Auto-create reports folder ───────────────────────────────
# Creates reports/ folder automatically before every test run
# Without this — pytest crashes if reports/ folder is missing
os.makedirs("reports", exist_ok=True)


# ── Excel reporter — writes PASS/FAIL back to Teamsync_testcases.xlsx ──
# Collects every test outcome during the run and updates STATUS column
# of the matching Test Case ID row when the session finishes.
_excel_reporter = ExcelReporter()


def _extract_error(report) -> str:
    """Pull a short, useful error description out of a pytest report.

    For failed tests:   the exception type + message (first line of repr).
    For skipped tests:  the skip reason ("BLOCKED: ..." etc.)
    For passed tests:   empty string.
    """
    if report.outcome == "passed":
        return ""
    # Skipped — pytest stores the reason in longrepr as a tuple
    if report.outcome == "skipped":
        if isinstance(report.longrepr, tuple) and len(report.longrepr) >= 3:
            return str(report.longrepr[2])   # (path, lineno, reason)
        return str(report.longrepr or "").strip()[:300]
    # Failed — longrepr is a ReprExceptionInfo or string
    text = ""
    if hasattr(report.longrepr, "reprcrash") and report.longrepr.reprcrash:
        text = report.longrepr.reprcrash.message
    else:
        text = str(report.longrepr or "")
    # Keep the first meaningful line only — full traceback is overkill in Excel
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return (lines[0] if lines else text)[:300]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture each test's outcome, error, and duration for the Excel reporter.

    Phases pytest reports for each test:
      • setup    — fixtures run AND @pytest.mark.skip is evaluated here
      • call     — the test function body actually executes (only if setup passed)
      • teardown — fixture cleanup (ignored — doesn't change pass/fail)

    Outcomes we care about per phase:
      • setup → failed  : fixture crashed → test never ran → record as FAILED
      • setup → skipped : @pytest.mark.skip / skipif fired → record as SKIPPED
      • call  → any     : real test result — record passed/failed/skipped
    """
    outcome = yield
    report = outcome.get_result()
    if report.when == "setup":
        if report.outcome in ("failed", "skipped"):
            _excel_reporter.record(
                item.name,
                report.outcome,
                error=_extract_error(report),
                duration=report.duration,
            )
    elif report.when == "call":
        # Consume the API status set by `_print()` during the test body
        api_code = api_tracker.consume()
        _excel_reporter.record(
            item.name,
            report.outcome,
            api_code=api_code,
            error=_extract_error(report),
            duration=report.duration,
        )


def pytest_sessionfinish(session, exitstatus):
    """Write all collected results to Teamsync_testcases.xlsx."""
    _excel_reporter.write_results()


# ── pytest hook — runs before any test starts ────────────────
def pytest_configure(config):

    # ── Timestamped report name ───────────────────────────────
    # Every run gets a unique filename so old reports are never overwritten
    # Example: reports/IMIR_Full_Report_2026-03-23_16-45-30.html
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_name = f"reports/IMIR_Full_Report_{timestamp}.html"

    # Set the HTML report path — pytest-html reads this setting
    try:
        config.option.htmlpath = report_name
        config.option.self_contained_html = True
    except AttributeError:
        # htmlpath not available if pytest-html not installed
        pass

    # ── Register custom markers ───────────────────────────────
    # Stops pytest showing "Unknown mark" warnings
    # Lets you run: pytest -m ui   OR   pytest -m api
    config.addinivalue_line(
        "markers", "login: Combined UI + API tests for Login module"
    )
    config.addinivalue_line(
        "markers", "upload: Combined UI + API tests for Upload module"
    )
    config.addinivalue_line(
        "markers", "creation: Combined UI + API tests for Creation module"
    )
    config.addinivalue_line(
        "markers", "delete: Combined UI + API tests for Delete module"
    )
    config.addinivalue_line(
        "markers", "rename: Combined UI + API tests for Rename module"
    )
    config.addinivalue_line(
        "markers", "move: Combined UI + API tests for Move module"
    )
    config.addinivalue_line(
        "markers", "copy_paste: Combined UI + API tests for Copy-Paste module"
    )
    config.addinivalue_line(
        "markers", "share: Combined UI + API tests for Share module"
    )
    config.addinivalue_line(
        "markers", "shortcut: Combined UI + API tests for Create Shortcut module"
    )


# ── Shared API client fixture ─────────────────────────────────
class ApiClient:
    """Wraps requests with clean error handling for all API tests."""

    def post(self, url, **kwargs):
        try:
            response = requests.post(url, timeout=30, **kwargs)
            return response
        except requests.exceptions.SSLError:
            pytest.fail(f"SSL certificate error.\nURL: {url}")
        except requests.exceptions.ConnectionError:
            pytest.fail(f"Cannot connect to server. Is the app running?\nURL: {url}")
        except requests.exceptions.Timeout:
            pytest.fail(f"Request timed out after 30 seconds.\nURL: {url}")
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Request failed: {e}")

    def parse_json(self, response):
        try:
            return response.json()
        except Exception:
            pytest.fail(
                f"Response is not valid JSON.\n"
                f"Status: {response.status_code}\n"
                f"Body: {response.text[:300]}"
            )


@pytest.fixture
def api_client():
    return ApiClient()


# ── Single browser, single tab for all tests ─────────────────
# scope="session" → one browser + one tab reused across every test

@pytest.fixture(scope="session")
def context(browser, browser_context_args):
    ctx = browser.new_context(**browser_context_args)
    yield ctx
    ctx.close()

@pytest.fixture(scope="session")
def page(context):
    pg = context.new_page()
    yield pg
    pg.close()


# ── Bearer token for upload/API tests ────────────────────────
# Function-scoped: re-logs in before EVERY test that asks for it.
# Reason: Keycloak tokens expire in ~15 min. With session-scope the same stale
# token was being handed to every test, so any API call after the 15-min mark
# returned 401 — cascading failures across long runs (uploads + creation).
# Cost: ~200 ms login round-trip per API test (~6 s added across the whole run).

@pytest.fixture
def auth_token():
    import requests as _req
    from config.api_config import ENDPOINTS, DEFAULT_HEADERS, VALID_USERNAME, VALID_PASSWORD_ENCRYPTED
    resp = _req.post(
        ENDPOINTS["login"],
        files={"username": (None, VALID_USERNAME), "password": (None, VALID_PASSWORD_ENCRYPTED)},
        headers=DEFAULT_HEADERS,
        verify=False,
        timeout=30,
    )
    return resp.json()["access_token"]


# ── Auto-logout after every LOGIN test ───────────────────────
# Only applies to tests in tests/login/ — other modules manage
# their own session via module-level login fixtures

@pytest.fixture(autouse=True)
def auto_logout(page, request):
    yield
    if "test_login" not in str(request.node.fspath):
        return
    try:
        if "teamsync/home" in page.url:
            from pages.login_page import LoginPage
            lp = LoginPage(page)
            lp.logout()
    except Exception:
        from config.api_config import LOGIN_PAGE_URL
        page.goto(LOGIN_PAGE_URL)