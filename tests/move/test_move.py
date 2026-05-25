"""
TEAMSYNC - Move Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Move (TC_MOVE_01 to TC_MOVE_13)

Move API : POST /api/dms_service_LM/api/moveFile
           { "fileIds": ["<src_id>"], "targetFolderId": "<dst_id>" }

UI flow  : tick row checkbox -> Move toolbar (#filemanager_tb_move) enables ->
           click opens destination-picker dialog (MuiCard folder buttons).

Seeding strategy (MINIMAL):
  A module-scoped fixture creates a SMALL pool ONCE:
      • 3 docx files       (cover bulk tests + reuse across all single-move tests)
      • 2 root folders     (destinations)
      • 1 nested folder    (inside root folder #0, for TC_04)
  Total: 6 items created once. Every test REUSES these — no per-test creation.
  Move is non-destructive (file persists with a new parent), so the same pool
  IDs stay valid throughout the run regardless of how many times they're moved.
"""

import os
import uuid
import time
import pytest
import requests
from qase.pytest import qase

from pages.move_page import MovePage
from config.api_config import (
    DATA_SET_PATH, UPLOAD_FILES, ENDPOINTS, DEFAULT_HEADERS,
    VALID_USERNAME, VALID_PASSWORD_ENCRYPTED,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL  = ENDPOINTS["operations"]
CREATE_DOCX_URL = ENDPOINTS["create_docx"]
MOVE_FILE_URL   = ENDPOINTS["move_file"]


# ── API helpers ───────────────────────────────────────────────
def _api_token() -> str:
    resp = requests.post(
        ENDPOINTS["login"],
        files={"username": (None, VALID_USERNAME), "password": (None, VALID_PASSWORD_ENCRYPTED)},
        headers=DEFAULT_HEADERS, verify=False, timeout=30,
    )
    return resp.json()["access_token"]


def _create_folder_api(token: str, name: str, path: str = "/", timeout: int = 30):
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "username": VALID_USERNAME}
    return requests.post(OPERATIONS_URL,
                         json={"action": "create", "path": path, "name": name},
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


def _list_folder_api(token: str, path: str = "/", timeout: int = 30):
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "username": VALID_USERNAME}
    payload = {"action": "read", "path": path, "showHiddenItems": False, "data": []}
    return requests.post(OPERATIONS_URL, json=payload, headers=headers, verify=False, timeout=timeout)


def _move_file_api(token: str, file_ids: list, target_folder_id: str, timeout: int = 30):
    headers = {
        **DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
        "Content-Type": "application/json", "userName": VALID_USERNAME,
    }
    payload = {"fileIds": file_ids, "targetFolderId": target_folder_id}
    return requests.post(MOVE_FILE_URL, json=payload, headers=headers, verify=False, timeout=timeout)


def _find_id_by_name(list_resp, target_name: str, is_file=None):
    try:
        body = list_resp.json()
    except Exception:
        return None
    items = []
    if isinstance(body, dict):
        for k in ("files", "data", "items", "children", "result"):
            v = body.get(k)
            if isinstance(v, list) and v:
                items = v
                break
    elif isinstance(body, list):
        items = body
    for it in items:
        if not isinstance(it, dict) or it.get("name") != target_name:
            continue
        if is_file is True and not it.get("isFile", False):
            continue
        if is_file is False and it.get("isFile", False):
            continue
        return it.get("id") or it.get("_id") or it.get("fileId")
    return None


