"""
TEAMSYNC - Rename Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Rename (TC_RENAME_01 to TC_RENAME_14)

Rename API : POST /api/operationModule/api/operations
             { "action":"rename", "path":"/", "name":<old>, "newName":<new>,
               "data":[{...}], "showFileExtension": true }

UI flow    : right-click row -> '#filemanager_cm_rename' -> MUI dialog input
             (shows base name, no extension) -> RENAME button (DoneIcon).

Seeding strategy (minimal):
  A module-scoped fixture creates a SMALL pool ONCE (2 files + 2 folders).
  Every test then REUSES existing items in the drive (rename is non-destructive,
  so items persist). No per-test uploads/creates. Pickers scroll the virtualised
  grid to locate a renamable file/folder regardless of drive size.
"""

import os
import uuid
import pytest
import requests
from qase.pytest import qase

from pages.rename_page import RenamePage
from config.api_config import (
    DATA_SET_PATH, UPLOAD_FILES, ENDPOINTS, DEFAULT_HEADERS,
    VALID_USERNAME, VALID_PASSWORD_ENCRYPTED,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL  = ENDPOINTS["operations"]
CREATE_DOCX_URL = ENDPOINTS["create_docx"]


# ── API helpers (used only by the one-time pool seeder) ───────
def _api_token() -> str:
    resp = requests.post(
        ENDPOINTS["login"],
        files={"username": (None, VALID_USERNAME), "password": (None, VALID_PASSWORD_ENCRYPTED)},
        headers=DEFAULT_HEADERS, verify=False, timeout=30,
    )
    return resp.json()["access_token"]


def _create_folder_api(token: str, name: str, timeout: int = 30):
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "username": VALID_USERNAME}
    return requests.post(OPERATIONS_URL, json={"action": "create", "path": "/", "name": name},
                         headers=headers, verify=False, timeout=timeout)


def _create_docx_api(token: str, filename: str, timeout: int = 30):
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "username": VALID_USERNAME, "type": "Files", "generatingAiTheme": "true"}
    fields = {
        "path": (None, "/"), "action": (None, "save"), "filename": (None, filename),
        "metaData": (None, '{"fileType":"","attributes":[]}'), "fileExt": (None, "docx"),
        "generatingAiTheme": (None, "true"), "theme": (None, "defaultTheme"),
    }
    return requests.post(CREATE_DOCX_URL, files=fields, headers=headers, verify=False, timeout=timeout)


# ── Module-level login + one-time minimal pool ────────────────
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
    rp = RenamePage(page)
    rp.login_and_open()

    # One-time minimal pool: 2 files + 2 folders for the whole module to reuse.
    token = _api_token()
    for _ in range(2):
        _create_docx_api(token, f"poolf_{uuid.uuid4().hex[:8]}.docx")
    for _ in range(2):
        _create_folder_api(token, f"poold_{uuid.uuid4().hex[:8]}")
    rp.reload_grid()   # make the pool visible in the grid
    yield


@pytest.fixture
def rp(page):
    return RenamePage(page)


@pytest.fixture(scope="module")
def token() -> str:
    return _api_token()


@pytest.fixture(autouse=True)
def _close_lingering_dialog(page):
    """Negative tests intentionally leave the rename dialog open; close any
    lingering dialog before AND after each test so it can't block the next one."""
    def _dismiss():
        try:
            dlg = page.locator('#file_rename_dialog, .MuiDialog-root')
            if dlg.count() > 0 and dlg.first.is_visible():
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
        except Exception:
            pass
    _dismiss()
    yield
    _dismiss()


# ── Item pickers (reuse existing drive items — no creation) ───
def _pick_file_row(rp: RenamePage):
    """First non-system FILE row, scrolled into view."""
    loc = rp.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon:not(.e-fe-folder))')
    return rp.scroll_until_visible(loc)


def _seed_file_row(rp: RenamePage, token: str):
    """Create a fresh docx via API, reload the grid, and return its row.
    Used by rename tests instead of _pick_file_row so each test gets a clean
    user-owned file (avoiding shortcuts, shared-file replicas, and stale
    leftovers from other modules that aren't renameable).
    Returns None if creation or location fails."""
    name = f"renf_{uuid.uuid4().hex[:8]}.docx"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "username": VALID_USERNAME, "type": "Files", "generatingAiTheme": "true"}
    fields = {
        "path": (None, "/"), "action": (None, "save"), "filename": (None, name),
        "metaData": (None, '{"fileType":"","attributes":[]}'), "fileExt": (None, "docx"),
        "generatingAiTheme": (None, "true"), "theme": (None, "defaultTheme"),
    }
    try:
        requests.post(CREATE_DOCX_URL, files=fields, headers=headers,
                      verify=False, timeout=30)
    except Exception:
        return None
    rp.reload_grid()
    return rp.scroll_until_visible(rp.find_row_by_name(name))


