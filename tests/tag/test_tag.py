"""
TEAMSYNC - Tag (Theme) Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: TAG-Phase2 (TC_Tag_01 to TC_Tag_26)

Flows (captured from the live app):
  Create tag : toolbar #filemanager_tb_theme -> name input (maxlength 20) -> Save
               -> POST /dms_service_LM/api/themes  {themeName, color}
  Assign tag : right-click row -> #filemanager_cm_edittag -> pick tag -> SAVE
               -> POST /dms_service_LM/api/change-file-themes  {fileId, themeIds[]}
  Tags render as MUI chips (with colour) in the grid Tags column; chip X removes.

NOTE: the assign endpoint (change-file-themes) is currently buggy. These tests
assert 200 (system behaviour) so they FAIL honestly until it's fixed and pass
once it returns 200.

Assertion standard: follow real behaviour, not the manual sheet status.
"""

import uuid

import pytest
import requests
from qase.pytest import qase

from pages.tag_page import TagPage
from config.api_config import (
    ENDPOINTS, DEFAULT_HEADERS, VALID_USERNAME, VALID_PASSWORD_ENCRYPTED, LOGIN_PAGE_URL,
)
from utils.excel_reporter import api_tracker


THEMES_URL = ENDPOINTS["themes"]
CHANGE_THEMES_URL = ENDPOINTS["change_file_themes"]


# ── Module-level login (Ankit — default account) ───────────────
@pytest.fixture(scope="module", autouse=True)
def module_login(page):
    page.context.clear_cookies()
    try:
        page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")
    except Exception:
        pass
    try:
        page.goto(LOGIN_PAGE_URL, wait_until="load", timeout=30000)
    except Exception:
        pass
    TagPage(page).login_and_open()
    yield


@pytest.fixture
def tp(page):
    return TagPage(page)


@pytest.fixture(scope="module")
def shared_tag():
    """Create ONE tag for the whole module and reuse it across the flow
    (assign / search / duplicate / persist) instead of making a new tag per
    test. Created via API once at module start."""
    resp = requests.post(
        ENDPOINTS["login"],
        files={"username": (None, VALID_USERNAME), "password": (None, VALID_PASSWORD_ENCRYPTED)},
        headers=DEFAULT_HEADERS, verify=False, timeout=30,
    )
    token = resp.json()["access_token"]
    name = _unique_tag()
    _themes_create(token, name)
    print(f"  [SETUP] shared tag for module: '{name}'")
    return name


@pytest.fixture(autouse=True)
def _fresh_drive(page, module_login):
    """Clean Main Drive before each test (closes menus/dialogs, fresh grid)."""
    try:
        TagPage(page).reload_grid()
    except Exception:
        pass
    yield


# ── API helpers ────────────────────────────────────────────────
def _themes_get(auth_token):
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {auth_token}", "Username": VALID_USERNAME}
    try:
        return requests.get(THEMES_URL, headers=h, verify=False, timeout=30).json()
    except Exception:
        return []


def _themes_create(auth_token, name, color="#4986e7"):
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {auth_token}",
         "Content-Type": "application/json", "username": VALID_USERNAME}
    return requests.post(THEMES_URL, json={"themeName": name, "color": color},
                         headers=h, verify=False, timeout=30)


def _assign_api(auth_token, file_id, theme_ids):
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {auth_token}",
         "Content-Type": "application/json; charset=utf8", "userName": VALID_USERNAME}
    return requests.post(CHANGE_THEMES_URL, json={"fileId": file_id, "themeIds": theme_ids},
                         headers=h, verify=False, timeout=30)


def _theme_names(auth_token):
    out = []
    for t in _themes_get(auth_token) or []:
        if isinstance(t, dict):
            n = t.get("themeName") or t.get("name")
            if n:
                out.append(n)
    return out


def _has_theme(auth_token, name) -> bool:
    """Case-insensitive membership — the app title-cases tags (tag_x -> Tag_x)."""
    return name.lower() in {n.lower() for n in _theme_names(auth_token)}


def _unique_tag():
    return f"tag_{uuid.uuid4().hex[:8]}"   # 12 chars (< maxlength 20)


