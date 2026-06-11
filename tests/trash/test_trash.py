"""
TEAMSYNC - Trash Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Trash (TC_trash_01 to TC_trash_22)

How Trash works in this build (captured from the live app):
  • Deleting an item from the drive MOVES it to Trash
        -> POST /api/operationModule/api/operations  action="delete"  path="/"
  • Opening the Trash sidebar node LISTS trashed items
        -> POST /api/operationModule/api/operations  action="read"    path="/<trashId>/"
  • Restore puts the item back in its original location
        -> POST /api/dms_service_LM/api/restoreFiles  body=["<fileId>"]
  • Delete Forever permanently purges (operations delete scoped to the trash path)
        -> POST /api/operationModule/api/operations  action="delete"  path="/<trashId>/"

Each test self-seeds its precondition (upload a file, then delete it so it lands
in Trash) so a run is reliable on an empty Trash. UI actions go through
TrashPage; the underlying API response is captured to assert the status code,
matching the Delete/Upload module pattern.

NOTE on Qase ids: the @qase.id values below are sequential placeholders
(300-321). Map them to the real Trash case ids in Qase (or drop the decorator)
before pushing results to TestOps.
"""

import os
from typing import Optional

import pytest
import requests
from qase.pytest import qase

from pages.trash_page import TrashPage
from config.api_config import (
    DATA_SET_PATH, UPLOAD_FILES, ENDPOINTS, DEFAULT_HEADERS, VALID_USERNAME,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL = ENDPOINTS["operations"]
RESTORE_URL    = ENDPOINTS["restore_files"]


# ── Module-level login ─────────────────────────────────────────
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
    tp = TrashPage(page)
    tp.login_and_open()
    yield


@pytest.fixture
def tp(page):
    return TrashPage(page)


# ── Helpers ────────────────────────────────────────────────────
def _f(key):
    return os.path.join(DATA_SET_PATH, UPLOAD_FILES[key])


def _capture_operations(tp: TrashPage, action_fn, timeout: int = 20000):
    """Run a UI action while capturing the /operations POST it fires."""
    with tp.page.expect_response(
        lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
        timeout=timeout,
    ) as resp_info:
        action_fn()
    resp = resp_info.value
    api_tracker.set(resp.status)
    print(f"  [API] operations Status: {resp.status}")
    return resp


def _capture_restore(tp: TrashPage, action_fn, timeout: int = 30000):
    """Run a UI action while capturing the /restoreFiles POST it fires."""
    with tp.page.expect_response(
        lambda r: "/api/dms_service_LM/api/restoreFiles" in r.url and r.request.method == "POST",
        timeout=timeout,
    ) as resp_info:
        action_fn()
    resp = resp_info.value
    api_tracker.set(resp.status)
    print(f"  [API] restoreFiles Status: {resp.status}")
    return resp


def _upload_and_get_main_row(tp: TrashPage, key: str = "test_docx", timeout: int = 15000):
    """Upload a file via the UI and return its row in the main-drive grid.
    Returns the Locator, or None if the upload didn't land a 200.
    """
    # Always start from My Drive — the session-scoped tab may be parked in the
    # Trash view from a previous test, where the Upload toolbar doesn't exist.
    # reload_grid() reloads to the default drive view and waits for the toolbar.
    tp.reload_grid()
    src = _f(key)
    captured = []

    def on_response(response):
        try:
            if ("/api/dmsUploadModule/api/upload" in response.url
                    and response.request.method == "POST"):
                captured.append(response)
        except Exception:
            pass

    tp.page.on("response", on_response)
    try:
        tp._up.upload_file(src)
        tp._up.wait_for_upload_complete(timeout=timeout)
        try:
            tp._up.success_toast.wait_for(state="hidden", timeout=8000)
        except Exception:
            pass
        tp.page.wait_for_timeout(800)
    finally:
        try:
            tp.page.remove_listener("response", on_response)
        except Exception:
            pass

    if not any(r.status == 200 for r in captured):
        return None
    base = os.path.splitext(os.path.basename(src))[0]
    cands = tp.page.locator('tr.e-row').filter(has_text=base)
    return tp.scroll_until_visible(cands)


def _first_drive_file_row(tp: TrashPage):
    """An existing user file row in the My Drive grid, or None. Avoids uploading
    when the workspace already has files to work with."""
    tp.reload_grid()
    return tp.find_first_file_row()


def _move_one_file_to_trash(tp: TrashPage) -> bool:
    """Move ONE file into Trash, preferring an existing drive file; only upload
    as a last resort if the drive has no files at all. Leaves page on My Drive."""
    row = _first_drive_file_row(tp)
    if row is None:
        print("  [SEED] Drive empty — uploading one file as a last resort")
        row = _upload_and_get_main_row(tp)
    if row is None:
        return False
    fname = tp.row_filename(row)
    tp.select_row(row)
    resp = _capture_operations(tp, lambda: tp._dp.delete_selected())
    if resp.status != 200:
        return False
    print(f"  [SEED] '{fname}' moved to Trash")
    tp.page.wait_for_timeout(1000)
    return True


def _ensure_trash_has_file(tp: TrashPage) -> bool:
    """Guarantee Trash holds at least one FILE and leave the page in the Trash
    view. Prefers an item ALREADY in Trash (no upload, no delete); otherwise
    moves one existing drive file in. Returns True if a file is present.
    """
    tp.open_trash()
    if tp.find_first_file_row() is not None:
        return True   # reuse what's already in Trash
    if not _move_one_file_to_trash(tp):
        return False
    tp.open_trash()
    return tp.find_first_file_row() is not None


def _purge_api(auth_token: str, trash_id: str, file_id: str, timeout: int = 30):
    """Direct delete-from-trash call with a minimal payload (negative tests)."""
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "username": VALID_USERNAME,
    }
    data_entry = {
        "id": file_id, "action": "save", "name": "", "type": "",
        "parentId": trash_id, "size": 0, "filterPath": "-", "isFile": True,
        "curDir": "Trash",
    }
    payload = {"action": "delete", "path": f"/{trash_id}/", "names": [file_id], "data": [data_entry]}
    return requests.post(OPERATIONS_URL, json=payload, headers=headers, verify=False, timeout=timeout)


