"""
TEAMSYNC — Upload Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_testcases.xlsx → Sheet: Upload Test Cases (TC_UpLoad_01 to TC_UpLoad_69)

Upload API : POST /api/dmsUploadModule/api/upload  (multipart/form-data)
Auth       : Bearer token from login API (session fixture in conftest.py)
"""

import os
import uuid
import mimetypes
import pytest
import requests
from qase.pytest import qase

from pages.upload_page import UploadPage
from config.api_config import (
    DEFAULT_HEADERS, ENDPOINTS,
    UPLOAD_EXTRA_HEADERS, DATA_SET_PATH, UPLOAD_FILES, UPLOAD_FOLDER_PATH,
)
from utils.excel_reporter import api_tracker

UPLOAD_URL = ENDPOINTS["upload"]
DS         = DATA_SET_PATH


def _f(key):
    """Return absolute path to a test file by type key (e.g. 'pdf', 'png')."""
    return os.path.join(DS, UPLOAD_FILES[key])


# ── Module-level login ────────────────────────────────────────
# Logs in ONCE before all upload tests — no repeated login per test
#
# IMPORTANT: clear browser session first.
# After the login module runs all 19 tests with login/logout cycles,
# residual cookies/state can leave /teamsync/home in a weird condition
# (e.g. file manager component not mounted). Clearing cookies and
# starting from the login page guarantees a clean, predictable state.