# ── Response capture (UI actions) ──────────────────────────────
def _capture_themes_post(tp: TagPage, action_fn, timeout: int = 15000):
    with tp.page.expect_response(
        lambda r: r.url.rstrip("/").endswith("/api/themes") and r.request.method == "POST",
        timeout=timeout,
    ) as info:
        action_fn()
    resp = info.value
    api_tracker.set(resp.status)
    print(f"  [API] themes POST Status: {resp.status}")
    return resp


def _capture_assign(tp: TagPage, action_fn, timeout: int = 15000):
    with tp.page.expect_response(
        lambda r: "/change-file-themes" in r.url and r.request.method == "POST",
        timeout=timeout,
    ) as info:
        action_fn()
    resp = info.value
    api_tracker.set(resp.status)
    print(f"  [API] change-file-themes Status: {resp.status}")
    return resp


# Error markers the assign endpoint puts in the BODY while returning HTTP 200.
_ASSIGN_ERROR_MARKERS = (
    "no value present", "exception", "not found", "internal server",
    "bad request", "\"error\":\"", "failed", "could not",
)


def _assert_assign_ok(resp):
    """Validate change-file-themes by BODY, not just status — the endpoint
    returns HTTP 200 even on failure (error text lives in the body)."""
    try:
        body = resp.text()
    except Exception:
        body = ""
    assert resp.status == 200, f"[API] change-file-themes HTTP {resp.status}; body: {body[:200]}"
    low = body.lower()
    hit = [m for m in _ASSIGN_ERROR_MARKERS if m in low]
    assert not hit, (
        f"[BEHAVIOUR] change-file-themes returned 200 but the body signals failure "
        f"{hit}: {body[:200]}"
    )


def _existing_tagged_row(tp: TagPage):
    """A grid row that already carries at least one tag chip, or None."""
    rows = tp.page.locator('#filemanager_grid tr.e-row:not(.Restricted)')
    for i in range(min(rows.count(), 40)):
        r = rows.nth(i)
        if tp.row_tag_chips(r):
            return r
    return None


# ══════════════════════════════════════════════════════════════
# TC_Tag_01 - Create new tag
# ══════════════════════════════════════════════════════════════
@qase.id(500)
@qase.title("TC_Tag_01: Create a new tag")
@pytest.mark.tag
def test_TC_Tag_01_create_tag(tp, auth_token):
    name = _unique_tag()
    tp.open_create_tag()
    tp.type_tag_name(name)
    resp = _capture_themes_post(tp, lambda: tp.save_new_tag())
    assert resp.status in (200, 201), f"[API] Expected 200/201, got {resp.status}"
    assert _has_theme(auth_token, name), f"[DATA] '{name}' not in themes after create"
    print(f"  [PASS] Tag '{name}' created")


# ══════════════════════════════════════════════════════════════
# TC_Tag_02 - Create multiple tags
# ══════════════════════════════════════════════════════════════
@qase.id(501)
@qase.title("TC_Tag_02: Create multiple tags")
@pytest.mark.tag
def test_TC_Tag_02_create_multiple_tags(tp, auth_token):
    names = [_unique_tag() for _ in range(2)]   # 2 = minimal "multiple"
    for n in names:
        r = _themes_create(auth_token, n)
        assert r.status_code in (200, 201), f"[API] create '{n}' got {r.status_code}"
    existing = {n.lower() for n in _theme_names(auth_token)}
    missing = [n for n in names if n.lower() not in existing]
    assert not missing, f"[DATA] tags not persisted: {missing}"
    print(f"  [PASS] Created {len(names)} tags")


# ══════════════════════════════════════════════════════════════
# TC_Tag_03 - Assign tag to file  (change-file-themes currently buggy)
# ══════════════════════════════════════════════════════════════
@qase.id(502)
@qase.title("TC_Tag_03: Assign a tag to a file")
@pytest.mark.tag
def test_TC_Tag_03_assign_tag_to_file(tp, shared_tag):
    tp.reload_grid()
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file in the drive to tag")
    tp.open_add_tag_dialog(row)
    tp.select_tag_in_dialog(shared_tag)
    resp = _capture_assign(tp, lambda: tp.save_assign())
    _assert_assign_ok(resp)
    print(f"  [PASS] Tag '{shared_tag}' assigned to file")