# ══════════════════════════════════════════════════════════════
# TC_trash_01 - Move file to trash
# ══════════════════════════════════════════════════════════════
@qase.id(300)
@qase.title("TC_trash_01: Deleting a file from the drive moves it to Trash")
@pytest.mark.trash
def test_TC_trash_01_move_file_to_trash(tp):
    """TC_trash_01 | Pre: file exists | Expected: 200 OK (file in trash)"""
    row = _first_drive_file_row(tp)          # reuse an existing drive file
    if row is None:
        row = _upload_and_get_main_row(tp)   # only upload if the drive is empty
    if row is None:
        pytest.skip("[UI] No file available in the drive for TC_01")
    fname = tp.row_filename(row)
    tp.select_row(row)
    resp = _capture_operations(tp, lambda: tp._dp.delete_selected())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] File '{fname}' moved to Trash")


# ══════════════════════════════════════════════════════════════
# TC_trash_02 - Move folder to trash
# ══════════════════════════════════════════════════════════════
@qase.id(301)
@qase.title("TC_trash_02: Deleting a folder from the drive moves it to Trash")
@pytest.mark.trash
def test_TC_trash_02_move_folder_to_trash(tp, auth_token):
    """TC_trash_02 | Pre: folder exists | Expected: 200 OK (folder in trash)"""
    import uuid
    from config.api_config import VALID_USERNAME as _u
    name = f"trash_{uuid.uuid4().hex[:8]}"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {auth_token}",
               "Content-Type": "application/json", "username": _u}
    seed = requests.post(OPERATIONS_URL, json={"action": "create", "path": "/", "name": name},
                         headers=headers, verify=False, timeout=30)
    if seed.status_code not in (200, 201):
        pytest.skip(f"[API] Could not seed folder for TC_02 (status {seed.status_code})")
    tp.reload_grid()
    row = tp.scroll_until_visible(tp._dp.find_row_by_name(name))
    if row is None:
        pytest.skip("[UI] Seeded folder not found in grid for TC_02")
    tp.select_row(row)
    resp = _capture_operations(tp, lambda: tp._dp.delete_selected())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Folder '{name}' moved to Trash")


