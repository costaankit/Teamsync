# """
# conftest.py — TEAMSYNC Project
# Configures Playwright browser and base settings for all tests.
# """
 
# import pytest
# from playwright.sync_api import sync_playwright
 
 
# # This file is automatically picked up by pytest.
# # Playwright fixtures (page, browser, context) are provided
# # by the pytest-playwright plugin — no extra setup needed here.
 
# # ── Global settings ──────────────────────────────────────────
# def pytest_configure(config):
#     config.addinivalue_line(
#         "markers", "ui: marks tests as UI/browser tests"
#     )
#     config.addinivalue_line(
#         "markers", "api: marks tests as API tests"
#     )
"""
conftest.py — TEAMSYNC Project
Configures Playwright browser, report generation, and base settings.
"""
 
import os
import pytest
import requests
from datetime import datetime
 
 
# ── Auto-create reports folder ───────────────────────────────
# Creates reports/ folder automatically before every test run
# Without this — pytest crashes if reports/ folder is missing
os.makedirs("reports", exist_ok=True)
 
 
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
        "markers", "ui: marks tests as UI/browser tests (Playwright)"
    )
    config.addinivalue_line(
        "markers", "api: marks tests as API tests (requests)"
    )
 
 
# ── Shared API client fixture ─────────────────────────────────
class ApiClient:
    """Wraps requests with clean error handling for all API tests."""
 
    def post(self, url, **kwargs):
        try:
            response = requests.post(url, timeout=10, **kwargs)
            return response
        except requests.exceptions.ConnectionError:
            pytest.fail(f"Cannot connect to server. Is the app running?\nURL: {url}")
        except requests.exceptions.Timeout:
            pytest.fail(f"Request timed out after 10 seconds.\nURL: {url}")
        except requests.exceptions.SSLError:
            pytest.fail(f"SSL certificate error.\nURL: {url}")
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
 
 
# ── Shared browser session across all UI tests ───────────────
# Overrides pytest-playwright defaults so the browser opens once
# and stays open for the entire test run (no close/reopen per test).
 
@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {**browser_type_launch_args, "headless": False}
 
@pytest.fixture(scope="session")
def context(browser):
    ctx = browser.new_context()
    yield ctx
    ctx.close()
 
@pytest.fixture(scope="session")
def page(context):
    pg = context.new_page()
    yield pg
    pg.close()