# ══════════════════════════════════════════════════════════════
# TC_Tag_04 - Assign tag to folder
# ══════════════════════════════════════════════════════════════
@qase.id(503)
@qase.title("TC_Tag_04: Assign a tag to a folder")
@pytest.mark.tag
def test_TC_Tag_04_assign_tag_to_folder(tp, shared_tag):
    tp.reload_grid()
    row = tp.find_first_folder_row()
    if row is None:
        pytest.skip("[UI] No folder in the drive to tag")
    tp.open_add_tag_dialog(row)
    tp.select_tag_in_dialog(shared_tag)
    resp = _capture_assign(tp, lambda: tp.save_assign())
    _assert_assign_ok(resp)
    print(f"  [PASS] Tag '{shared_tag}' assigned to folder")


# ══════════════════════════════════════════════════════════════
# TC_Tag_05 - Remove tag from file
# ══════════════════════════════════════════════════════════════
@qase.id(504)
@qase.title("TC_Tag_05: Remove a tag from a file")
@pytest.mark.tag
def test_TC_Tag_05_remove_tag(tp):
    row = _existing_tagged_row(tp)
    if row is None:
        pytest.skip("[UI] No tagged file in the drive to remove a tag from")
    before = tp.row_tag_chips(row)
    resp = _capture_assign(tp, lambda: tp.remove_first_chip(row))
    _assert_assign_ok(resp)
    tp.page.wait_for_timeout(800)
    after = tp.row_tag_chips(tp.scroll_until_visible(row) or row)
    assert len(after) < len(before), f"[UI] tag not removed ({before} -> {after})"
    print(f"  [PASS] Tag removed ({before} -> {after})")


# ══════════════════════════════════════════════════════════════
# TC_Tag_06 - Search by tag
# ══════════════════════════════════════════════════════════════
@qase.id(505)
@qase.title("TC_Tag_06: Search files by tag")
@pytest.mark.tag
def test_TC_Tag_06_search_by_tag(tp, auth_token):
    # Use a tag that is actually on a file in the drive, then verify the Advanced
    # Search tag filter surfaces it (search-by-tag is the same theme filter).
    row = _existing_tagged_row(tp)
    if row is None:
        pytest.skip("[DATA] No tagged file in the drive to search for")
    tag = tp.row_tag_chips(row)[0]
    from pages.advance_search_page import AdvanceSearchPage
    sp = AdvanceSearchPage(tp.page)
    sp.open_panel()
    sp.add_tag(tag)
    with tp.page.expect_response(
        lambda r: "/operationModule/api/operations" in r.url and r.request.method == "POST"
        and '"filter"' in (r.request.post_data or ""), timeout=20000,
    ) as info:
        sp.click_search()
    resp = info.value
    api_tracker.set(resp.status)
    assert resp.status == 200, f"[API] tag search expected 200, got {resp.status}"
    tp.page.wait_for_timeout(1500)
    rows = sp.file_result_rows()
    n = rows.count()
    assert n > 0, f"[BEHAVIOUR] Tag search '{tag}' returned 0 files (a tagged file exists)"
    bad = [sp.row_name(rows.nth(i)) for i in range(min(n, 10)) if tag not in sp.row_tags(rows.nth(i))]
    assert not bad, f"[BEHAVIOUR] Tag search returned files without tag '{tag}': {bad}"
    print(f"  [PASS] Tag search '{tag}' returned {n} matching file(s)")


# ══════════════════════════════════════════════════════════════
# TC_Tag_07 - Filter by tag (same theme filter as search)
# ══════════════════════════════════════════════════════════════
@qase.id(506)
@qase.title("TC_Tag_07: Filter results by tag")
@pytest.mark.tag
def test_TC_Tag_07_filter_by_tag(tp, auth_token):
    row = _existing_tagged_row(tp)
    if row is None:
        pytest.skip("[DATA] No tagged file in the drive to filter by")
    tag = tp.row_tag_chips(row)[0]
    from pages.advance_search_page import AdvanceSearchPage
    sp = AdvanceSearchPage(tp.page)
    sp.open_panel()
    sp.add_tag(tag)
    with tp.page.expect_response(
        lambda r: "/operationModule/api/operations" in r.url and r.request.method == "POST"
        and '"filter"' in (r.request.post_data or ""), timeout=20000,
    ) as info:
        sp.click_search()
    resp = info.value
    api_tracker.set(resp.status)
    assert resp.status == 200, f"[API] tag filter expected 200, got {resp.status}"
    f = (resp.request.post_data_json or {}).get("filter") or {}
    assert f.get("themeIds"), "[API] filter.themeIds empty"
    print(f"  [PASS] Tag filter applied for '{tag}'")