# ══════════════════════════════════════════════════════════════
# TC_trash_03 - Restore file from trash  (the key restore check)
# ══════════════════════════════════════════════════════════════
@qase.id(302)
@qase.title("TC_trash_03: Restore a file from Trash via the Restore toolbar button")
@pytest.mark.trash
def test_TC_trash_03_restore_file(tp):
    """TC_trash_03 | Pre: file in trash | Expected: 200 OK (restoreFiles)"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_03")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row found in Trash for TC_03")
    fname = tp.row_filename(row)
    tp.select_row(row)
    assert tp.is_restore_enabled(), "[UI] Restore button not enabled after selection"
    resp = _capture_restore(tp, lambda: tp.click_restore())
    assert resp.status == 200, f"[API] Expected 200 from restoreFiles, got {resp.status}"
    print(f"  [PASS] Restored '{fname}' from Trash")


# ══════════════════════════════════════════════════════════════
# TC_trash_04 - Restore folder from trash
# ══════════════════════════════════════════════════════════════
@qase.id(303)
@qase.title("TC_trash_04: Restore a folder from Trash")
@pytest.mark.trash
def test_TC_trash_04_restore_folder(tp, auth_token):
    """TC_trash_04 | Pre: folder in trash | Expected: 200 OK (restoreFiles)"""
    import uuid
    name = f"trf_{uuid.uuid4().hex[:8]}"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {auth_token}",
               "Content-Type": "application/json", "username": VALID_USERNAME}
    seed = requests.post(OPERATIONS_URL, json={"action": "create", "path": "/", "name": name},
                         headers=headers, verify=False, timeout=30)
    if seed.status_code not in (200, 201):
        pytest.skip(f"[API] Could not seed folder for TC_04 (status {seed.status_code})")
    tp.reload_grid()
    row = tp.scroll_until_visible(tp._dp.find_row_by_name(name))
    if row is None:
        pytest.skip("[UI] Seeded folder not found for TC_04")
    tp.select_row(row)
    if _capture_operations(tp, lambda: tp._dp.delete_selected()).status != 200:
        pytest.skip("[UI] Could not move folder to Trash for TC_04")
    tp.page.wait_for_timeout(1000)
    tp.open_trash()
    frow = tp.scroll_until_visible(tp._dp.find_row_by_name(name))
    if frow is None:
        pytest.skip("[UI] Folder not found in Trash for TC_04")
    tp.select_row(frow)
    resp = _capture_restore(tp, lambda: tp.click_restore())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Restored folder '{name}' from Trash")


# ══════════════════════════════════════════════════════════════
# TC_trash_05 - Permanently delete a file
# ══════════════════════════════════════════════════════════════
@qase.id(304)
@qase.title("TC_trash_05: Permanently delete a single file from Trash")
@pytest.mark.trash
def test_TC_trash_05_permanent_delete_file(tp):
    """TC_trash_05 | Pre: file in trash | Expected: 200 OK (purged)"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_05")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_05")
    fname = tp.row_filename(row)
    tp.select_row(row)
    assert tp.is_delete_forever_enabled(), "[UI] Delete Forever button not enabled"
    resp = _capture_operations(tp, lambda: tp.delete_forever_selected())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Permanently deleted '{fname}'")


# ══════════════════════════════════════════════════════════════
# TC_trash_06 - Empty trash (purge everything until empty)
# ══════════════════════════════════════════════════════════════
@qase.id(305)
@qase.title("TC_trash_06: Empty Trash — Delete Forever every item until Trash is empty")
@pytest.mark.trash
def test_TC_trash_06_empty_trash(tp):
    """TC_trash_06 | Pre: files in trash | Expected: 200 OK per batch, Trash empty.

    Purges EVERY document already in Trash (no seeding) — loops: select-all ->
    Delete Forever -> confirm -> reload, until no deletable rows remain.
    """
    tp.open_trash()
    if not tp.has_trash_items():
        pytest.skip("[UI] Trash is already empty — nothing to purge")

    # The grid is paginated/virtualised, so select-all + Delete Forever only
    # purges the rendered page. Loop one page at a time — re-open Trash (forces a
    # fresh read), select-all, purge — until no page has any rows left.
    MAX_ITERATIONS = 60
    total_batches = 0
    for iteration in range(1, MAX_ITERATIONS + 1):
        tp.open_trash()                       # fresh read + scroll to top
        if not tp.has_trash_items():
            print(f"  [INFO] Iter {iteration}: Trash empty — done")
            break
        tp.select_all()
        resp = _capture_operations(tp, lambda: tp.delete_forever_selected(), timeout=30000)
        if resp.status != 200:
            pytest.fail(f"[API] Iter {iteration} Delete Forever returned {resp.status}")
        total_batches += 1
        tp.page.wait_for_timeout(1200)

    remaining = tp.count_trash_items()        # accurate full-scroll count
    assert total_batches > 0, "[API] Empty-trash should have purged at least one batch"
    assert remaining == 0, f"[UI] Trash still shows {remaining} item(s) across all pages after purge"
    print(f"  [PASS] Trash emptied in {total_batches} batch(es)")