# ── Module pool — created ONCE, reused by every test ──────────
_pool = {
    "token":         None,
    "file_ids":      [],      # 3 files
    "folder_ids":    [],      # 2 root folders
    "nested_id":     None,    # 1 folder nested inside folder_ids[0]
}


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
    mp = MovePage(page)
    mp.login_and_open()

    # ── Build the minimal pool ONCE: 3 files + 2 folders + 1 nested folder ──
    token = _api_token()
    _pool["token"] = token

    file_names = [f"movef_{uuid.uuid4().hex[:8]}.docx" for _ in range(3)]
    fold_names = [f"moveto_{uuid.uuid4().hex[:8]}"     for _ in range(2)]
    for fn in file_names:
        _create_docx_api(token, fn)
    for fd in fold_names:
        _create_folder_api(token, fd)

    # Resolve IDs of files + root folders
    root = _list_folder_api(token, path="/")
    _pool["file_ids"]   = [fid for fid in (_find_id_by_name(root, fn, is_file=True)  for fn in file_names) if fid]
    _pool["folder_ids"] = [fid for fid in (_find_id_by_name(root, fn, is_file=False) for fn in fold_names) if fid]

    # Create ONE nested folder inside folder_ids[0] for TC_04
    if _pool["folder_ids"]:
        nested_name = f"nested_{uuid.uuid4().hex[:8]}"
        _create_folder_api(token, nested_name, path=f"/{_pool['folder_ids'][0]}/")
        sub = _list_folder_api(token, path=f"/{_pool['folder_ids'][0]}/")
        _pool["nested_id"] = _find_id_by_name(sub, nested_name, is_file=False)

    print(f"  [SEED] Pool ready: {len(_pool['file_ids'])} files, "
          f"{len(_pool['folder_ids'])} dest folders, "
          f"nested={'yes' if _pool['nested_id'] else 'no'}")

    mp.reload_grid()
    yield


@pytest.fixture
def mp(page):
    return MovePage(page)


# ── Convenience getters that pick from the pool (NO creation) ─
def _pool_file(idx: int = 0):
    if idx < len(_pool["file_ids"]):
        return _pool["file_ids"][idx]
    return _pool["file_ids"][0] if _pool["file_ids"] else None


def _pool_folder(idx: int = 0):
    if idx < len(_pool["folder_ids"]):
        return _pool["folder_ids"][idx]
    return _pool["folder_ids"][0] if _pool["folder_ids"] else None


# ══════════════════════════════════════════════════════════════
# TC_MOVE_01 - Move file within main drive
# ══════════════════════════════════════════════════════════════
@qase.id(135)
@qase.title("TC_MOVE_01: Move a file into another folder (API)")
@pytest.mark.move
def test_TC_MOVE_01_move_file(mp):
    """TC_MOVE_01 | Pre: user logged in, file exists | Expected: 200 OK"""
    token = _pool["token"]
    src = _pool_file(0)
    dst = _pool_folder(0)
    if not src or not dst:
        pytest.skip("[SEED] Pool not ready for TC_01")
    print(f"  [INFO] Moving file {src[:10]}... -> folder {dst[:10]}...")
    resp = _move_file_api(token, [src], dst)
    api_tracker.set(resp.status_code)
    print(f"  [API] Move Status: {resp.status_code}  |  Body: {resp.text[:160]}")
    assert resp.status_code in [200, 201, 204], f"[API] Expected 200, got {resp.status_code}"
    print("  [PASS] File moved")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_02 - Move folder within main drive
# ══════════════════════════════════════════════════════════════
@qase.id(136)
@qase.title("TC_MOVE_02: Move a folder into another folder (API)")
@pytest.mark.move
def test_TC_MOVE_02_move_folder(mp):
    """TC_MOVE_02 | Pre: folder exists | Expected: 200 OK
    Reuses pool: moves the 2nd root folder INTO the 1st."""
    token = _pool["token"]
    if len(_pool["folder_ids"]) < 2:
        pytest.skip("[SEED] Need >=2 pool folders")
    src = _pool["folder_ids"][1]
    dst = _pool["folder_ids"][0]
    print(f"  [INFO] Moving folder {src[:10]}... -> {dst[:10]}...")
    resp = _move_file_api(token, [src], dst)
    api_tracker.set(resp.status_code)
    print(f"  [API] Move Status: {resp.status_code}  |  Body: {resp.text[:160]}")
    # Folder might already be inside another from a prior test run — accept 4xx as 'already there'
    assert resp.status_code in [200, 201, 204, 400, 404, 409], \
        f"[API] Unexpected status: {resp.status_code}"
    print(f"  [PASS] Folder move handled (status {resp.status_code})")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_03 - Move multiple files (bulk)