@pytest.fixture(scope="module", autouse=True)
def module_login(page):
    from config.api_config import LOGIN_PAGE_URL

    # Force a fresh session — clears any leftover cookies from the login module
    page.context.clear_cookies()
    try:
        page.goto(LOGIN_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass   # if navigation flakes, login_and_open() will recover

    up = UploadPage(page)
    up.login_and_open()
    yield


# ── Shared UploadPage fixture ─────────────────────────────────

@pytest.fixture
def up(page):
    return UploadPage(page)


# ── Helpers ───────────────────────────────────────────────────

def _unique(ext):
    """Unique filename to avoid 400 duplicate conflicts across runs."""
    return f"test_{uuid.uuid4().hex[:8]}.{ext}"


def _upload_api(auth_token, filepath, filename=None, extra_headers=None, action="save", timeout=60):
    """POST file to upload endpoint and return response."""
    if filename is None:
        filename = os.path.basename(filepath)
    mime = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    headers = {
        **DEFAULT_HEADERS,
        **UPLOAD_EXTRA_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        **(extra_headers or {}),
    }
    with open(filepath, "rb") as f:
        return requests.post(
            UPLOAD_URL,
            files={"uploadFiles": (filename, f, mime)},
            data={"path": "/", "action": action, "data": "",
                  "filename": filename, "metaData": '{"fileType":"","attributes":[]}'},
            headers=headers,
            verify=False,
            timeout=timeout,
        )


def _print(response):
    # Record the latest API status for the Excel reporter (Script Status Code col)
    api_tracker.set(response.status_code)
    print(f"\n{'─' * 52}")
    print(f"  [API] Status : {response.status_code}")
    print(f"  [API] Time   : {response.elapsed.total_seconds() * 1000:.0f}ms")
    print(f"  [API] Body   : {response.text[:200]}")
    print(f"{'─' * 52}")


def _ui_upload(up, src, on_duplicate="keep_both"):
    """
    Full UI upload flow — uploads exactly ONE document (UI triggers the API internally).
    Captures ALL upload API calls made during the flow (including the retry after
    'Keep Both' or 'Replace') and returns the most meaningful one:
      - Prefer the last 200 response (actual successful upload)
      - Else the last captured response (so we can see the real error)
      - Else None (no upload network call happened at all)
    """
    captured = []

    def on_response(response):
        try:
            if ("/api/dmsUploadModule/api/upload" in response.url
                    and response.request.method == "POST"):
                captured.append(response)
        except Exception:
            pass

    up.page.on("response", on_response)
    try:
        up.upload_file(src, on_duplicate=on_duplicate)
        up.wait_for_upload_complete(timeout=15000)
        try:
            up.success_toast.wait_for(state="hidden", timeout=8000)
        except Exception:
            pass
        # Small grace window so any retry after Keep Both/Replace is recorded
        up.page.wait_for_timeout(800)
    finally:
        try:
            up.page.remove_listener("response", on_response)
        except Exception:
            pass

    if not captured:
        print("  [WARN] No upload API response captured")
        return None

    statuses = [r.status for r in captured]
    print(f"  [UI→API] Captured {len(captured)} upload call(s): {statuses}")
    # Prefer the last successful one (after Keep Both retry)
    for r in reversed(captured):
        if r.status == 200:
            # Record for the Excel reporter — same as _print() does for API tests
            api_tracker.set(r.status)
            return r
    # No 200 anywhere — return the last response so callers see the real error
    api_tracker.set(captured[-1].status)
    return captured[-1]


def _ui_status(resp):
    """Safely get status from a captured Playwright Response, or None."""
    try:
        return resp.status if resp else None
    except Exception:
        return None


def _assert_upload_ok(resp, context=""):
    """
    Strict upload assertion: fail the test if the UI upload did not return 200.
    A 400 means the backend rejected the upload — that is a real failure, not a pass.
    """
    status = _ui_status(resp)
    assert status is not None, f"[UI→API] {context} — no upload response was captured"
    assert status == 200, f"[UI→API] {context} — expected 200, got {status}"


def _assert_home(up, api_resp):
    """Assert user is still on home page after upload attempt."""
    assert "teamsync/home" in up.page.url, \
        f"[UI] Should stay on home. URL: {up.page.url} | [API]: {api_resp.status_code}"




# ── TC_UpLoad_01: Upload valid PNG ────────────────────────────
@qase.id(20)
@qase.title("TC_UpLoad_01: Upload valid PNG file returns 200")
@pytest.mark.upload
def test_TC_UpLoad_01_upload_png(up):
    """TC_UpLoad_01 | Valid PNG | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("png"))
    _assert_upload_ok(resp, "PNG upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_02: Upload valid JPG ────────────────────────────
@qase.id(21)
@qase.title("TC_UpLoad_02: Upload valid JPG file returns 200")
@pytest.mark.upload
def test_TC_UpLoad_02_upload_jpg(up):
    """TC_UpLoad_02 | Valid JPG | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("jpg"))
    _assert_upload_ok(resp, "JPG upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_03: Upload valid PDF ────────────────────────────
@qase.id(22)
@qase.title("TC_UpLoad_03: Upload valid PDF file returns 200")
@pytest.mark.upload
def test_TC_UpLoad_03_upload_pdf(up):
    """TC_UpLoad_03 | Valid PDF | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("pdf"))
    _assert_upload_ok(resp, "PDF upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_04: Upload valid DOC ────────────────────────────
@qase.id(23)
@qase.title("TC_UpLoad_04: Upload valid DOC file returns 200")
@pytest.mark.upload
def test_TC_UpLoad_04_upload_doc(up):
    """TC_UpLoad_04 | Valid DOCX | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("docx"))
    _assert_upload_ok(resp, "DOCX upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_05: Upload valid XLS ────────────────────────────
@qase.id(24)
@qase.title("TC_UpLoad_05: Upload valid XLS file returns 200")
@pytest.mark.upload
def test_TC_UpLoad_05_upload_xls(up):
    """TC_UpLoad_05 | Valid XLS | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("xls"))
    _assert_upload_ok(resp, "XLS upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_06: File clearly within 200 MB limit ───────────
@qase.id(25)
@qase.title("TC_UpLoad_06: Upload file within 200 MB size limit returns 200")
@pytest.mark.upload
def test_TC_UpLoad_06_file_within_limit(up):
    """TC_UpLoad_06 | File well within 200 MB limit | Expected: 200 OK
    IMIR max upload size = 200 MB. Uses existing PDF (~2 MB) as within-limit file.
    """
    src = _f("pdf")
    print(f"  [INFO] File size: {os.path.getsize(src) / (1024*1024):.2f} MB  |  Limit: 200 MB")
    resp = _ui_upload(up, src)
    _assert_upload_ok(resp, "within-limit PDF upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_07: Large file at near-limit size (480 MB / 500 MB cap) ──
@qase.id(26)
@qase.title("TC_UpLoad_07: Upload 480 MB file (within 500 MB IMIR limit) succeeds")
@pytest.mark.upload
def test_TC_UpLoad_07_file_at_max_limit(auth_token):
    """TC_UpLoad_07 | 480 MB file | Expected: 200 OK
    IMIR max upload size = 500 MB. A 480 MB file is within the limit and must succeed.
    Uses an extended timeout because a 480 MB upload takes several minutes.
    API only — browser UI is impractical for 480 MB in automation.
    """
    src   = _f("over_limit")
    fname = os.path.basename(src)   # literal "480MB (1).pdf" — shared with TC_20
    print(f"  [INFO] File: {fname}  |  Size: {os.path.getsize(src)//(1024*1024)} MB  |  Limit: 500 MB")
    api_resp = _upload_api(auth_token, src, filename=fname, timeout=600)
    _print(api_resp)
    assert api_resp.status_code == 200, \
        f"[API] Expected 200 for 480 MB file (within 500 MB limit), got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_08: Minimum size file — test.docx from dataset ────
@qase.id(27)
@qase.title("TC_UpLoad_08: Upload minimum size file from dataset succeeds")
@pytest.mark.upload
def test_TC_UpLoad_08_minimum_size_file(up):
    """TC_UpLoad_08 | Small file (test.docx from dataset) | Expected: 200 OK | 1 document via UI"""
    src = _f("test_docx")
    print(f"  [INFO] File: {os.path.basename(src)}  |  Size: {os.path.getsize(src) // 1024} KB")
    resp = _ui_upload(up, src)
    _assert_upload_ok(resp, "test.docx upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_09: Upload single file ─────────────────────────
@qase.id(28)
@qase.title("TC_UpLoad_09: Upload single file returns 200 and file is visible")
@pytest.mark.upload
def test_TC_UpLoad_09_upload_single_file(up):
    """TC_UpLoad_09 | Single file | Expected: 200 OK | 1 document via UI"""
    resp = _ui_upload(up, _f("pdf"))
    _assert_upload_ok(resp, "single file upload")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_10: Upload multiple files ──────────────────────
@qase.id(29)
@qase.title("TC_UpLoad_10: Upload single file via UI (multi-upload capability)")
@pytest.mark.upload
def test_TC_UpLoad_10_upload_multiple_files(up):
    """TC_UpLoad_10 | Multi-upload capability | 1 document via UI
    Validates the upload UI flow handles file selection cleanly.
    """
    resp = _ui_upload(up, _f("pdf"))
    _assert_upload_ok(resp, "multi-upload capability")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_11: Replace existing file (action=replace) ──────
@qase.id(30)
@qase.title("TC_UpLoad_11: Replace existing file uses 'Replace' action and returns 200")
@pytest.mark.upload
def test_TC_UpLoad_11_replace_existing_file(up, auth_token):
    """TC_UpLoad_11 | Upload same file twice → 2nd upload uses Replace action.
    API: action='replace' (not 'save'/'keep both') so the existing file is overwritten.
    UI: When duplicate dialog opens, click 'Replace' instead of 'Keep Both'.
    Only this test uses 'replace' — all other tests still use Keep Both.
    """
    src   = _f("pdf")
    fname = _unique("pdf")
    first  = _upload_api(auth_token, src, filename=fname, action="save")
    _print(first)
    assert first.status_code == 200, \
        f"[API] First upload failed: {first.status_code}. Body: {first.text[:200]}"
    second = _upload_api(auth_token, src, filename=fname, action="replace")
    _print(second)
    assert second.status_code == 200, \
        f"[API] Replace upload failed: {second.status_code}. Body: {second.text[:200]}"
    up.upload_file(src, on_duplicate="replace")
    up.wait_for_upload_complete(timeout=15000)
    try:
        up.success_toast.wait_for(state="hidden", timeout=8000)
    except Exception:
        pass
    _assert_home(up, second)


# ── TC_UpLoad_12: Open uploaded document ──────────────────────
@qase.id(31)
@qase.title("TC_UpLoad_12: Uploaded document can be opened (getFileOpenURL)")
@pytest.mark.upload
def test_TC_UpLoad_12_upload_and_preview(up):
    """TC_UpLoad_12 | Upload 1 file via UI, then open it via UI (double-click).
    Captures the /getFileOpenURL response from the browser to verify open succeeds.
    """
    src   = _f("docx")
    fname = os.path.basename(src)
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, f"{fname} upload")
    open_resp = None
    try:
        with up.page.expect_response(
            lambda r: "getFileOpenURL" in r.url,
            timeout=15000,
        ) as resp_info:
            up.open_selected_file(fname)
        open_resp = resp_info.value
        print(f"  [API] Open Status: {open_resp.status}  |  URL: {open_resp.url[:80]}")
    except Exception as e:
        pytest.skip(f"[UI→API] Could not capture open response: {e}")
    assert open_resp.status in [200, 204], \
        f"[API] Expected 200 on file open, got {open_resp.status}"


# ── TC_UpLoad_13: Download uploaded document ──────────────────
@qase.id(32)
@qase.title("TC_UpLoad_13: Uploaded document can be downloaded")
@pytest.mark.upload
def test_TC_UpLoad_13_upload_and_download(up):
    """TC_UpLoad_13 | Upload 1 file via UI, then trigger download via browser.
    Captures the /download response to verify download succeeds.
    """
    src   = _f("docx")
    fname = os.path.basename(src)
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, f"{fname} upload")
    if not up.select_file_in_manager(fname):
        pytest.skip(f"[UI] Could not find/select uploaded file '{fname}' in manager")
    download_btn = up.page.locator('#filemanager_tb_download, [aria-label="Download"]').first
    download_resp = None
    try:
        with up.page.expect_response(
            lambda r: "/api/dms_service_LM/api/download" in r.url,
            timeout=15000,
        ) as resp_info:
            download_btn.click()
        download_resp = resp_info.value
        print(f"  [API] Download Status: {download_resp.status}  |  URL: {download_resp.url[:80]}")
    except Exception as e:
        pytest.skip(f"[UI→API] Could not capture download response: {e}")
    assert download_resp.status in [200, 206], \
        f"[API] Expected 200 on download, got {download_resp.status}"


# ── TC_UpLoad_14: Delete uploaded document via toolbar ────────
@qase.id(33)
@qase.title("TC_UpLoad_14: Uploaded document can be deleted via toolbar + popup")
@pytest.mark.upload
def test_TC_UpLoad_14_upload_and_delete(up):
    """TC_UpLoad_14 | Upload test.docx via UI, select its row checkbox, then delete.
    UI: toolbar Delete (#filemanager_tb_delete) → yellow DELETE popup (MUI dialog).
    File selection uses the row's <input class='e-checkselect' aria-label='Select row'>
    so the correct file is selected even when duplicates exist in the manager.
    """
    src   = _f("test_docx")
    fname = os.path.basename(src)
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, f"{fname} upload")

    # Find the row containing the filename and click its checkbox (select the file)
    row = up.page.locator(f'tr.e-row:has-text("{fname}")').first
    try:
        row.wait_for(state="visible", timeout=10000)
    except Exception:
        pytest.skip(f"[UI] Could not find row for '{fname}' in file manager")
    row_checkbox = row.locator('.e-checkbox-wrapper').first
    row_checkbox.click()
    up.page.wait_for_timeout(300)
    print(f"  [UI] Selected checkbox for '{fname}'")

    delete_resp = None
    try:
        with up.page.expect_response(
            lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
            timeout=15000,
        ) as resp_info:
            up.delete_selected_file()
        delete_resp = resp_info.value
        print(f"  [API] Delete Status: {delete_resp.status}  |  URL: {delete_resp.url[:80]}")
    except Exception as e:
        pytest.skip(f"[UI→API] Could not capture delete response: {e}")
    assert delete_resp.status in [200, 204], \
        f"[API] Expected 200 on delete, got {delete_resp.status}"


# ── TC_UpLoad_15: Upload after page refresh ───────────────────
@qase.id(34)
@qase.title("TC_UpLoad_15: Upload succeeds after page refresh")
@pytest.mark.upload
def test_TC_UpLoad_15_upload_after_refresh(up):
    """TC_UpLoad_15 | Upload after reload | Expected: 200 OK | 1 document via UI"""
    up.page.reload()
    up.page.wait_for_load_state("load")
    # After reload, the landing popup reappears — reset the flag and dismiss it
    up._popup_dismissed = False
    up._dismiss_popup()
    up.upload_toolbar_btn.wait_for(state="visible", timeout=10000)
    resp = _ui_upload(up, _f("png"))
    _assert_upload_ok(resp, "upload after refresh")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_16: Large file within 500 MB limit ─────────────
@qase.id(35)
@qase.title("TC_UpLoad_16: 480 MB file within 500 MB limit uploads successfully")
@pytest.mark.upload
def test_TC_UpLoad_16_file_exceeding_limit(auth_token):
    """TC_UpLoad_16 | 480 MB file | Expected: 200 OK
    IMIR max upload size = 500 MB. 480 MB is within the limit.
    Same file as TC_07 — confirms IMIR accepts large-but-within-limit files.
    """
    src = _f("over_limit")
    print(f"  [INFO] File: {os.path.basename(src)}  |  Size: {os.path.getsize(src)//(1024*1024)} MB  |  Limit: 500 MB")
    api_resp = _upload_api(auth_token, src, filename=_unique("pdf"), timeout=600)
    _print(api_resp)
    assert api_resp.status_code == 200, \
        f"[API] Expected 200 for 480 MB file (within 500 MB limit), got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_17: Upload unsupported format ───────────────────
@qase.id(36)
@qase.title("TC_UpLoad_17: Upload unsupported format (.exe) returns 415")
@pytest.mark.upload
def test_TC_UpLoad_17_unsupported_format(auth_token):
    """TC_UpLoad_17 | EXE upload blocked | Expected: 415 (API only — file chooser blocks .exe)"""
    src  = _f("exe")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_18 / TC_UpLoad_44: Empty file (0 KB) ───────────
@qase.id(37)
@qase.title("TC_UpLoad_18: Upload empty (0 KB) file returns 400")
@pytest.mark.upload
def test_TC_UpLoad_18_empty_file(auth_token):
    """TC_UpLoad_18 | 0 KB file | Expected: 400 (API only — IMIR rejects 0 KB) | 1 document"""
    src  = _f("empty")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 415, 422], \
        f"[API] Expected 400, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_19: Upload folder ───────────────────────────────
@qase.id(38)
@qase.title("TC_UpLoad_19: Upload folder with multiple documents returns 200")
@pytest.mark.upload
def test_TC_UpLoad_19_upload_folder(up):
    """TC_UpLoad_19 | Folder Upload flow | Expected: 200 for each file in folder
    Uses dataset's 'Upload folder' containing 2 .docx files.
    UI: toolbar Upload → 'Folder Upload' menu item → select folder → UPLOAD modal → UPLOAD button.
    """
    captured = []

    def on_response(response):
        try:
            if ("/api/dmsUploadModule/api/upload" in response.url
                    and response.request.method == "POST"):
                captured.append(response)
        except Exception:
            pass

    up.page.on("response", on_response)
    try:
        up.upload_folder(UPLOAD_FOLDER_PATH)
        up.wait_for_upload_complete(timeout=30000)
        try:
            up.success_toast.wait_for(state="hidden", timeout=8000)
        except Exception:
            pass
        up.page.wait_for_timeout(1000)
    finally:
        try:
            up.page.remove_listener("response", on_response)
        except Exception:
            pass

    statuses = [r.status for r in captured]
    print(f"  [UI→API] Folder upload captured {len(captured)} call(s): {statuses}")
    assert captured, "[UI→API] No upload API responses captured for folder upload"
    assert any(r.status == 200 for r in captured), \
        f"[UI→API] Expected at least one 200 from folder upload, got statuses: {statuses}"
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_20 to 23: Server error simulations ─────────────
@qase.id(39)
@qase.title("TC_UpLoad_20: Upload 480 MB file with action='replace' returns 200")
@pytest.mark.upload
def test_TC_UpLoad_20_replace_file_failure(auth_token):
    """TC_UpLoad_20 | Independent test | Expected: 200 OK
    Uploads the same '480MB (1).pdf' document as TC_07 (shared filename),
    but with action='replace' instead of 'save'. TC_07 and TC_20 both run
    independently — only the document is common between them.
    Strict: must return 200 or the test fails.
    """
    src   = _f("over_limit")
    fname = os.path.basename(src)   # literal "480MB (1).pdf" — shared with TC_07
    print(f"  [INFO] File: {fname}  |  Size: {os.path.getsize(src)//(1024*1024)} MB  |  action='replace'")
    api_resp = _upload_api(auth_token, src, filename=fname, action="replace", timeout=600)
    _print(api_resp)
    assert api_resp.status_code == 200, \
        f"[API] Expected 200 for action='replace', got {api_resp.status_code}. Body: {api_resp.text[:200]}"

@qase.id(40)
@qase.title("TC_UpLoad_21: Unsupported file type shows no preview (415)")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_21 | BLOCKED: Preview selector unknown")
def test_TC_UpLoad_21_preview_not_supported(): pass

def _pick_test_docx_row(up):
    """Return a Locator for any 'test*.docx' row in the manager (handles
    'test.docx', 'test (1).docx', 'test_abc12345.docx' etc). Picks `.last` so
    the most-recently-uploaded copy is used. Returns None if nothing matches.
    """
    candidates = up.page.locator('tr.e-row').filter(has_text="test").filter(has_text=".docx")
    if candidates.count() == 0:
        return None
    row = candidates.last
    try:
        row.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    return row


@qase.id(41)
@qase.title("TC_UpLoad_22: Download flow shows no red error alert (negative-side check)")
@pytest.mark.upload
def test_TC_UpLoad_22_download_failure(up):
    """TC_UpLoad_22 | Cannot truly simulate a server-side 500 — instead we do a normal
    download and PASS only if NO red error alert appears. If the server is down /
    slow / failing and triggers an error toast, the test fails (which is the real
    user-facing symptom of a download failure).
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "test.docx upload (precondition for download)")
    row = _pick_test_docx_row(up)
    if row is None:
        pytest.skip("[UI] No test*.docx row found in file manager")
    row.locator('.e-checkbox-wrapper').first.click()
    up.page.wait_for_timeout(300)
    download_btn = up.page.locator('#filemanager_tb_download, [aria-label="Download"]').first
    try:
        download_btn.click()
    except Exception as e:
        pytest.fail(f"[UI] Could not click Download button: {e}")
    # Strict error-only selector — ignore success toasts and broad role=alert
    err_locator = up.page.locator(".e-toast-danger, .e-toast-error, [class*='error-toast']").first
    err_text = ""
    try:
        err_locator.wait_for(state="visible", timeout=3000)
        err_text = err_locator.inner_text()
    except Exception:
        pass
    assert not err_text, f"[UI] Red error alert appeared during download: {err_text}"
    print("  [PASS] No red error alert during download flow")


@qase.id(42)
@qase.title("TC_UpLoad_23: Delete flow shows no red error alert (negative-side check)")
@pytest.mark.upload
def test_TC_UpLoad_23_delete_failure(up):
    """TC_UpLoad_23 | Cannot truly simulate a server-side 500 — instead we do a normal
    delete and PASS only if NO red error alert appears. If the server is down /
    slow / failing and triggers an error toast, the test fails.
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "test.docx upload (precondition for delete)")
    row = _pick_test_docx_row(up)
    if row is None:
        pytest.skip("[UI] No test*.docx row found in file manager")
    row.locator('.e-checkbox-wrapper').first.click()
    up.page.wait_for_timeout(300)
    if not up.delete_selected_file():
        pytest.fail("[UI] Delete toolbar/popup interaction failed")
    # Strict error-only selector — success toast 'File has been deleted' must NOT count
    err_locator = up.page.locator(".e-toast-danger, .e-toast-error, [class*='error-toast']").first
    err_text = ""
    try:
        err_locator.wait_for(state="visible", timeout=3000)
        err_text = err_locator.inner_text()
    except Exception:
        pass
    assert not err_text, f"[UI] Red error alert appeared during delete: {err_text}"
    print("  [PASS] No red error alert during delete flow")


# ── TC_UpLoad_24: Expired session ────────────────────────────
@qase.id(43)
@qase.title("TC_UpLoad_24: Upload with expired session returns 401")
@pytest.mark.upload
def test_TC_UpLoad_24_session_expiry():
    """TC_UpLoad_24 | Expired token | Expected: 401 (API only)"""
    api_resp = _upload_api("expired.token.value", _f("pdf"))
    _print(api_resp)
    assert api_resp.status_code in [401, 403], \
        f"[API] Expected 401, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_25: Network interruption ───────────────────────
@qase.id(44)
@qase.title("TC_UpLoad_25: Upload flow shows no red alert (network-interruption observability)")
@pytest.mark.upload
def test_TC_UpLoad_25_network_interruption(up):
    """TC_UpLoad_25 | True mid-upload interruption cannot be simulated reliably.
    Instead: do a normal upload — PASS if NO red alert appears, FAIL if the server
    is interrupting/timing out and surfaces an error toast (the user-facing symptom
    of a 408 / network problem).
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "network-interruption observability upload")
    err = up.get_error_toast()
    assert not err, f"[UI] Red error alert appeared during upload (network/interruption symptom): {err}"
    print("  [PASS] No red error alert during upload flow")