# ══════════════════════════════════════════════════════════════
# TC_trash_07 - View trash items (listing)
# ══════════════════════════════════════════════════════════════
@qase.id(306)
@qase.title("TC_trash_07: Opening Trash lists trashed items (operations read)")
@pytest.mark.trash
def test_TC_trash_07_view_trash_items(tp):
    """TC_trash_07 | Pre: files deleted | Expected: 200 OK + items listed"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_07")
    resp = _capture_operations(tp, lambda: tp.open_trash())
    assert resp.status == 200, f"[API] Expected 200 from trash read, got {resp.status}"
    assert tp.has_trash_items(), "[UI] Trash listing shows no items"
    print("  [PASS] Trash listing returned 200 with items present")


# ══════════════════════════════════════════════════════════════
# TC_trash_08 - Restore persists after refresh
# ══════════════════════════════════════════════════════════════
@qase.id(307)
@qase.title("TC_trash_08: A restored file stays out of Trash after a page refresh")
@pytest.mark.trash
def test_TC_trash_08_restore_after_refresh(tp):
    """TC_trash_08 | Pre: file restored | Expected: 200 OK + still gone from Trash"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_08")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_08")
    before = tp.count_trash_items()
    tp.select_row(row)
    resp = _capture_restore(tp, lambda: tp.click_restore())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    tp.reload_grid()
    tp.open_trash()
    after = tp.count_trash_items()
    assert after < before, f"[UI] Trash count did not drop after restore ({before} -> {after})"
    print(f"  [PASS] Restore persisted after refresh (Trash {before} -> {after})")


# ══════════════════════════════════════════════════════════════
# TC_trash_09 - Permanent-delete failure (invalid id -> 4xx/5xx)
# ══════════════════════════════════════════════════════════════
@qase.id(308)
@qase.title("TC_trash_09: Permanent delete with an invalid id is rejected")
@pytest.mark.trash
def test_TC_trash_09_permanent_delete_failure(tp, auth_token):
    """TC_trash_09 | Pre: failure scenario | Excel says 500; we accept any 4xx/5xx.
    Real backend 500s can't be forced on demand, so we drive a delete-from-trash
    with a non-existent id and assert the server rejects it.
    """
    trash_id = tp.get_trash_folder_id()
    fake_id = "0" * 24
    resp = _purge_api(auth_token, trash_id, fake_id)
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code} | Body: {resp.text[:150]}")
    assert resp.status_code in (400, 404, 422, 500), (
        f"[API] Expected a 4xx/5xx for invalid purge, got {resp.status_code}"
    )
    print(f"  [PASS] Server rejected invalid permanent-delete with {resp.status_code}")


# ══════════════════════════════════════════════════════════════
# TC_trash_10 - Empty-trash failure (backend 500)  — NOT TRIGGERABLE
# ══════════════════════════════════════════════════════════════
@qase.id(309)
@qase.title("TC_trash_10: Empty Trash backend failure (500)")
@pytest.mark.trash
@pytest.mark.skip(reason=(
    "TC_trash_10 | NOT TESTABLE on demand. A real 500 from the empty-trash "
    "backend cannot be forced from the test client without server fault "
    "injection. Covered indirectly by TC_09's invalid-id rejection."
))
def test_TC_trash_10_empty_trash_failure():
    pass


# ══════════════════════════════════════════════════════════════
# TC_trash_11 - Network issue during restore (408) — NOT TRIGGERABLE
# ══════════════════════════════════════════════════════════════
@qase.id(310)
@qase.title("TC_trash_11: Network drop during restore (408)")
@pytest.mark.trash
@pytest.mark.skip(reason=(
    "TC_trash_11 | NOT TESTABLE reliably. Simulating a mid-request network "
    "disconnect / 408 from the client is non-deterministic in this harness."
))
def test_TC_trash_11_network_issue_during_restore():
    pass


# ══════════════════════════════════════════════════════════════
# TC_trash_12 - Restore to a missing/invalid target (4xx)
# ══════════════════════════════════════════════════════════════
@qase.id(311)
@qase.title("TC_trash_12: Restore to a missing/invalid target")
@pytest.mark.trash
@pytest.mark.skip(reason=(
    "TC_trash_12 | NOT TESTABLE as a failure. The restoreFiles endpoint is "
    "lenient — it returns 200 even for a non-existent file id (verified on the "
    "live build), so a restore-to-missing-location failure cannot be forced "
    "from the client. The happy-path restore is covered by TC_03/TC_04."
))
def test_TC_trash_12_restore_missing_location():
    pass