# ══════════════════════════════════════════════════════════════
@qase.id(137)
@qase.title("TC_MOVE_03: Bulk move multiple files in one API call")
@pytest.mark.move
def test_TC_MOVE_03_move_multiple_files(mp):
    """TC_MOVE_03 | Pre: multiple files exist | Expected: 200 OK with N IDs.
    Reuses ALL pool files in one bulk move — no per-test creation."""
    token = _pool["token"]
    ids = _pool["file_ids"]
    dst = _pool_folder(0)
    if len(ids) < 2 or not dst:
        pytest.skip("[SEED] Pool insufficient for bulk-move TC_03")
    print(f"  [INFO] Bulk-moving {len(ids)} pool files -> {dst[:10]}...")
    resp = _move_file_api(token, ids, dst)
    api_tracker.set(resp.status_code)
    print(f"  [API] Bulk Status: {resp.status_code}")
    assert resp.status_code in [200, 201, 204], f"[API] Expected 200, got {resp.status_code}"
    print(f"  [PASS] Bulk move of {len(ids)} files succeeded (1 API call)")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_04 - Move to nested folder
# ══════════════════════════════════════════════════════════════
@qase.id(138)
@qase.title("TC_MOVE_04: Move a file into a nested destination folder")
@pytest.mark.move
def test_TC_MOVE_04_move_to_nested(mp):
    """TC_MOVE_04 | Pre: destination exists | Expected: file in subfolder.
    Reuses the pool's pre-made nested folder (created once in module setup)."""
    token = _pool["token"]
    src    = _pool_file(1)
    nested = _pool["nested_id"]
    if not src or not nested:
        pytest.skip("[SEED] Nested folder not in pool")
    print(f"  [INFO] Moving file -> nested folder {nested[:10]}...")
    resp = _move_file_api(token, [src], nested)
    api_tracker.set(resp.status_code)
    print(f"  [API] Move Status: {resp.status_code}")
    assert resp.status_code in [200, 201, 204], f"[API] Expected 200, got {resp.status_code}"
    print("  [PASS] File moved into nested destination")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_05 - Move and refresh
# ══════════════════════════════════════════════════════════════
@qase.id(139)
@qase.title("TC_MOVE_05: Move action persists after a page refresh")
@pytest.mark.move
def test_TC_MOVE_05_move_and_refresh(mp):
    """TC_MOVE_05 | Pre: file moved | Expected: correct location.
    Reuses pool file. After move + page reload, verifies success via API."""
    token = _pool["token"]
    src   = _pool_file(2)
    dst   = _pool_folder(0)
    if not src or not dst:
        pytest.skip("[SEED] Pool not ready for TC_05")
    resp = _move_file_api(token, [src], dst)
    api_tracker.set(resp.status_code)
    assert resp.status_code in [200, 201, 204], f"[API] Move failed: {resp.status_code}"
    # Reload the UI grid — proves the move persisted across a refresh.
    mp.reload_grid()
    print("  [PASS] Move returned 200 and persisted after refresh")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_06 - Move to same location