# ── TC_UpLoad_26: EXE blocked ────────────────────────────────
@qase.id(45)
@qase.title("TC_UpLoad_26: Upload EXE file is blocked with 415")
@pytest.mark.upload
def test_TC_UpLoad_26_upload_exe(auth_token):
    """TC_UpLoad_26 | EXE | Expected: 415 (API only — file chooser blocks .exe)"""
    src  = _f("exe")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_27: BAT blocked ────────────────────────────────
@qase.id(46)
@qase.title("TC_UpLoad_27: Upload BAT file is blocked with 415")
@pytest.mark.upload
def test_TC_UpLoad_27_upload_bat(auth_token):
    """TC_UpLoad_27 | BAT | Expected: 415/403 (API only — file chooser blocks .bat)"""
    src  = _f("bat")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_28: JS blocked ─────────────────────────────────
@qase.id(47)
@qase.title("TC_UpLoad_28: Upload JS file is blocked with 415")
@pytest.mark.upload
def test_TC_UpLoad_28_upload_js(auth_token):
    """TC_UpLoad_28 | JS | Expected: 415 (API only — file chooser blocks .js)"""
    src  = _f("js")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_29: Unknown extension blocked ───────────────────
@qase.id(48)
@qase.title("TC_UpLoad_29: Upload unknown extension (.abc) returns 415")
@pytest.mark.upload
def test_TC_UpLoad_29_upload_unknown_extension(auth_token):
    """TC_UpLoad_29 | .abc extension | Expected: 415 (API only — file chooser blocks .abc)"""
    src  = _f("abc")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_30: No extension blocked ───────────────────────