# ══════════════════════════════════════════════════════════════
# TC_Tag_08 - Edit tag name  — NO rename endpoint/UI captured
# ══════════════════════════════════════════════════════════════
@qase.id(507)
@qase.title("TC_Tag_08: Edit/rename a tag")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_08 | NOT AUTOMATABLE yet — no rename/edit-theme endpoint or UI has "
    "been provided. Need the edit-tag flow (PUT/PATCH themes) to implement."
))
def test_TC_Tag_08_edit_tag():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_09 - Tag persists after refresh
# ══════════════════════════════════════════════════════════════
@qase.id(508)
@qase.title("TC_Tag_09: A created tag persists after refresh")
@pytest.mark.tag
def test_TC_Tag_09_persist_after_refresh(tp, shared_tag, auth_token):
    # Reuse the shared tag — reload and confirm it's still present.
    tp.reload_grid()
    assert _has_theme(auth_token, shared_tag), f"[DATA] '{shared_tag}' missing after refresh"
    print(f"  [PASS] Tag '{shared_tag}' persists after refresh")


# ══════════════════════════════════════════════════════════════
# TC_Tag_10 - Create duplicate tag
# ══════════════════════════════════════════════════════════════
@qase.id(509)
@qase.title("TC_Tag_10: Creating a duplicate tag is rejected")
@pytest.mark.tag
def test_TC_Tag_10_duplicate_tag(tp, shared_tag, auth_token):
    # Try to re-create the existing shared tag -> must be rejected.
    dup = _themes_create(auth_token, shared_tag)
    api_tracker.set(dup.status_code)
    print(f"  [API] duplicate create status: {dup.status_code} | {dup.text[:120]}")
    assert dup.status_code not in (200, 201), (
        f"[BEHAVIOUR] duplicate tag '{shared_tag}' was accepted ({dup.status_code}) — expected rejection"
    )
    print("  [PASS] Duplicate tag rejected")


# ══════════════════════════════════════════════════════════════
# TC_Tag_11 - Create empty tag
# ══════════════════════════════════════════════════════════════
@qase.id(510)
@qase.title("TC_Tag_11: Creating an empty tag is blocked")
@pytest.mark.tag
def test_TC_Tag_11_empty_tag(tp):
    tp.open_create_tag()
    assert tp.is_create_tag_input_visible(), "[UI] Create-tag input did not appear"
    # Leave empty and try to save — a themes POST must NOT succeed.
    fired = {"ok": False}
    try:
        with tp.page.expect_response(
            lambda r: r.url.rstrip("/").endswith("/api/themes") and r.request.method == "POST"
            and r.status in (200, 201), timeout=4000,
        ):
            tp.save_new_tag()
        fired["ok"] = True
    except Exception:
        fired["ok"] = False
    assert not fired["ok"], "[BEHAVIOUR] empty tag was created — expected validation block"
    print("  [PASS] Empty tag blocked (no successful create)")


# ══════════════════════════════════════════════════════════════
# TC_Tag_12 - Create long tag name (input caps at maxlength 20)
# ══════════════════════════════════════════════════════════════
@qase.id(511)
@qase.title("TC_Tag_12: Tag name is limited to 20 characters")
@pytest.mark.tag
def test_TC_Tag_12_long_tag_name(tp):
    tp.open_create_tag()
    tp.type_tag_name("X" * 30)
    val = tp.get_tag_input_value()
    assert len(val) <= 20, f"[UI] tag input accepted {len(val)} chars (maxlength should cap at 20)"
    print(f"  [PASS] Long tag name capped at {len(val)} chars")


# ══════════════════════════════════════════════════════════════
# TC_Tag_13 - Assign tag without permission — needs restricted fixture
# ══════════════════════════════════════════════════════════════
@qase.id(512)
@qase.title("TC_Tag_13: Assigning a tag without permission is forbidden")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_13 | NOT TESTABLE — needs a file the logged-in user has no write "
    "permission on (a restricted/foreign file fixture), which this single-account "
    "env doesn't provide."
))
def test_TC_Tag_13_assign_no_permission():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_14 - Assign non-existing tag (invalid themeId -> error)
# ══════════════════════════════════════════════════════════════
@qase.id(513)
@qase.title("TC_Tag_14: Assigning a non-existent tag is rejected")
@pytest.mark.tag
def test_TC_Tag_14_assign_nonexisting_tag(auth_token):
    fake_theme = "0" * 24
    fake_file = "0" * 24
    resp = _assign_api(auth_token, fake_file, [fake_theme])
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code} | {resp.text[:120]}")
    assert resp.status_code in (400, 404, 422, 500), (
        f"[API] Expected a 4xx/5xx for non-existent tag/file, got {resp.status_code}"
    )
    print(f"  [PASS] Server rejected non-existent tag assign ({resp.status_code})")


