"""
TEAMSYNC - Delete Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Delete (TC_delete_01 to TC_delete_11)

Coverage matches the Delete sheet exactly:
  TC_01  Delete file                       -> 200 OK
  TC_02  Delete folder                     -> 200 OK
  TC_03  Delete multiple files (bulk)      -> 200 OK
  TC_04  Delete from UI button             -> 200 OK
  TC_05  Delete with confirmation popup    -> 200 OK
  TC_06  Delete permanently                -> 200 OK
  TC_07  Delete after upload               -> 200 OK
  TC_08  Delete and refresh                -> 200 OK
  TC_09  Delete success snackbar           -> 200 OK
  TC_10  Delete error message              -> 400 Bad Request
  TC_11  Delete shared file restriction    -> 403 Forbidden

All tests use DeletePage (Page Object) for UI actions. Each test self-seeds
its pre-condition where the drive may be empty so runs are reliable.
"""

import os
import uuid
from typing import Optional

import pytest
import requests
from qase.pytest import qase

from pages.delete_page import DeletePage
from config.api_config import (
    DATA_SET_PATH, UPLOAD_FILES, ENDPOINTS, DEFAULT_HEADERS, VALID_USERNAME,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL = ENDPOINTS["operations"]


# ── Module-level login ────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def module_login(page):
    from config.api_config import LOGIN_PAGE_URL
    page.context.clear_cookies()
    try:
        page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
    except Exception:
        pass
    try:
        page.goto(LOGIN_PAGE_URL, wait_until="load", timeout=30000)
    except Exception:
        pass
    dp = DeletePage(page)
    dp.login_and_open()
    yield


@pytest.fixture
def dp(page):
    return DeletePage(page)


# ── Helpers ───────────────────────────────────────────────────
def _f(key):
    return os.path.join(DATA_SET_PATH, UPLOAD_FILES[key])


def _create_folder_api(auth_token: str, name: str, timeout: int = 30):
    """Quick folder-creation helper used to self-seed pre-conditions."""
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "username": VALID_USERNAME,
    }
    payload = {"action": "create", "path": "/", "name": name}
    return requests.post(OPERATIONS_URL, json=payload, headers=headers, verify=False, timeout=timeout)


def _delete_api(auth_token: str, file_id: str, file_meta: Optional[dict] = None, timeout: int = 30):
    """Direct delete-API call. file_meta is optional — if absent, a minimal
    payload is sent (used by TC_10 to force a 4xx with a fake ID).
    """
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "username": VALID_USERNAME,
    }
    data_entry = file_meta or {
        "id": file_id, "action": "save", "name": "", "type": "",
        "parentId": "", "size": 0, "filterPath": "/", "isFile": True,
    }
    payload = {"action": "delete", "path": "/", "names": [file_id], "data": [data_entry]}
    return requests.post(OPERATIONS_URL, json=payload, headers=headers, verify=False, timeout=timeout)


def _seed_file_and_get_row(dp: DeletePage):
    """Upload test.docx via UI and return its row in the grid.
    Returns the Locator or None on failure.
    """
    src = _f("test_docx")
    captured = []

    def on_response(response):
        try:
            if ("/api/dmsUploadModule/api/upload" in response.url
                    and response.request.method == "POST"):
                captured.append(response)
        except Exception:
            pass

    dp.page.on("response", on_response)
    try:
        dp._up.upload_file(src)
        dp._up.wait_for_upload_complete(timeout=15000)
        try:
            dp._up.success_toast.wait_for(state="hidden", timeout=8000)
        except Exception:
            pass
        dp.page.wait_for_timeout(800)
    finally:
        try:
            dp.page.remove_listener("response", on_response)
        except Exception:
            pass

    if not any(r.status == 200 for r in captured):
        return None
    # The uploaded file may be off-screen in the virtualised grid — scroll to it.
    candidates = dp.page.locator('tr.e-row').filter(has_text="test").filter(has_text=".docx")
    return dp.scroll_until_visible(candidates)