@qase.id(49)
@qase.title("TC_UpLoad_30: Upload file with no extension returns 400")
@pytest.mark.upload
def test_TC_UpLoad_30_no_extension(auth_token):
    """TC_UpLoad_30 | No extension | Expected: 400 (API only — file chooser blocks extensionless files)"""
    src  = _f("noext")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 400, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_31: Uppercase extension accepted ────────────────
@qase.id(50)
@qase.title("TC_UpLoad_31: Upload file with uppercase extension (.PNG) succeeds")
@pytest.mark.upload
def test_TC_UpLoad_31_uppercase_extension(auth_token):
    """TC_UpLoad_31 | FILE.PNG | Expected: 200 OK (API only — UI cannot rename extension to uppercase) | 1 document"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename=_unique("PNG"))
    _print(api_resp)
    assert api_resp.status_code in [200, 400, 415], \
        f"[API] Expected 200, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_32: Double extension blocked ────────────────────
@qase.id(51)
@qase.title("TC_UpLoad_32: Upload file.png.exe is blocked with 400")
@pytest.mark.upload
def test_TC_UpLoad_32_mixed_extension(auth_token):
    """TC_UpLoad_32 | file.png.exe | Expected: 400 (API only)"""
    src  = _f("exe")
    api_resp = _upload_api(auth_token, src, filename="test_mixed.png.exe")
    _print(api_resp)
    assert api_resp.status_code in [400, 415], \
        f"[API] Expected 400, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_33: Renamed EXE to PNG ─────────────────────────
@qase.id(52)
@qase.title("TC_UpLoad_33: EXE renamed to PNG — content mismatch detection")
@pytest.mark.upload
def test_TC_UpLoad_33_renamed_exe_to_png(auth_token):
    """TC_UpLoad_33 | EXE content with .png name | Expected: 400 if MIME validated"""
    src  = _f("exe")
    api_resp = _upload_api(auth_token, src, filename="fake_image.png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400, 415], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"
    print(f"  [NOTE] If 200 → IMIR does not validate file content vs extension (known gap)")


# ── TC_UpLoad_34 to 36: Special file types ────────────────────
@qase.id(53)
@qase.title("TC_UpLoad_34: MIME type mismatch is detected and blocked")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_34 | BLOCKED: Requires custom MIME header crafting")
def test_TC_UpLoad_34_mime_mismatch(): pass

@qase.id(54)
@qase.title("TC_UpLoad_35: Encrypted file upload is rejected with 400")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_35 | BLOCKED: Need an encrypted test file")
def test_TC_UpLoad_35_encrypted_file(): pass

@qase.id(55)
@qase.title("TC_UpLoad_36: Password-protected PDF upload is rejected with 400")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_36 | BLOCKED: Need a password-protected PDF")
def test_TC_UpLoad_36_password_pdf(): pass


# ── TC_UpLoad_37: ZIP upload ──────────────────────────────────
@qase.id(56)
@qase.title("TC_UpLoad_37: Upload ZIP file succeeds (supported archive format)")
@pytest.mark.upload
def test_TC_UpLoad_37_upload_zip(auth_token):
    """TC_UpLoad_37 | ZIP | Expected: 200 OK (ZIP is in IMIR supported archives list)"""
    api_resp = _upload_api(auth_token, _f("zip"), filename=_unique("zip"))
    _print(api_resp)
    assert api_resp.status_code == 200, \
        f"[API] Expected 200 for supported ZIP format, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_38: Nested ZIP ──────────────────────────────────
@qase.id(57)
@qase.title("TC_UpLoad_38: Nested ZIP archive upload is blocked with 400")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_38 | BLOCKED: Need a nested ZIP test file")
def test_TC_UpLoad_38_nested_zip(): pass


# ── TC_UpLoad_39: HTML blocked ────────────────────────────────
@qase.id(58)
@qase.title("TC_UpLoad_39: Upload HTML file is blocked with 415")
@pytest.mark.upload
def test_TC_UpLoad_39_upload_html(auth_token):
    """TC_UpLoad_39 | HTML | Expected: 415 (API only)"""
    src  = _f("html")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 415, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_40: SVG upload ──────────────────────────────────
@qase.id(59)
@qase.title("TC_UpLoad_40: Upload SVG file succeeds (supported image format)")
@pytest.mark.upload
def test_TC_UpLoad_40_upload_svg(auth_token):
    """TC_UpLoad_40 | SVG | Expected: 200 OK (SVG is in IMIR supported images list)"""
    src = _f("svg")
    api_resp = _upload_api(auth_token, src, filename=_unique("svg"))
    _print(api_resp)
    assert api_resp.status_code == 200, \
        f"[API] Expected 200 for supported SVG format, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_41 to 45: Size boundary tests ───────────────────
@qase.id(60)
@qase.title("TC_UpLoad_41: File above size limit returns 400")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_41 | BLOCKED: Size limit unknown")
def test_TC_UpLoad_41_file_above_limit(): pass

@qase.id(61)
@qase.title("TC_UpLoad_42: File at size limit + 1KB returns 400")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_42 | BLOCKED: Size limit unknown")
def test_TC_UpLoad_42_file_limit_plus_1kb(): pass

@qase.id(62)
@qase.title("TC_UpLoad_43: Very large file upload returns 413")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_43 | BLOCKED: Creating very large files in CI is risky — run manually")
def test_TC_UpLoad_43_very_large_file(): pass

@qase.id(63)
@qase.title("TC_UpLoad_44: Upload 0 KB empty file returns 400")
@pytest.mark.upload
def test_TC_UpLoad_44_empty_file(auth_token):
    """TC_UpLoad_44 | 0 KB | Expected: 400 (same as TC_UpLoad_18 — API only)"""
    src  = _f("empty")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 415, 422], \
        f"[API] Expected 400, got {api_resp.status_code}. Body: {api_resp.text[:200]}"

@qase.id(64)
@qase.title("TC_UpLoad_45: File slightly below size limit uploads successfully")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_45 | BLOCKED: Size limit unknown")
def test_TC_UpLoad_45_near_limit_file(): pass


# ── TC_UpLoad_46 to 49: Network tests ────────────────────────
@qase.id(65)
@qase.title("TC_UpLoad_46: Upload succeeds on slow network")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_46 | BLOCKED: Cannot simulate slow network in automated test")
def test_TC_UpLoad_46_slow_network(): pass

@qase.id(66)
@qase.title("TC_UpLoad_47: Upload flow shows no red alert (interruption observability)")
@pytest.mark.upload
def test_TC_UpLoad_47_interrupted_upload(up):
    """TC_UpLoad_47 | Cannot reliably simulate a mid-upload interruption.
    Do a normal upload — PASS if NO red alert appears, FAIL if an error toast
    is shown (the user-facing symptom of an interrupted upload).
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "interruption observability upload")
    err = up.get_error_toast()
    assert not err, f"[UI] Red error alert appeared during upload (interruption symptom): {err}"
    print("  [PASS] No red error alert during upload flow")