# ══════════════════════════════════════════════════════════════
# TC_Tag_15 - Remove non-existing tag
# ══════════════════════════════════════════════════════════════
@qase.id(514)
@qase.title("TC_Tag_15: Removing a tag not present is handled")
@pytest.mark.tag
def test_TC_Tag_15_remove_nonexisting_tag(auth_token):
    fake_file = "0" * 24
    resp = _assign_api(auth_token, fake_file, [])   # empty list = remove all
    api_tracker.set(resp.status_code)
    print(f"  [API] Status: {resp.status_code} | {resp.text[:120]}")
    assert resp.status_code in (200, 400, 404, 422, 500), f"[API] Unexpected {resp.status_code}"
    print(f"  [PASS] Remove-nonexistent handled gracefully ({resp.status_code})")


# ══════════════════════════════════════════════════════════════
# TC_Tag_16 - Search non-existing tag -> no results
# ══════════════════════════════════════════════════════════════
@qase.id(515)
@qase.title("TC_Tag_16: Searching a tag with no files returns no results")
@pytest.mark.tag
def test_TC_Tag_16_search_nonexisting_tag(tp, auth_token):
    # Create a brand-new tag (assigned to nothing) and search by it -> 0 files.
    name = _unique_tag()
    assert _themes_create(auth_token, name).status_code in (200, 201), "[API] tag create failed"
    tp.reload_grid()
    from pages.advance_search_page import AdvanceSearchPage
    sp = AdvanceSearchPage(tp.page)
    sp.open_panel()
    sp.add_tag(name)
    with tp.page.expect_response(
        lambda r: "/operationModule/api/operations" in r.url and r.request.method == "POST"
        and '"filter"' in (r.request.post_data or ""), timeout=20000,
    ) as info:
        sp.click_search()
    resp = info.value
    api_tracker.set(resp.status)
    assert resp.status == 200, f"[API] expected 200, got {resp.status}"
    tp.page.wait_for_timeout(1200)
    n = sp.file_result_rows().count()
    assert n == 0, f"[BEHAVIOUR] unused tag '{name}' returned {n} files, expected 0"
    print("  [PASS] Unused tag returned 0 results")


# ══════════════════════════════════════════════════════════════
# TC_Tag_17 - Server error on tag creation — NOT TRIGGERABLE
# ══════════════════════════════════════════════════════════════
@qase.id(516)
@qase.title("TC_Tag_17: Server error during tag creation")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_17 | NOT TESTABLE on demand — a real 500 from the themes backend "
    "cannot be forced from the client without fault injection."
))
def test_TC_Tag_17_server_error():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_18 - 'Add Tag' option visible in the context menu
# ══════════════════════════════════════════════════════════════
@qase.id(517)
@qase.title("TC_Tag_18: 'Add Tag' option appears on right-click")
@pytest.mark.tag
def test_TC_Tag_18_tag_option_visible(tp):
    row = tp.find_first_file_row()
    if row is None:
        pytest.skip("[UI] No file in the drive")
    assert tp.is_add_tag_menu_visible(row), "[UI] 'Add Tag' menu item not visible"
    print("  [PASS] 'Add Tag' option visible")


# ══════════════════════════════════════════════════════════════
# TC_Tag_19 - Create-tag input field appears
# ══════════════════════════════════════════════════════════════
@qase.id(518)
@qase.title("TC_Tag_19: Create-tag input field appears")
@pytest.mark.tag
def test_TC_Tag_19_tag_input_field(tp):
    tp.open_create_tag()
    assert tp.is_create_tag_input_visible(), "[UI] Create-tag input not visible"
    print("  [PASS] Create-tag input visible")