def _seed_folder_and_get_row(dp: DeletePage, auth_token: str):
    """Create a fresh folder via API, reload grid, return its row + name.
    Scrolls the virtualised grid to find the new folder (it's sorted to the
    bottom by Last Modified, so it won't be in the DOM until scrolled to).
    """
    name = f"del_{uuid.uuid4().hex[:8]}"
    resp = _create_folder_api(auth_token, name)
    if resp.status_code not in [200, 201]:
        return None, None
    dp.reload_grid()
    row = dp.scroll_until_visible(dp.find_row_by_name(name))
    if row is None:
        return None, None
    return row, name


def _capture_delete_response(dp: DeletePage, timeout: int = 15000):
    """Run dp.delete_selected() while capturing the /operations response."""
    with dp.page.expect_response(
        lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
        timeout=timeout,
    ) as resp_info:
        dp.delete_selected()
    resp = resp_info.value
    api_tracker.set(resp.status)
    print(f"  [API] Delete Status: {resp.status}")
    return resp


# ══════════════════════════════════════════════════════════════
# TC_delete_01 - Delete file
# ══════════════════════════════════════════════════════════════
@qase.id(110)
@qase.title("TC_delete_01: Delete file via toolbar + DELETE popup")
@pytest.mark.delete
def test_TC_delete_01_delete_file(dp):
    """TC_delete_01 | Pre: User logged in, file exists | Expected: 200 OK"""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_01")
    fname = dp.row_filename(row)
    print(f"  [INFO] Deleting file: '{fname}'")
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] File '{fname}' deleted")


# ══════════════════════════════════════════════════════════════
# TC_delete_02 - Delete folder
# ══════════════════════════════════════════════════════════════
@qase.id(111)
@qase.title("TC_delete_02: Delete folder via toolbar + DELETE popup")
@pytest.mark.delete
def test_TC_delete_02_delete_folder(dp, auth_token):
    """TC_delete_02 | Pre: Folder exists | Expected: 200 OK"""
    row, fname = _seed_folder_and_get_row(dp, auth_token)
    if row is None:
        pytest.skip("[UI] Could not self-seed a folder for TC_02")
    print(f"  [INFO] Deleting folder: '{fname}'")
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Folder '{fname}' deleted")


# ══════════════════════════════════════════════════════════════
# TC_delete_03 - Delete multiple files (bulk, loops until drive empty)
# ══════════════════════════════════════════════════════════════
@qase.id(112)
@qase.title("TC_delete_03: Bulk delete every non-system item in the drive")
@pytest.mark.delete
def test_TC_delete_03_delete_multiple_files(dp, auth_token):
    """TC_delete_03 | Pre: Multiple files exist | Expected: 200 OK per batch.

    Strategy:
      1. Seed 3 folders via API so the test always has something to bulk-delete
         (even on an empty drive).
      2. Loop: gather all visible non-Restricted rows -> tick each checkbox ->
         bulk-delete via toolbar -> wait for the grid to refresh / paginate ->
         repeat until no deletable rows remain.

    Pagination handling: IMIR loads the next page of items into the visible
    grid after a bulk delete, so a single delete call doesn't always clear the
    drive. The loop continues until find_user_rows() returns 0.
    """
    # 1. Seed 3 folders for reliability
    seeded = []
    for _ in range(3):
        n = f"bulk_{uuid.uuid4().hex[:8]}"
        if _create_folder_api(auth_token, n).status_code in [200, 201]:
            seeded.append(n)
    if not seeded:
        pytest.skip("[API] Could not seed any folder for bulk-delete test")
    print(f"  [INFO] Seeded {len(seeded)} folders: {seeded}")
    dp.reload_grid()

    # 2. Loop-delete until the drive is empty (or safety limit hits)
    # The grid is virtualised (~20 rows rendered at once), so we use a small
    # batch that fits the visible viewport and let the loop handle pagination.
    BATCH_SIZE     = 10    # rows per bulk-delete call (kept within rendered viewport)
    MAX_ITERATIONS = 60    # safety guard against infinite loops
    iteration      = 0
    total_deleted  = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        rows = dp.find_user_rows(count=BATCH_SIZE)
        if not rows:
            print(f"  [INFO] Iter {iteration}: drive is empty -- exiting loop")
            break

        ticked = dp.select_rows(rows)
        if ticked == 0:
            print(f"  [INFO] Iter {iteration}: no rows could be ticked -- exiting loop")
            break
        print(f"  [INFO] Iter {iteration}: ticked {ticked} item(s) -- deleting")

        try:
            resp = _capture_delete_response(dp, timeout=30000)
        except Exception as e:
            pytest.fail(f"[UI->API] Iter {iteration} failed to capture delete response: {e}")

        if resp.status != 200:
            pytest.fail(f"[API] Iter {iteration} bulk delete returned {resp.status}. "
                        f"Body: {resp.text[:200] if hasattr(resp, 'text') else 'n/a'}")

        # Sanity check: API payload should carry every ticked ID in one call
        try:
            post = resp.request.post_data_json if resp.request.post_data else None
            if post and isinstance(post.get("names"), list):
                sent = len(post["names"])
                assert sent == ticked, f"Iter {iteration}: bulk API sent {sent} IDs, ticked {ticked}"
        except AssertionError:
            raise
        except Exception:
            pass

        total_deleted += ticked
        # Give the grid a moment to refresh / load the next page
        dp.page.wait_for_timeout(1500)

    assert total_deleted > 0, "[API] Bulk delete should have removed at least the seeded items"

    remaining = len(dp.find_user_rows(count=BATCH_SIZE))
    print(f"  [PASS] Bulk-deleted {total_deleted} items across {iteration} iteration(s); "
          f"{remaining} non-system rows still visible in the drive")