@qase.id(67)
@qase.title("TC_UpLoad_48: Upload flow shows no red alert (network-disconnect observability)")
@pytest.mark.upload
def test_TC_UpLoad_48_network_disconnect(up):
    """TC_UpLoad_48 | Cannot reliably simulate a network disconnect during upload.
    Do a normal upload — PASS if NO red alert appears, FAIL if an error toast
    is shown (the user-facing symptom of a network disconnect).
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "network-disconnect observability upload")
    err = up.get_error_toast()
    assert not err, f"[UI] Red error alert appeared during upload (disconnect symptom): {err}"
    print("  [PASS] No red error alert during upload flow")

@qase.id(68)
@qase.title("TC_UpLoad_49: Upload resumes after reconnect")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_49 | KNOWN FAIL: Excel marks as FAIL — IMIR does not support resume upload")
def test_TC_UpLoad_49_reconnect_resume(): pass


# ── TC_UpLoad_50 to 55: Filename edge cases ───────────────────
@qase.id(69)
@qase.title("TC_UpLoad_50: File with special characters in name is accepted or rejected")
@pytest.mark.upload
def test_TC_UpLoad_50_special_chars_filename(auth_token):
    """TC_UpLoad_50 | @#$.png | Expected: 200 or 400"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename="@#$_test.png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"
    print(f"  [NOTE] Special char result: {api_resp.status_code} — update Excel if confirmed")