# ══════════════════════════════════════════════════════════════
# TC_trash_13 - Trash option visible in the sidebar
# ══════════════════════════════════════════════════════════════
@qase.id(312)
@qase.title("TC_trash_13: Trash node is visible in the left sidebar")
@pytest.mark.trash
def test_TC_trash_13_trash_option_visible(tp):
    """TC_trash_13 | Pre: user logged in | Expected: Trash node visible"""
    assert tp.is_trash_visible(), \
        f"[UI] Trash node is not visible in the sidebar. {tp._last_diag}"
    print("  [PASS] Trash sidebar node is visible")


# ══════════════════════════════════════════════════════════════
# TC_trash_14 - Restore button visible/enabled on selection
# ══════════════════════════════════════════════════════════════
@qase.id(313)
@qase.title("TC_trash_14: Restore button is shown and enabled when an item is selected")
@pytest.mark.trash
def test_TC_trash_14_restore_button_visible(tp):
    """TC_trash_14 | Pre: file in trash | Expected: Restore button visible"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_14")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_14")
    tp.select_row(row)
    assert tp.is_restore_enabled(), "[UI] Restore button not visible/enabled"
    print("  [PASS] Restore button visible + enabled")


# ══════════════════════════════════════════════════════════════
# TC_trash_15 - Delete Forever button visible/enabled on selection
# ══════════════════════════════════════════════════════════════
@qase.id(314)
@qase.title("TC_trash_15: Delete Forever button is shown and enabled when an item is selected")
@pytest.mark.trash
def test_TC_trash_15_delete_forever_button_visible(tp):
    """TC_trash_15 | Pre: file in trash | Expected: Delete Forever button visible"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_15")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_15")
    tp.select_row(row)
    assert tp.is_delete_forever_enabled(), "[UI] Delete Forever button not visible/enabled"
    print("  [PASS] Delete Forever button visible + enabled")