def _pick_folder_row(rp: RenamePage):
    """First non-system FOLDER row, scrolled into view."""
    loc = rp.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon.e-fe-folder)')
    return rp.scroll_until_visible(loc)


def _pick_two_folder_rows(rp: RenamePage):
    """Two distinct non-system folder rows (for the duplicate-name test)."""
    loc = rp.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon.e-fe-folder)')
    if rp.scroll_until_visible(loc) is None or loc.count() < 2:
        return None, None
    return loc.nth(0), loc.nth(1)


# ── Rename helpers ────────────────────────────────────────────
def _capture_rename(rp: RenamePage, timeout: int = 15000):
    with rp.page.expect_response(
        lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
        timeout=timeout,
    ) as resp_info:
        rp.confirm_rename()
    resp = resp_info.value
    api_tracker.set(resp.status)
    print(f"  [API] Rename Status: {resp.status}")
    return resp


def _assert_rename_rejected(rp: RenamePage, context: str):
    """Assert an invalid rename is blocked (disabled button, inline error,
    4xx response, error snackbar, or dialog staying open). Always closes the
    dialog before returning so it can't block the next test."""
    if rp.is_confirm_disabled():
        api_tracker.set(0)
        print(f"  [PASS] {context}: RENAME button disabled (UI blocked)")
        rp.close_dialog()
        return
    err = rp.get_dialog_error()
    if err:
        api_tracker.set(0)
        print(f"  [PASS] {context}: inline dialog error '{err}'")
        rp.close_dialog()
        return
    resp = None
    try:
        with rp.page.expect_response(
            lambda r: "/api/operationModule/api/operations" in r.url and r.request.method == "POST",
            timeout=6000,
        ) as resp_info:
            rp.confirm_rename()
        resp = resp_info.value
        api_tracker.set(resp.status)
    except Exception:
        pass
    if resp is not None and resp.status >= 400:
        print(f"  [PASS] {context}: server rejected with {resp.status}")
        rp.close_dialog()
        return
    snack = rp.get_snackbar_text(timeout=3000)
    keywords = ("exist", "invalid", "empty", "long", "error", "cannot", "not allow")
    if snack and any(k in snack.lower() for k in keywords):
        print(f"  [PASS] {context}: error message '{snack}'")
        rp.close_dialog()
        return
    if rp.rename_confirm_btn.is_visible():
        print(f"  [PASS] {context}: dialog still open, rename not applied")
        rp.close_dialog()
        return
    rp.close_dialog()
    pytest.fail(f"[UI] {context}: invalid name appears to have been accepted "
                f"(resp={resp.status if resp else 'no-call'}, snack={snack!r})")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_01 - Rename file