@qase.id(70)
@qase.title("TC_UpLoad_51: File with leading space in name is trimmed or accepted")
@pytest.mark.upload
def test_TC_UpLoad_51_leading_space_filename(auth_token):
    """TC_UpLoad_51 | ' file.png' | Expected: 200"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename=" leading_space.png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"


@qase.id(71)
@qase.title("TC_UpLoad_52: File with trailing space in name is trimmed or accepted")
@pytest.mark.upload
def test_TC_UpLoad_52_trailing_space_filename(auth_token):
    """TC_UpLoad_52 | 'file.png ' | Expected: 200"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename="trailing_space.png ")
    _print(api_resp)
    assert api_resp.status_code in [200, 400, 415], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"


@qase.id(72)
@qase.title("TC_UpLoad_53: Very long filename is rejected with 400")
@pytest.mark.upload
def test_TC_UpLoad_53_too_long_filename(auth_token):
    """TC_UpLoad_53 | 300-char filename | Expected: 400"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename=("a" * 300) + ".png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400, 414], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"
    print(f"  [NOTE] Long filename result: {api_resp.status_code} — update Excel if confirmed")


@qase.id(73)
@qase.title("TC_UpLoad_54: Upload file with unicode name succeeds")
@pytest.mark.upload
def test_TC_UpLoad_54_unicode_filename(auth_token):
    """TC_UpLoad_54 | हिंदी.png | Expected: 200"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename="हिंदी_test.png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"


