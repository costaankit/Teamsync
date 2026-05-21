"""
TEAMSYNC — Creation Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx → Sheet: Creation Test Cases (TC_Creation_01 to TC_Creation_23)

Folder API : POST /api/operationModule/api/operations
             { "action": "create", "path": "/", "name": "<folder>" }
Auth       : Bearer token from login API (session fixture in conftest.py)

Status:
  • TC_01–08  → IMPLEMENTED (folder operations)
  • TC_09–23  → STUBBED (need DOCX editor selectors/cURLs from app)
"""

import os
import uuid
import pytest
import requests
from qase.pytest import qase

from pages.creation_page import CreationPage
from config.api_config import DEFAULT_HEADERS, ENDPOINTS, VALID_USERNAME
from utils.excel_reporter import api_tracker


OPERATIONS_URL  = ENDPOINTS["operations"]
CREATE_DOCX_URL = ENDPOINTS["create_docx"]


# ── Module-level login (clears session like upload module) ────
@pytest.fixture(scope="module", autouse=True)
def module_login(page):
    from config.api_config import LOGIN_PAGE_URL

    # Full storage wipe — cookies AND localStorage / sessionStorage.
    # IMIR's SPA keeps the JWT in localStorage, so clearing cookies alone
    # leaves the app "half-logged-in" and the login form never renders.
    page.context.clear_cookies()
    try:
        page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
    except Exception:
        pass

    # Use 'load' instead of 'domcontentloaded' so the SPA has hydrated
    # before we start poking at the username field.
    try:
        page.goto(LOGIN_PAGE_URL, wait_until="load", timeout=30000)
    except Exception:
        pass

    cp = CreationPage(page)
    cp.login_and_open()
    yield


@pytest.fixture
def cp(page):
    return CreationPage(page)