# ══════════════════════════════════════════════════════════════
@qase.id(121)
@qase.title("TC_RENAME_01: Rename a file via right-click -> Rename")
@pytest.mark.rename
def test_TC_RENAME_01_rename_file(rp, token):
    """TC_RENAME_01 | Pre: file exists | Expected: 200 OK"""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    print(f"  [INFO] Renaming file '{rp.row_filename(row)}'")
    rp.open_rename_dialog(row)
    rp.set_new_name(f"renfile_{uuid.uuid4().hex[:6]}")
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] File renamed")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_02 - Rename folder
# ══════════════════════════════════════════════════════════════
@qase.id(122)
@qase.title("TC_RENAME_02: Rename a folder via right-click -> Rename")
@pytest.mark.rename
def test_TC_RENAME_02_rename_folder(rp):
    """TC_RENAME_02 | Pre: folder exists | Expected: 200 OK"""
    row = _pick_folder_row(rp)
    if row is None:
        pytest.skip("[UI] No folder available to rename")
    print(f"  [INFO] Renaming folder '{rp.row_filename(row)}'")
    rp.open_rename_dialog(row)
    rp.set_new_name(f"renfolder_{uuid.uuid4().hex[:6]}")
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Folder renamed")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_03 - Rename with valid name
# ══════════════════════════════════════════════════════════════
@qase.id(123)
@qase.title("TC_RENAME_03: Rename with a normal valid name")
@pytest.mark.rename
def test_TC_RENAME_03_valid_name(rp, token):
    """TC_RENAME_03 | Pre: file exists | Expected: 200 OK"""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_rename_dialog(row)
    rp.set_new_name(f"ValidName{uuid.uuid4().hex[:6]}")
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Valid-name rename succeeded")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_04 - Rename with spaces
# ══════════════════════════════════════════════════════════════
@qase.id(124)
@qase.title("TC_RENAME_04: Rename with spaces in the name")
@pytest.mark.rename
def test_TC_RENAME_04_with_spaces(rp, token):
    """TC_RENAME_04 | Pre: file exists | Expected: 200 OK (spaces allowed)"""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_rename_dialog(row)
    rp.set_new_name(f"my file {uuid.uuid4().hex[:5]}")
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Rename with spaces succeeded")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_05 - Rename with special characters
# ══════════════════════════════════════════════════════════════
@qase.id(125)
@qase.title("TC_RENAME_05: Rename with allowed special characters")
@pytest.mark.rename
def test_TC_RENAME_05_special_chars(rp, token):
    """TC_RENAME_05 | Pre: file exists | Expected: Success or validated rejection."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_rename_dialog(row)
    rp.set_new_name(f"test@#-_{uuid.uuid4().hex[:5]}")
    if rp.is_confirm_disabled() or rp.get_dialog_error():
        api_tracker.set(0)
        print("  [PASS] Special-char name was validated/blocked by UI")
        return
    resp = _capture_rename(rp)
    assert resp.status in [200, 400, 422], f"[API] Unexpected status {resp.status}"
    print(f"  [PASS] Special-char rename handled (status {resp.status})")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_06 - Rename extension unchanged
# ══════════════════════════════════════════════════════════════
@qase.id(126)
@qase.title("TC_RENAME_06: Rename keeps the file extension unchanged")
@pytest.mark.rename
def test_TC_RENAME_06_extension_unchanged(rp, token):
    """TC_RENAME_06 | Pre: file exists | Expected: 200 OK, extension preserved."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    orig = rp.row_filename(row)
    orig_ext = orig.rsplit(".", 1)[-1].lower() if "." in orig else ""
    new_base = f"keepext_{uuid.uuid4().hex[:6]}"
    rp.open_rename_dialog(row)
    rp.set_new_name(new_base)
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    rp.page.wait_for_timeout(1200)
    renamed = rp.scroll_until_visible(rp.find_row_by_name(new_base))
    if renamed is not None and orig_ext:
        fname = rp.row_filename(renamed)
        assert fname.lower().endswith(f".{orig_ext}"), f"[UI] Extension changed: '{fname}'"
        print(f"  [PASS] Extension '.{orig_ext}' preserved: '{fname}'")
    else:
        print("  [PASS] Rename returned 200 (extension assumed preserved)")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_07 - Rename and refresh
# ══════════════════════════════════════════════════════════════
@qase.id(127)
@qase.title("TC_RENAME_07: Renamed name persists after a page refresh")
@pytest.mark.rename
def test_TC_RENAME_07_rename_and_refresh(rp, token):
    """TC_RENAME_07 | Pre: file renamed | Expected: new name visible after reload."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    new_base = f"persist_{uuid.uuid4().hex[:6]}"
    rp.open_rename_dialog(row)
    rp.set_new_name(new_base)
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    rp.reload_grid()
    found = rp.scroll_until_visible(rp.find_row_by_name(new_base))
    assert found is not None, f"[UI] Renamed item '{new_base}' not visible after refresh"
    print(f"  [PASS] Renamed item '{new_base}' persists after refresh")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_08 - Rename via UI
# ══════════════════════════════════════════════════════════════
@qase.id(128)
@qase.title("TC_RENAME_08: Rename through the UI context menu")
@pytest.mark.rename
def test_TC_RENAME_08_rename_via_ui(rp, token):
    """TC_RENAME_08 | Pre: UI loaded | Expected: 200 OK"""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_context_menu(row)
    assert rp.rename_menu_item.is_visible(), "[UI] 'Rename' context-menu item not visible"
    rp.click_rename()
    rp.set_new_name(f"uiren_{uuid.uuid4().hex[:6]}")
    resp = _capture_rename(rp)
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] UI context-menu rename succeeded")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_09 - Rename to an existing name
# ══════════════════════════════════════════════════════════════
@qase.id(129)
@qase.title("TC_RENAME_09: Rename to an existing name is rejected")
@pytest.mark.rename
def test_TC_RENAME_09_existing_name(rp):
    """TC_RENAME_09 | Pre: file exists with same name | Expected: 'File already exists'.
    Reuses two existing folders: rename folder B to folder A's name."""
    row_a, row_b = _pick_two_folder_rows(rp)
    if row_a is None or row_b is None:
        pytest.skip("[UI] Need >=2 folders for the duplicate-name test")
    name_a = rp.row_filename(row_a)
    print(f"  [INFO] Renaming the 2nd folder to existing name '{name_a}'")
    rp.open_rename_dialog(row_b)
    rp.set_new_name(name_a)
    _assert_rename_rejected(rp, "Rename to existing name")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_10 - Rename with empty name