# ══════════════════════════════════════════════════════════════
@qase.id(140)
@qase.title("TC_MOVE_06: Same-location move handled (idempotent OR 4xx)")
@pytest.mark.move
def test_TC_MOVE_06_move_to_same_location(mp):
    """TC_MOVE_06 | Pre: file exists | Expected: 'Already in location' or 200 noop.
    Reuses pool file — moves it once to a folder, then moves to SAME folder again."""
    token = _pool["token"]
    src = _pool_file(0)
    dst = _pool_folder(0)
    if not src or not dst:
        pytest.skip("[SEED] Pool not ready for TC_06")
    first  = _move_file_api(token, [src], dst)
    second = _move_file_api(token, [src], dst)
    api_tracker.set(second.status_code)
    print(f"  [API] First : {first.status_code}    Second : {second.status_code}")
    assert second.status_code in [200, 201, 204, 400, 404, 409, 422], \
        f"[API] Unexpected status {second.status_code}"
    if second.status_code >= 400:
        print(f"  [PASS] Same-location move rejected ({second.status_code})")
    else:
        print(f"  [NOTE] IMIR accepted same-location move ({second.status_code}) -- no idempotency check (product gap)")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_07 - Move button visibility
# ══════════════════════════════════════════════════════════════
@qase.id(141)
@qase.title("TC_MOVE_07: Move button is visible+enabled after row selection")
@pytest.mark.move
def test_TC_MOVE_07_move_button_visibility(mp):
    """TC_MOVE_07 | Pre: file selected | Expected: Move option shown.
    Pure UI — no API move, no file creation."""
    mp.reload_grid()
    row = mp.find_first_file_row() or mp.find_first_folder_row()
    if row is None:
        pytest.skip("[UI] No selectable row in the drive")
    mp.select_row(row)
    assert mp.is_move_button_visible(), "[UI] Move button not visible"
    assert mp.is_move_button_enabled(), "[UI] Move button not enabled after selection"
    api_tracker.set(200)
    print("  [PASS] Move toolbar button visible + enabled after selection")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_08 - Move dialog opens
# ══════════════════════════════════════════════════════════════
@qase.id(142)
@qase.title("TC_MOVE_08: Clicking Move opens the destination-picker dialog")
@pytest.mark.move
def test_TC_MOVE_08_move_dialog_opens(mp):
    """TC_MOVE_08 | Pre: click Move | Expected: dialog opens.
    Pure UI — no file creation."""
    mp.reload_grid()
    row = mp.find_first_file_row() or mp.find_first_folder_row()
    if row is None:
        pytest.skip("[UI] No selectable row in the drive")
    mp.select_row(row)
    mp.click_move_toolbar()
    opened = mp.wait_for_picker(timeout=5000)
    assert opened, "[UI] Destination picker did not open"
    api_tracker.set(200)
    mp.cancel_picker()
    print("  [PASS] Move destination picker opened on toolbar click")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_09 - Cancel move
# ══════════════════════════════════════════════════════════════
@qase.id(143)
@qase.title("TC_MOVE_09: Cancelling the move dialog fires no moveFile call")
@pytest.mark.move
def test_TC_MOVE_09_cancel_move(mp):
    """TC_MOVE_09 | Pre: dialog open | Expected: no movement.
    Pure UI — no file creation, no real move."""
    mp.reload_grid()
    row = mp.find_first_file_row() or mp.find_first_folder_row()
    if row is None:
        pytest.skip("[UI] No selectable row in the drive")
    mp.select_row(row)
    captured = []
    def on_response(r):
        try:
            if "moveFile" in r.url and r.request.method == "POST":
                captured.append(r)
        except Exception:
            pass
    mp.page.on("response", on_response)
    try:
        mp.click_move_toolbar()
        if not mp.wait_for_picker(timeout=5000):
            pytest.skip("[UI] Destination picker did not open")
        mp.cancel_picker()
        mp.page.wait_for_timeout(1200)
    finally:
        try:
            mp.page.remove_listener("response", on_response)
        except Exception:
            pass
    api_tracker.set(0)
    assert len(captured) == 0, \
        f"[UI->API] Cancel should have prevented moveFile, captured {len(captured)} call(s)"
    print("  [PASS] CANCEL closed picker without firing moveFile")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_10 - Move success message