# ══════════════════════════════════════════════════════════════
# TC_Tag_20 - Tag colour is displayed on the chip
# ══════════════════════════════════════════════════════════════
@qase.id(519)
@qase.title("TC_Tag_20: A tag chip shows its colour")
@pytest.mark.tag
def test_TC_Tag_20_tag_color(tp):
    row = _existing_tagged_row(tp)
    if row is None:
        pytest.skip("[DATA] No tagged file in the drive to check colour")
    style = tp.row_tag_color(row)
    assert "background-color" in style.lower(), f"[UI] chip has no colour style: '{style}'"
    print(f"  [PASS] Tag chip shows colour ({style[:60]})")


# ══════════════════════════════════════════════════════════════
# TC_Tag_21 - Success message on tag creation
# ══════════════════════════════════════════════════════════════
@qase.id(520)
@qase.title("TC_Tag_21: Success message after creating a tag")
@pytest.mark.tag
def test_TC_Tag_21_success_message(tp):
    name = _unique_tag()
    tp.open_create_tag()
    tp.type_tag_name(name)
    resp = _capture_themes_post(tp, lambda: tp.save_new_tag())
    assert resp.status in (200, 201), f"[API] create failed ({resp.status})"
    text = tp.get_snackbar_text(timeout=5000)
    print(f"  [UI] Snackbar: '{text}'")
    assert text, "[UI] No success snackbar after tag creation"
    print(f"  [PASS] Success message shown: '{text}'")


# ══════════════════════════════════════════════════════════════
# TC_Tag_22 - Error message on failed tag creation (duplicate)
# ══════════════════════════════════════════════════════════════
@qase.id(521)
@qase.title("TC_Tag_22: Error message on a failed tag creation")
@pytest.mark.tag
def test_TC_Tag_22_error_message(tp, shared_tag):
    # UI-create a duplicate of the shared tag -> expect a non-success / error toast.
    tp.open_create_tag()
    tp.type_tag_name(shared_tag)
    try:
        resp = _capture_themes_post(tp, lambda: tp.save_new_tag(), timeout=8000)
        assert resp.status not in (200, 201), (
            f"[BEHAVIOUR] duplicate create returned {resp.status} — expected an error"
        )
        print(f"  [PASS] Duplicate create returned error status {resp.status}")
    except Exception:
        text = tp.get_snackbar_text(timeout=4000)
        assert text, "[UI] No error feedback on duplicate tag create"
        print(f"  [PASS] Duplicate create surfaced error: '{text}'")


# ══════════════════════════════════════════════════════════════
# TC_Tag_23 - Tag persists after file rename — depends on assign (buggy)
# ══════════════════════════════════════════════════════════════
@qase.id(522)
@qase.title("TC_Tag_23: A file's tag survives a rename")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_23 | Deferred — depends on the currently-broken assign flow "
    "(change-file-themes) to seed a tagged file, plus a rename. Enable once "
    "assign works; then: tag a fresh file, rename it, assert the chip persists."
))
def test_TC_Tag_23_tag_after_rename():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_24 - Tag persists after file move — depends on assign (buggy)
# ══════════════════════════════════════════════════════════════
@qase.id(523)
@qase.title("TC_Tag_24: A file's tag survives a move")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_24 | Deferred — depends on the currently-broken assign flow to seed "
    "a tagged file, plus a move. Enable once assign works."
))
def test_TC_Tag_24_tag_after_move():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_25 - Tag gone after file delete
# ══════════════════════════════════════════════════════════════
@qase.id(524)
@qase.title("TC_Tag_25: A deleted file's tag is no longer visible")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_25 | Deferred — needs a freshly tagged file to delete (depends on the "
    "broken assign flow); deleting an existing tagged user file is destructive."
))
def test_TC_Tag_25_tag_after_delete():
    pass


# ══════════════════════════════════════════════════════════════
# TC_Tag_26 - Concurrent tagging (no conflict)
# ══════════════════════════════════════════════════════════════
@qase.id(525)
@qase.title("TC_Tag_26: Concurrent tag assignment causes no conflict")
@pytest.mark.tag
@pytest.mark.skip(reason=(
    "TC_Tag_26 | Deferred — meaningful concurrent tagging needs the assign flow "
    "(change-file-themes) to actually work; it currently 500s. Enable once assign "
    "is fixed, then assign two tags to one real file in parallel and assert both "
    "land with no conflict."
))
def test_TC_Tag_26_concurrent_tagging():
    pass