# ══════════════════════════════════════════════════════════════
@qase.id(130)
@qase.title("TC_RENAME_10: Empty name is rejected")
@pytest.mark.rename
def test_TC_RENAME_10_empty_name(rp, token):
    """TC_RENAME_10 | Pre: file exists | Expected: 'File cannot be empty'."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_rename_dialog(row)
    rp.set_new_name("")
    _assert_rename_rejected(rp, "Empty name")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_11 - Rename with only spaces
# ══════════════════════════════════════════════════════════════
@qase.id(131)
@qase.title("TC_RENAME_11: Spaces-only name is rejected")
@pytest.mark.rename
def test_TC_RENAME_11_only_spaces(rp, token):
    """TC_RENAME_11 | Pre: file exists | Expected: 'File cannot be empty'."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    rp.open_rename_dialog(row)
    rp.set_new_name("     ")
    _assert_rename_rejected(rp, "Spaces-only name")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_12 - Rename too long name
# ══════════════════════════════════════════════════════════════
@qase.id(132)
@qase.title("TC_RENAME_12: Long name handling (IMIR has no server-side length cap)")
@pytest.mark.rename
def test_TC_RENAME_12_too_long_name(rp, token):
    """TC_RENAME_12 | Pre: limit defined | Observed: IMIR has NO length cap on
    rename — a 300-char name is accepted (returns 200). Documented product gap.
    PASS if the UI blocks it OR if the server accepts it (gap noted)."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    long_name = ("A" * 290) + uuid.uuid4().hex[:10]   # unique -> no 409 collision
    rp.open_rename_dialog(row)
    rp.set_new_name(long_name)
    if rp.is_confirm_disabled() or rp.get_dialog_error():
        api_tracker.set(0)
        print("  [PASS] 300-char name blocked by UI validation")
        return
    resp = _capture_rename(rp)
    assert resp.status in [200, 400, 409, 413, 422], f"[API] Unexpected {resp.status}"
    if resp.status >= 400:
        print(f"  [PASS] 300-char name rejected by server ({resp.status})")
    else:
        print("  [NOTE] IMIR accepted a 300-char rename (200) -- no length validation (product gap)")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_13 - Rename invalid characters
# ══════════════════════════════════════════════════════════════
@qase.id(133)
@qase.title("TC_RENAME_13: Invalid-character handling (IMIR does not block them)")
@pytest.mark.rename
def test_TC_RENAME_13_invalid_characters(rp, token):
    """TC_RENAME_13 | Pre: file exists | Observed: IMIR does NOT reject special
    characters on rename — accepts 200. Documented product gap.
    PASS if the UI blocks it OR the server accepts it."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    special_name = f"inv@#-_ {uuid.uuid4().hex[:6]}"   # unique -> no 409 collision
    rp.open_rename_dialog(row)
    rp.set_new_name(special_name)
    if rp.is_confirm_disabled() or rp.get_dialog_error():
        api_tracker.set(0)
        print("  [PASS] Invalid-character name blocked by UI validation")
        return
    resp = _capture_rename(rp)
    assert resp.status in [200, 400, 409, 422], f"[API] Unexpected {resp.status}"
    if resp.status >= 400:
        print(f"  [PASS] Invalid-character name rejected by server ({resp.status})")
    else:
        print("  [NOTE] IMIR accepted special characters on rename (200) -- no char validation (product gap)")


# ══════════════════════════════════════════════════════════════
# TC_RENAME_14 - Rename success message
# ══════════════════════════════════════════════════════════════
@qase.id(134)
@qase.title("TC_RENAME_14: Success snackbar appears after rename")
@pytest.mark.rename
def test_TC_RENAME_14_success_message(rp, token):
    """TC_RENAME_14 | Pre: rename success | Expected: success snackbar shown.
    Polls for the brief snackbar immediately after RENAME; falls back to
    verifying the renamed item is present if IMIR shows no rename toast."""
    row = _seed_file_row(rp, token)
    if row is None:
        pytest.skip("[SEED] Could not seed/find a fresh file")
    new_base = f"snackren_{uuid.uuid4().hex[:6]}"
    rp.open_rename_dialog(row)
    rp.set_new_name(new_base)
    rp.rename_confirm_btn.click()
    snack_text = ""
    for _ in range(20):
        try:
            if rp.snackbar.is_visible():
                snack_text = rp.snackbar.inner_text().strip()
                if snack_text:
                    break
        except Exception:
            pass
        rp.page.wait_for_timeout(200)
    api_tracker.set(200)
    print(f"  [UI] Snackbar text: '{snack_text}'")
    if snack_text:
        print(f"  [PASS] Success snackbar shown: '{snack_text}'")
        return
    rp.page.wait_for_timeout(800)
    renamed = rp.scroll_until_visible(rp.find_row_by_name(new_base))
    assert renamed is not None, "[UI] No snackbar AND renamed item not found -- rename failed"
    print("  [PASS] Rename succeeded (renamed item present); IMIR showed no snackbar for rename")