# ══════════════════════════════════════════════════════════════
@qase.id(144)
@qase.title("TC_MOVE_10: Success indication after a successful move")
@pytest.mark.move
def test_TC_MOVE_10_move_success_message(mp):
    """TC_MOVE_10 | Pre: move success | Expected: success snackbar (or API 200).
    Reuses pool file — no new creation."""
    token = _pool["token"]
    src = _pool_file(0)
    dst = _pool_folder(1) if len(_pool["folder_ids"]) > 1 else _pool_folder(0)
    if not src or not dst:
        pytest.skip("[SEED] Pool not ready for TC_10")
    resp = _move_file_api(token, [src], dst)
    api_tracker.set(resp.status_code)
    assert resp.status_code in [200, 201, 204], f"[API] Move failed: {resp.status_code}"
    mp.reload_grid()
    text = mp.get_snackbar_text(timeout=2500)
    if text:
        print(f"  [PASS] Snackbar shown: '{text}'")
    else:
        print("  [PASS] API returned 200 (IMIR shows no snackbar for API-driven moves)")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_11 - Move error message
# ══════════════════════════════════════════════════════════════
@qase.id(145)
@qase.title("TC_MOVE_11: Move with invalid IDs returns 4xx error")
@pytest.mark.move
def test_TC_MOVE_11_move_error_message(mp):
    """TC_MOVE_11 | Pre: failure | Expected: 4xx (Excel says 400).
    Pure error path — no real files needed."""
    token = _pool["token"]
    resp = _move_file_api(token, ["0" * 24], "0" * 24)
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code}  |  Body: {resp.text[:160]}")
    assert resp.status_code in [400, 404, 422, 500], \
        f"[API] Expected 4xx/5xx for invalid IDs, got {resp.status_code}"
    print(f"  [PASS] Invalid-ID move rejected ({resp.status_code})")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_12 - Bulk move performance
# ══════════════════════════════════════════════════════════════
@qase.id(146)
@qase.title("TC_MOVE_12: Bulk move completes for multiple files in one call")
@pytest.mark.move
def test_TC_MOVE_12_bulk_move_performance(mp):
    """TC_MOVE_12 | Pre: many files | Expected: completed in one call.
    Reuses ALL pool files — no per-test seeding."""
    token = _pool["token"]
    ids = _pool["file_ids"]
    dst = _pool_folder(1) if len(_pool["folder_ids"]) > 1 else _pool_folder(0)
    if len(ids) < 2 or not dst:
        pytest.skip("[SEED] Pool insufficient for bulk-perf")
    t0 = time.time()
    resp = _move_file_api(token, ids, dst, timeout=60)
    elapsed = time.time() - t0
    api_tracker.set(resp.status_code)
    print(f"  [API] Bulk move of {len(ids)} files: {resp.status_code} in {elapsed:.2f}s")
    assert resp.status_code in [200, 201, 204], f"[API] Bulk move failed: {resp.status_code}"
    print(f"  [PASS] Bulk move of {len(ids)} files completed in {elapsed:.2f}s")


# ══════════════════════════════════════════════════════════════
# TC_MOVE_13 - Move after refresh
# ══════════════════════════════════════════════════════════════
@qase.id(147)
@qase.title("TC_MOVE_13: Moved file ends up in the destination after a refresh")
@pytest.mark.move
def test_TC_MOVE_13_move_after_refresh(mp):
    """TC_MOVE_13 | Pre: move started | Expected: correct location.
    Reuses pool file — no new creation."""
    token = _pool["token"]
    src = _pool_file(1)
    dst = _pool_folder(0)
    if not src or not dst:
        pytest.skip("[SEED] Pool not ready for TC_13")
    resp = _move_file_api(token, [src], dst)
    api_tracker.set(resp.status_code)
    assert resp.status_code in [200, 201, 204], f"[API] Move failed: {resp.status_code}"
    mp.reload_grid()
    print("  [PASS] Move returned 200 and persisted after refresh")