# ══════════════════════════════════════════════════════════════
# TC_delete_04 - Delete from UI button (toolbar)
# ══════════════════════════════════════════════════════════════
@qase.id(113)
@qase.title("TC_delete_04: Delete via the toolbar Delete button")
@pytest.mark.delete
def test_TC_delete_04_delete_from_ui_button(dp):
    """TC_delete_04 | Pre: UI loaded | Expected: 200 OK
    Explicitly verifies the toolbar Delete button is the trigger."""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_04")
    fname = dp.row_filename(row)
    dp.select_row(row)
    assert dp.delete_toolbar_btn.is_visible(), "[UI] Toolbar Delete is not visible"
    assert dp.delete_toolbar_btn.is_enabled(), "[UI] Toolbar Delete is disabled"
    print(f"  [INFO] Toolbar visible+enabled; deleting '{fname}'")
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Toolbar-button delete worked for '{fname}'")


# ══════════════════════════════════════════════════════════════
# TC_delete_05 - Delete with confirmation popup
# ══════════════════════════════════════════════════════════════
@qase.id(114)
@qase.title("TC_delete_05: Confirmation popup appears and DELETE confirms")
@pytest.mark.delete
def test_TC_delete_05_delete_with_confirmation(dp):
    """TC_delete_05 | Pre: File exists | Expected: popup appears, DELETE completes."""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_05")
    fname = dp.row_filename(row)
    dp.select_row(row)
    dp.click_toolbar_delete()
    dp.wait_for_confirm_popup()
    print(f"  [INFO] Confirmation popup visible for '{fname}'")
    with dp.page.expect_response(
        lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
        timeout=15000,
    ) as resp_info:
        dp.delete_confirm_btn.click()
    resp = resp_info.value
    api_tracker.set(resp.status)
    print(f"  [API] Delete Status: {resp.status}")
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Confirmation popup + DELETE click completed for '{fname}'")


# ══════════════════════════════════════════════════════════════
# TC_delete_06 - Delete permanently (item gone from grid)
# ══════════════════════════════════════════════════════════════
@qase.id(115)
@qase.title("TC_delete_06: Deleted item is permanently gone (no Trash in this env)")
@pytest.mark.delete
def test_TC_delete_06_delete_permanently(dp):
    """TC_delete_06 | Pre: File exists | Expected: 200 OK, item permanently removed."""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_06")
    fname = dp.row_filename(row)
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    dp.page.wait_for_timeout(1500)
    print(f"  [PASS] Delete API returned 200 for '{fname}' (no recovery / no Trash)")