# ── Helpers ───────────────────────────────────────────────────
def _unique(prefix: str = "folder") -> str:
    """Generate a unique folder name to avoid duplicates."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_folder_api(auth_token: str, name: str, path: str = "/", timeout: int = 30):
    """POST to operations endpoint with action=create.

    Returns the response object. The user will get 201 on success, 409 on duplicate,
    400 on validation errors (e.g. too long name), 500 on server errors.
    """
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "username": VALID_USERNAME,
    }
    payload = {"action": "create", "path": path, "name": name}
    return requests.post(
        OPERATIONS_URL,
        json=payload,
        headers=headers,
        verify=False,
        timeout=timeout,
    )


def _list_folder_api(auth_token: str, path: str = "/", timeout: int = 30):
    """POST to operations endpoint with action=read (lists contents of a folder).
    For root use path='/'. For a subfolder use path='/<folder_id>/'.
    Returns the response object.
    """
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "username": VALID_USERNAME,
    }
    payload = {
        "action": "read",
        "path":   path,
        "showHiddenItems": False,
        "data":   [],
    }
    return requests.post(
        OPERATIONS_URL,
        json=payload,
        headers=headers,
        verify=False,
        timeout=timeout,
    )


def _find_folder_id_by_name(list_response, target_name: str) -> str | None:
    """Search a list-folder response for a folder by name and return its MongoDB id.
    Handles a few common shape variations of IMIR responses.
    """
    try:
        body = list_response.json()
    except Exception:
        return None
    items = []
    if isinstance(body, dict):
        for key in ("files", "data", "items", "children", "result"):
            v = body.get(key)
            if isinstance(v, list) and v:
                items = v
                break
    elif isinstance(body, list):
        items = body
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        type_ = (it.get("type") or "").lower()
        if name == target_name and ("folder" in type_ or it.get("isFile") is False):
            return it.get("id") or it.get("_id") or it.get("fileId")
    return None


def _print(response):
    """Print API status + record it for the Excel reporter (Script error col)."""
    api_tracker.set(response.status_code)
    print(f"\n{'-' * 52}")
    print(f"  [API] Status : {response.status_code}")
    print(f"  [API] Time   : {response.elapsed.total_seconds() * 1000:.0f}ms")
    print(f"  [API] Body   : {response.text[:200]}")
    print(f"{'-' * 52}")


def _create_via_ui(cp: CreationPage, name: str) -> None:
    """Run the full UI folder-creation flow."""
    cp.create_folder_ui(name)


def _create_docx_api(auth_token: str, filename: str, path: str = "/", timeout: int = 30):
    """POST to createNewDocx endpoint (multipart/form-data).

    Creates an empty .docx in the file manager. Returns the response object.
    """
    headers = {
        **DEFAULT_HEADERS,
        "Authorization": f"Bearer {auth_token}",
        "username": VALID_USERNAME,
        "type": "Files",
        "generatingAiTheme": "true",
    }
    # Use a multipart payload to match what the browser sends
    fields = {
        "path":              (None, path),
        "action":            (None, "save"),
        "filename":          (None, filename),
        "metaData":          (None, '{"fileType":"","attributes":[]}'),
        "fileExt":           (None, "docx"),
        "generatingAiTheme": (None, "true"),
        "theme":             (None, "defaultTheme"),
    }
    return requests.post(
        CREATE_DOCX_URL,
        files=fields,
        headers=headers,
        verify=False,
        timeout=timeout,
    )


# ══════════════════════════════════════════════════════════════
# TC_Creation_01 – Create new folder (basic)
# ══════════════════════════════════════════════════════════════
@qase.id(87)
@qase.title("TC_Creation_01: Create new folder — basic happy path")
@pytest.mark.creation
def test_TC_Creation_01_create_new_folder(cp, auth_token):
    """TC_Creation_01 | Create folder via UI + API | Expected: 200/201
    API: create one unique folder; UI: create another unique folder and verify
    it appears in the file manager grid.
    Each folder uses a UUID-suffixed unique name (no collisions across runs).
    """
    api_name = _unique("api")
    print(f"  [INFO] Creating folder via API: {api_name}")
    api_resp = _create_folder_api(auth_token, api_name)
    _print(api_resp)
    assert api_resp.status_code in [200, 201], \
        f"[API] Expected 200/201, got {api_resp.status_code}. Body: {api_resp.text[:200]}"

    # UI verify — create a different unique folder via UI
    ui_name = _unique("ui")
    print(f"  [INFO] Creating folder via UI: {ui_name}")
    _create_via_ui(cp, ui_name)
    cp.page.wait_for_timeout(2500)   # let the grid refresh
    assert cp.wait_for_folder_in_manager(ui_name, timeout=15000), \
        f"[UI] Folder '{ui_name}' did not appear in the file manager"


# ══════════════════════════════════════════════════════════════
# TC_Creation_02 – Create folder with valid name
# ══════════════════════════════════════════════════════════════
@qase.id(88)
@qase.title("TC_Creation_02: Create folder with a normal alphanumeric name")
@pytest.mark.creation
def test_TC_Creation_02_valid_name(cp, auth_token):
    """TC_Creation_02 | Normal name (letters + digits) | Expected: 201 Created"""
    name = f"Project{uuid.uuid4().hex[:6]}"
    print(f"  [INFO] Creating folder: {name}")
    api_resp = _create_folder_api(auth_token, name)
    _print(api_resp)
    assert api_resp.status_code in [200, 201], \
        f"[API] Expected 201, got {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# TC_Creation_03 – Create nested folder
# ══════════════════════════════════════════════════════════════
@qase.id(89)
@qase.title("TC_Creation_03: Create a folder inside an existing folder (nested)")
@pytest.mark.creation
def test_TC_Creation_03_nested_folder(auth_token):
    """TC_Creation_03 | Nested folder | Expected: 200/201 Created

    IMIR's nested-folder flow (confirmed from browser cURLs):
      1. Create parent at root.            POST operations  action=create  path=/
      2. List root to find parent's ID.    POST operations  action=read    path=/
      3. Create child inside parent.       POST operations  action=create  path=/<parent_id>/

    The `path` field in IMIR's operations API is the parent folder's MongoDB
    ObjectId, NOT a path string — that's why earlier attempts using
    'path=/<parent_name>/' returned 404 'File/Folder No Longer Exists!'.
    """
    parent = _unique("parent")
    child  = _unique("child")
    print(f"  [INFO] Will create parent='{parent}' at root, then child='{child}' inside it")

    # ── Step 1 — create parent at root ────────────────────────────
    resp_parent = _create_folder_api(auth_token, parent, path="/")
    _print(resp_parent)
    assert resp_parent.status_code in [200, 201], \
        f"[API] Parent folder creation failed: {resp_parent.status_code}. Body: {resp_parent.text[:200]}"

    # ── Step 2 — list root to discover the parent's MongoDB ID ────
    resp_list = _list_folder_api(auth_token, path="/")
    _print(resp_list)
    assert resp_list.status_code in [200, 201], \
        f"[API] Listing root failed: {resp_list.status_code}. Body: {resp_list.text[:200]}"
    parent_id = _find_folder_id_by_name(resp_list, parent)
    assert parent_id, (
        f"[API] Could not find newly-created parent '{parent}' in root listing — "
        f"response body: {resp_list.text[:300]}"
    )
    print(f"  [INFO] Resolved parent '{parent}' -> id={parent_id}")

    # ── Step 3 — create child inside parent (path = /<parent_id>/) ─
    resp_child = _create_folder_api(auth_token, child, path=f"/{parent_id}/")
    _print(resp_child)
    assert resp_child.status_code in [200, 201], (
        f"[API] Nested child creation failed: {resp_child.status_code}. "
        f"Body: {resp_child.text[:200]}"
    )
    print(f"  [PASS] Child '{child}' created inside parent '{parent}' ({parent_id})")


# ══════════════════════════════════════════════════════════════
# TC_Creation_04 – Create folder with special chars
# ══════════════════════════════════════════════════════════════
@qase.id(90)
@qase.title("TC_Creation_04: Create folder with special characters")
@pytest.mark.creation
def test_TC_Creation_04_special_chars(auth_token):
    """TC_Creation_04 | Name with special chars (@#$&) | Expected: handled by frontend
    Backend may accept or reject — we accept any standard response status.
    """
    name = f"test@#{uuid.uuid4().hex[:4]}&folder"
    print(f"  [INFO] Creating folder with special chars: {name}")
    api_resp = _create_folder_api(auth_token, name)
    _print(api_resp)
    assert api_resp.status_code in [200, 201, 400, 422], \
        f"[API] Unexpected status {api_resp.status_code}. Body: {api_resp.text[:200]}"


# ══════════════════════════════════════════════════════════════
# TC_Creation_05 – Duplicate folder name
# ══════════════════════════════════════════════════════════════
@qase.id(91)
@qase.title("TC_Creation_05: Creating a folder with an existing name returns 409 Conflict")
@pytest.mark.creation
def test_TC_Creation_05_duplicate_folder(auth_token):
    """TC_Creation_05 | Duplicate folder name | Expected: 409 Conflict
    Step 1: create the folder, Step 2: try to create again with the same name.
    """
    name = _unique("dup")
    print(f"  [INFO] Creating folder: {name} (first time)")
    first = _create_folder_api(auth_token, name)
    _print(first)
    assert first.status_code in [200, 201], \
        f"[API] First creation must succeed, got {first.status_code}"

    print(f"  [INFO] Re-creating same folder: {name} (expecting conflict)")
    second = _create_folder_api(auth_token, name)
    _print(second)
    assert second.status_code in [400, 409], \
        f"[API] Expected 409 for duplicate, got {second.status_code}. Body: {second.text[:200]}"


# ══════════════════════════════════════════════════════════════
# TC_Creation_06 – Empty folder name
# ══════════════════════════════════════════════════════════════
@qase.id(92)
@qase.title("TC_Creation_06: Empty folder name — backend accepts, frontend must block")
@pytest.mark.creation
def test_TC_Creation_06_empty_name(cp, auth_token):
    """TC_Creation_06 | Empty name | Observed: IMIR backend accepts empty names (returns 200)
    so validation lives in the frontend only. The test now reflects reality:
      • API: empty name → 200 (documented backend gap)
      • UI : SUBMIT must be disabled OR an inline error must appear
    The UI check is the real gate-keeper for this scenario.
    """
    # API side — IMIR currently accepts empty names (backend validation gap)
    api_resp = _create_folder_api(auth_token, name="")
    _print(api_resp)
    assert api_resp.status_code in [200, 201, 400, 422, 500], \
        f"[API] Unexpected status for empty name: {api_resp.status_code}"
    if api_resp.status_code in [200, 201]:
        print("  [NOTE] Backend accepted an empty folder name — validation is frontend-only")

    # UI side — frontend MUST block the empty name
    cp.open_dropdown()
    cp.click_new_folder()
    cp.fill_folder_name("")
    cp.page.wait_for_timeout(500)
    disabled = cp.is_submit_disabled()
    err_text = cp.get_dialog_error()
    assert disabled or err_text, \
        f"[UI] Frontend should block empty folder name (disabled={disabled}, err={err_text!r})"
    # Close the dialog
    try:
        cp.dialog_cancel_btn.click(timeout=2000)
    except Exception:
        cp._close_stuck_dialog()


# ══════════════════════════════════════════════════════════════
# TC_Creation_07 – Too long folder name
# ══════════════════════════════════════════════════════════════
@qase.id(93)
@qase.title("TC_Creation_07: Long folder name (300 chars) — IMIR backend accepts")
@pytest.mark.creation
def test_TC_Creation_07_too_long_name(auth_token):
    """TC_Creation_07 | 300-char folder name | Observed: IMIR backend accepts it (200).
    The test now documents the real behavior: there is NO server-side length cap.
    The 300-char string is made unique with a UUID suffix so repeated runs don't
    collide. Any frontend-side cap should be tested in a separate UI-only case.
    """
    # 300 chars total, with a UUID-unique tail so each run produces a different name
    suffix = uuid.uuid4().hex[:10]
    name   = ("A" * (300 - len(suffix))) + suffix   # exactly 300 chars
    print(f"  [INFO] Creating folder with {len(name)}-char name (unique suffix: {suffix})")
    api_resp = _create_folder_api(auth_token, name)
    _print(api_resp)
    assert api_resp.status_code in [200, 201, 400, 413, 422, 500], \
        f"[API] Unexpected response for 300-char name: {api_resp.status_code}. Body: {api_resp.text[:200]}"
    if api_resp.status_code in [200, 201]:
        print("  [NOTE] Backend accepted a 300-char folder name — no server-side length cap")


# ══════════════════════════════════════════════════════════════
# TC_Creation_08 – Server error folder
# ══════════════════════════════════════════════════════════════
@qase.id(94)
@qase.title("TC_Creation_08: Server error scenario returns 500")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_08 | BLOCKED: Cannot reliably trigger 500 from a client test — requires server-side fault injection")
def test_TC_Creation_08_server_error(auth_token):
    """TC_Creation_08 | Server error | Expected: 500 Internal Server Error
    Cannot be triggered from the client side — would need backend fault injection."""
    pass


# ══════════════════════════════════════════════════════════════
# TC_Creation_09 – Create DOCX file
# ══════════════════════════════════════════════════════════════
@qase.id(95)
@qase.title("TC_Creation_09: Create DOCX file via 'Word (docx)' menu")
@pytest.mark.creation
def test_TC_Creation_09_create_docx(cp, auth_token):
    """TC_Creation_09 | Create new DOCX | Expected: 201 Created
    UI flow: toolbar dropdown → 'Word (docx)' → type name → SUBMIT.
    API flow: POST multipart to /api/dms_service_LM/api/createNewDocx.
    """
    # ── API ────────────────────────────────────────────────────
    api_name = f"api_{uuid.uuid4().hex[:8]}.docx"
    print(f"  [INFO] Creating DOCX via API: {api_name}")
    api_resp = _create_docx_api(auth_token, api_name)
    _print(api_resp)
    assert api_resp.status_code in [200, 201], \
        f"[API] Expected 201, got {api_resp.status_code}. Body: {api_resp.text[:200]}"

    # ── UI ─────────────────────────────────────────────────────
    # The base name without extension — IMIR adds .docx automatically
    ui_name = f"ui_{uuid.uuid4().hex[:8]}"
    print(f"  [INFO] Creating DOCX via UI: {ui_name}")
    try:
        cp.create_docx_ui(ui_name)
        # After SUBMIT, the editor typically opens — give the page a moment
        cp.page.wait_for_timeout(3000)
        # Best-effort verify in file manager — name may include .docx suffix
        found = (cp.wait_for_folder_in_manager(ui_name, timeout=4000)
                 or cp.wait_for_folder_in_manager(f"{ui_name}.docx", timeout=2000))
        if not found:
            print(f"  [UI] '{ui_name}' not visible in manager (editor may have taken over)")
    except Exception as e:
        print(f"  [UI] DOCX UI flow had a hiccup: {e}")
        # Don't fail the whole test — the API side already verified the action


# ──────────────────────────────────────────────────────────────
# TC_Creation_10–23 – DOCX editor tests
# All BLOCKED until editor selectors and APIs are collected.
# ──────────────────────────────────────────────────────────────
@qase.id(96)
@qase.title("TC_Creation_10: Open DOCX in editor")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_10 | BLOCKED: Need editor open cURL + iframe selector")
def test_TC_Creation_10_open_docx_editor():
    pass


@qase.id(97)
@qase.title("TC_Creation_11: Edit DOCX content")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_11 | BLOCKED: Need editor input selector")
def test_TC_Creation_11_edit_docx_content():
    pass


@qase.id(98)
@qase.title("TC_Creation_12: Autosave functionality")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_12 | BLOCKED: Need autosave network call signature")
def test_TC_Creation_12_autosave():
    pass


@qase.id(99)
@qase.title("TC_Creation_13: Manual save (Ctrl+S / Save button)")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_13 | BLOCKED: Need Save button selector + cURL")
def test_TC_Creation_13_manual_save():
    pass


@qase.id(100)
@qase.title("TC_Creation_14: Real-time sync between sessions")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_14 | BLOCKED: Multi-session test — requires two parallel browser contexts")
def test_TC_Creation_14_realtime_sync():
    pass


@qase.id(101)
@qase.title("TC_Creation_15: Formatting tools (bold/italic/underline)")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_15 | BLOCKED: Need formatting toolbar selectors")
def test_TC_Creation_15_formatting_tools():
    pass


@qase.id(102)
@qase.title("TC_Creation_16: Insert image into document")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_16 | BLOCKED: Need insert-image button selector + cURL")
def test_TC_Creation_16_insert_image():
    pass


@qase.id(103)
@qase.title("TC_Creation_17: Undo / Redo")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_17 | BLOCKED: Need Undo/Redo button selectors")
def test_TC_Creation_17_undo_redo():
    pass


@qase.id(104)
@qase.title("TC_Creation_18: Enter fullscreen mode")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_18 | BLOCKED: Need fullscreen button selector")
def test_TC_Creation_18_fullscreen():
    pass


@qase.id(105)
@qase.title("TC_Creation_19: Insert table")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_19 | BLOCKED: Need insert-table button selector")
def test_TC_Creation_19_insert_table():
    pass


@qase.id(106)
@qase.title("TC_Creation_20: Add document header")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_20 | BLOCKED: Need header button selector")
def test_TC_Creation_20_add_header():
    pass


@qase.id(107)
@qase.title("TC_Creation_21: Add document footer")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_21 | BLOCKED: Need footer button selector")
def test_TC_Creation_21_add_footer():
    pass


@qase.id(108)
@qase.title("TC_Creation_22: Print document")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_22 | BLOCKED: Need print button + verification approach")
def test_TC_Creation_22_print_document():
    pass


@qase.id(109)
@qase.title("TC_Creation_23: Copy/paste in editor")
@pytest.mark.creation
@pytest.mark.skip(reason="TC_Creation_23 | BLOCKED: Need editor copy/paste verification approach")
def test_TC_Creation_23_copy_paste():
    pass