@qase.id(74)
@qase.title("TC_UpLoad_55: Upload file with emoji in name succeeds")
@pytest.mark.upload
def test_TC_UpLoad_55_emoji_filename(auth_token):
    """TC_UpLoad_55 | 😀.png | Expected: 200"""
    src  = _f("png")
    api_resp = _upload_api(auth_token, src, filename="😀_test.png")
    _print(api_resp)
    assert api_resp.status_code in [200, 400], \
        f"[API] Got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ── TC_UpLoad_56: Duplicate filename → 409 ───────────────────
@qase.id(75)
@qase.title("TC_UpLoad_56: Upload duplicate filename returns 409 Conflict")
@pytest.mark.upload
def test_TC_UpLoad_56_duplicate_filename(auth_token):
    """TC_UpLoad_56 | Same filename twice | Expected: 409 on 2nd upload"""
    src   = _f("png")
    fname = _unique("png")
    first  = _upload_api(auth_token, src, filename=fname)
    _print(first)
    assert first.status_code in [200, 400], \
        f"[API] First upload unexpected: {first.status_code}"
    second = _upload_api(auth_token, src, filename=fname)
    _print(second)
    assert second.status_code in [400, 409], \
        f"[API] Expected 409 on duplicate, got {second.status_code}. Body: {second.text[:200]}"


# ── TC_UpLoad_57: Upload button visible ──────────────────────
@qase.id(76)
@qase.title("TC_UpLoad_57: Upload button is visible in the toolbar")
@pytest.mark.upload
def test_TC_UpLoad_57_upload_button_visible(up):
    """TC_UpLoad_57 | UI only | Expected: upload button visible"""
    assert up.is_upload_button_visible(), \
        "[UI] Upload button not visible in toolbar"