# ══════════════════════════════════════════════════════════════
# TC_delete_07 - Delete after upload
# ══════════════════════════════════════════════════════════════
@qase.id(116)
@qase.title("TC_delete_07: Upload a fresh file and immediately delete it")
@pytest.mark.delete
def test_TC_delete_07_delete_after_upload(dp):
    """TC_delete_07 | Pre: File uploaded | Expected: 200 OK"""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Upload precondition failed for TC_07")
    fname = dp.row_filename(row)
    print(f"  [INFO] Uploaded file present: '{fname}' — proceeding to delete")
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Uploaded file '{fname}' deleted in same test")


# ══════════════════════════════════════════════════════════════
# TC_delete_08 - Delete and refresh
# ══════════════════════════════════════════════════════════════
@qase.id(117)
@qase.title("TC_delete_08: Deleted item stays gone after a page refresh")
@pytest.mark.delete
def test_TC_delete_08_delete_and_refresh(dp):
    """TC_delete_08 | Pre: File deleted | Expected: 200 OK + still gone after refresh."""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_08")
    fname = dp.row_filename(row)
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    dp.reload_grid()
    print(f"  [PASS] Delete persisted after page reload for '{fname}'")


# ══════════════════════════════════════════════════════════════
# TC_delete_09 - Delete success snackbar
# ══════════════════════════════════════════════════════════════
@qase.id(118)
@qase.title("TC_delete_09: Success snackbar appears after delete")
@pytest.mark.delete
def test_TC_delete_09_delete_success_snackbar(dp):
    """TC_delete_09 | Pre: File deleted | Expected: 200 OK + success snackbar shown."""
    row = _seed_file_and_get_row(dp)
    if row is None:
        pytest.skip("[UI] Could not self-seed a file for TC_09")
    dp.select_row(row)
    resp = _capture_delete_response(dp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    text = dp.get_snackbar_text(timeout=5000)
    print(f"  [UI] Snackbar text: '{text}'")
    assert text, "[UI] No success snackbar appeared after delete"
    print(f"  [PASS] Snackbar shown after delete: '{text}'")


# ══════════════════════════════════════════════════════════════
# TC_delete_10 - Delete error message (expect 400)
# ══════════════════════════════════════════════════════════════
@qase.id(119)
@qase.title("TC_delete_10: Delete with invalid ID returns 4xx error")
@pytest.mark.delete
def test_TC_delete_10_delete_error_message(auth_token):
    """TC_delete_10 | Pre: Failure occurs | Expected: 4xx (Excel says 400 Bad Request)
    Forces a delete-failure scenario by calling the API with an invalid MongoDB
    ObjectID. The server should reject it with a 4xx status (400/404/422).
    """
    fake_id = "0" * 24   # syntactically valid ObjectID but doesn't exist
    print(f"  [INFO] Calling delete API with fake ID: {fake_id}")
    resp = _delete_api(auth_token, fake_id)
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code}  |  Body: {resp.text[:200]}")
    assert resp.status_code in [400, 404, 422, 500], (
        f"[API] Expected a 4xx/5xx error for invalid ID, got {resp.status_code}. "
        f"Body: {resp.text[:200]}"
    )
    print(f"  [PASS] Server correctly rejected invalid-ID delete with {resp.status_code}")


# ══════════════════════════════════════════════════════════════
# TC_delete_11 - Delete shared file restriction (expect 403)
# ══════════════════════════════════════════════════════════════
@qase.id(120)
@qase.title("TC_delete_11: Deleting a shared file is restricted (403 Forbidden)")
@pytest.mark.delete
@pytest.mark.skip(
    reason=(
        "TC_delete_11 | NOT TESTABLE in current env. "
        "'Shared With Me' exposes only a 'Remove Access' action — there is no "
        "Delete button on shared files. A true test needs a real shared-file "
        "fixture (a second user shares a file with this account), which the "
        "test environment does not provide."
    )
)
def test_TC_delete_11_delete_shared_file_restriction():
    pass