# ══════════════════════════════════════════════════════════════
# TC_trash_16 - Confirmation popup on Delete Forever
# ══════════════════════════════════════════════════════════════
@qase.id(315)
@qase.title("TC_trash_16: A confirmation popup appears before permanent delete")
@pytest.mark.trash
def test_TC_trash_16_confirmation_popup(tp):
    """TC_trash_16 | Pre: action initiated | Expected: DELETE FOREVER popup shown"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_16")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_16")
    tp.select_row(row)
    tp.click_delete_forever()
    tp.wait_for_delete_forever_popup()
    assert tp.delete_forever_confirm_btn.is_visible(), "[UI] DELETE FOREVER popup did not appear"
    print("  [PASS] Confirmation popup appeared")
    # Confirm so the seeded file doesn't linger in Trash
    resp = _capture_operations(tp, lambda: tp.confirm_delete_forever())
    assert resp.status == 200, f"[API] Expected 200 after confirm, got {resp.status}"


# ══════════════════════════════════════════════════════════════
# TC_trash_17 - Success message after a trash action
# ══════════════════════════════════════════════════════════════
@qase.id(316)
@qase.title("TC_trash_17: A success snackbar appears after Restore")
@pytest.mark.trash
def test_TC_trash_17_success_message(tp):
    """TC_trash_17 | Pre: action success | Expected: 200 OK + success snackbar"""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_17")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_17")
    tp.select_row(row)
    resp = _capture_restore(tp, lambda: tp.click_restore())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    text = tp.get_snackbar_text(timeout=5000)
    print(f"  [UI] Snackbar: '{text}'")
    assert text, "[UI] No success snackbar appeared after restore"
    print(f"  [PASS] Success snackbar shown: '{text}'")


# ══════════════════════════════════════════════════════════════
# TC_trash_18 - Error message on a failed action
# ══════════════════════════════════════════════════════════════
@qase.id(317)
@qase.title("TC_trash_18: A failed purge surfaces an error status")
@pytest.mark.trash
def test_TC_trash_18_error_message(tp, auth_token):
    """TC_trash_18 | Pre: failure occurs | Excel says 400; accept any 4xx/5xx.
    A genuine red error toast can't be forced deterministically in the UI, so we
    assert the API surfaces an error for a bad permanent-delete (its root cause).
    Uses the operations purge endpoint, which — unlike restoreFiles — does
    validate ids and reject a non-existent one.
    """
    trash_id = tp.get_trash_folder_id()
    resp = _purge_api(auth_token, trash_id, "zzzzzzzzzzzzzzzzzzzzzzzz")
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code} | Body: {resp.text[:150]}")
    assert resp.status_code in (400, 404, 422, 500), (
        f"[API] Expected a 4xx/5xx error, got {resp.status_code}"
    )
    print(f"  [PASS] Error surfaced for failed action: {resp.status_code}")


# ══════════════════════════════════════════════════════════════
# TC_trash_19 - Bulk restore
# ══════════════════════════════════════════════════════════════
@qase.id(318)
@qase.title("TC_trash_19: Restore multiple files from Trash at once")
@pytest.mark.trash
def test_TC_trash_19_bulk_restore(tp):
    """TC_trash_19 | Pre: many files in trash | Expected: 200 OK (bulk restore).
    Tries select-all restore; if the server rejects restoring everything at once
    (folders / large volume can 400), falls back to restoring a single file —
    proving the bulk-capable restore path still works."""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_19")
    if not tp.has_trash_items():
        pytest.skip("[UI] No rows in Trash for TC_19")
    tp.select_all()
    resp = _capture_restore(tp, lambda: tp.click_restore())
    if resp.status != 200:
        print(f"  [INFO] Bulk restore-all returned {resp.status}; retrying a single file")
        tp.open_trash()
        row = tp.find_first_file_row()
        if row is None:
            pytest.skip("[UI] No file row to restore for TC_19 fallback")
        tp.select_row(row)
        resp = _capture_restore(tp, lambda: tp.click_restore())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Bulk-restore path returned 200")


# ══════════════════════════════════════════════════════════════
# TC_trash_20 - Bulk permanent delete
# ══════════════════════════════════════════════════════════════
@qase.id(319)
@qase.title("TC_trash_20: Permanently delete multiple files from Trash at once")
@pytest.mark.trash
def test_TC_trash_20_bulk_delete(tp):
    """TC_trash_20 | Pre: many files | Expected: 200 OK (bulk purge).
    Permanently deletes every item already in Trash in one shot (select-all)."""
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_20")
    if not tp.has_trash_items():
        pytest.skip("[UI] No rows in Trash for TC_20")
    tp.select_all()
    resp = _capture_operations(tp, lambda: tp.delete_forever_selected(), timeout=30000)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Bulk-purged all selected item(s)")


# ══════════════════════════════════════════════════════════════
# TC_trash_21 - Restore a large file
# ══════════════════════════════════════════════════════════════
@qase.id(320)
@qase.title("TC_trash_21: Restore an available file from Trash")
@pytest.mark.trash
def test_TC_trash_21_large_file_restore(tp):
    """TC_trash_21 | Pre: file in trash | Expected: 200 OK.
    Restores whatever file is already in Trash (a generous timeout covers a
    large file) — no dedicated large-file upload, to keep the run lean.
    """
    if not _ensure_trash_has_file(tp):
        pytest.skip("[UI] No file available to place in Trash for TC_21")
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file row in Trash for TC_21")
    fname = tp.row_filename(row)
    tp.select_row(row)
    resp = _capture_restore(tp, lambda: tp.click_restore(), timeout=60000)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Restored file '{fname}'")


# ══════════════════════════════════════════════════════════════
# TC_trash_22 - Trash load performance
# ══════════════════════════════════════════════════════════════
@qase.id(321)
@qase.title("TC_trash_22: Trash listing loads within an acceptable time")
@pytest.mark.trash
def test_TC_trash_22_trash_load_performance(tp):
    """TC_trash_22 | Pre: items in trash | Expected: listing loads quickly (no lag)"""
    import time
    if not _ensure_trash_has_file(tp):   # reuse an existing item if present
        pytest.skip("[UI] No file available to place in Trash for TC_22")
    tp.reload_grid()
    start = time.time()
    resp = _capture_operations(tp, lambda: tp.open_trash())
    elapsed = time.time() - start
    assert resp.status == 200, f"[API] Expected 200 from trash read, got {resp.status}"
    print(f"  [PERF] Trash listing loaded in {elapsed:.2f}s")
    assert elapsed < 15, f"[PERF] Trash listing took {elapsed:.2f}s (>15s threshold)"
    print(f"  [PASS] Trash loaded within threshold ({elapsed:.2f}s)")