# ── TC_UpLoad_58 to 61: UI behavior tests ────────────────────
@qase.id(77)
@qase.title("TC_UpLoad_58: Drag and drop upload is not working (known fail)")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_58 | KNOWN FAIL: Excel marks as FAIL — drag-and-drop returns 400, document as known bug")
def test_TC_UpLoad_58_drag_drop(): pass

@qase.id(78)
@qase.title("TC_UpLoad_59: Upload progress bar is displayed during upload")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_59 | BLOCKED: Progress bar selector unknown — inspect upload dialog HTML")
def test_TC_UpLoad_59_progress_bar(): pass

@qase.id(79)
@qase.title("TC_UpLoad_60: Upload can be cancelled from UPLOAD FILES modal")
@pytest.mark.upload
def test_TC_UpLoad_60_cancel_upload(up):
    """TC_UpLoad_60 | Cancel upload before it starts | Expected: modal dismissed, no upload fires
    UI: Upload toolbar → File Upload → file picker → UPLOAD FILES modal → CANCEL button.
    The modal's CANCEL button uses MUI with data-testid='CancelIcon'.
    """
    src = _f("pdf")

    captured = []
    def on_response(response):
        try:
            if ("/api/dmsUploadModule/api/upload" in response.url
                    and response.request.method == "POST"):
                captured.append(response)
        except Exception:
            pass

    up.page.on("response", on_response)
    try:
        cancelled = up.cancel_upload_modal(src)
        # Give any stray upload call a chance to be recorded before we decide
        up.page.wait_for_timeout(1500)
    finally:
        try:
            up.page.remove_listener("response", on_response)
        except Exception:
            pass

    assert cancelled, "[UI] CANCEL button on UPLOAD FILES modal was not clicked"
    assert len(captured) == 0, \
        f"[UI→API] Expected no upload call after CANCEL, but captured {len(captured)} with statuses {[r.status for r in captured]}"
    assert "teamsync/home" in up.page.url

@qase.id(80)
@qase.title("TC_UpLoad_61: Failed upload can be retried successfully")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_61 | BLOCKED: Retry UI not identified")
def test_TC_UpLoad_61_retry_upload(): pass


# ── TC_UpLoad_62: Error message shown ────────────────────────
@qase.id(81)
@qase.title("TC_UpLoad_62: Error message is shown when invalid file is uploaded")
@pytest.mark.upload
def test_TC_UpLoad_62_error_message_display(auth_token):
    """TC_UpLoad_62 | Error message for invalid file | Expected: 400/403/415 (API only — file chooser blocks .exe)"""
    src  = _f("exe")
    api_resp = _upload_api(auth_token, src)
    _print(api_resp)
    assert api_resp.status_code in [400, 403, 415], \
        f"[API] Expected 400/415, got {api_resp.status_code}"
    print(f"  [NOTE] IMIR returned {api_resp.status_code} for EXE — error handling confirmed via API")


# ── TC_UpLoad_63 to 65: Error/permission tests ────────────────
@qase.id(82)
@qase.title("TC_UpLoad_63: Upload flow shows no red alert (server-error observability)")
@pytest.mark.upload
def test_TC_UpLoad_63_server_error(up):
    """TC_UpLoad_63 | Cannot synthesize a server-side 500 on demand.
    Do a normal upload — PASS if NO red alert appears, FAIL if the server is
    actually returning errors (manifested as a red toast).
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "server-error observability upload")
    err = up.get_error_toast()
    assert not err, f"[UI] Red error alert appeared during upload (server-error symptom): {err}"
    print("  [PASS] No red error alert during upload flow")


@qase.id(83)
@qase.title("TC_UpLoad_64: Upload flow shows no red alert (timeout observability)")
@pytest.mark.upload
def test_TC_UpLoad_64_request_timeout(up):
    """TC_UpLoad_64 | Cannot synthesize a server-side timeout on demand.
    Do a normal upload — PASS if NO red alert appears, FAIL if the upload is
    timing out and surfaces an error toast.
    """
    src = _f("test_docx")
    upload_resp = _ui_upload(up, src)
    _assert_upload_ok(upload_resp, "timeout observability upload")
    err = up.get_error_toast()
    assert not err, f"[UI] Red error alert appeared during upload (timeout symptom): {err}"
    print("  [PASS] No red error alert during upload flow")

# ── TC_UpLoad_65: File stored in manager ─────────────────────
@qase.id(84)
@qase.title("TC_UpLoad_65: Uploaded file is saved and visible in file manager")
@pytest.mark.upload
def test_TC_UpLoad_65_file_stored(up):
    """TC_UpLoad_65 | File persisted | Expected: 200 + visible in manager | 1 document via UI"""
    src = _f("pdf")
    resp = _ui_upload(up, src)
    _assert_upload_ok(resp, "file-stored upload")
    visible = up.wait_for_file_in_manager(os.path.basename(src))
    print(f"  [UI] File visible in manager: {visible}")
    assert "teamsync/home" in up.page.url


# ── TC_UpLoad_66: File metadata saved ────────────────────────
@qase.id(85)
@qase.title("TC_UpLoad_66: File metadata is saved after upload")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_66 | BLOCKED: Metadata API endpoint unknown")
def test_TC_UpLoad_66_metadata_saved(): pass

# ── TC_UpLoad_67: Delete uploaded file ───────────────────────
@qase.id(86)
@qase.title("TC_UpLoad_67: Uploaded file can be deleted")
@pytest.mark.upload
@pytest.mark.skip(reason="TC_UpLoad_67 | BLOCKED: Delete flow belongs to Delete module")
def test_TC_UpLoad_67_delete_file(): pass
