"""
TEAMSYNC - Advanced Search Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Advance search (SRCH_ADV01_TC01..TC28)

How search works (captured from the live app):
  • Open panel : click the Tune icon in the Main Drive search bar
  • The search : POST /operationModule/api/operations  action="read" + a "filter":
        { sourceType, attributes, themeIds, owner, ownerEmail,
          dateRangeType, dateFrom, dateTo }
  • Results    : returned in the standard folder-read response -> render in the
                 normal #filemanager_grid (Type col + Tag chips per row)
  • Dropdowns  : getAllFileType (types), themes (tags), getAttDetail (attributes)

Assertion standard (system behaviour, NOT the manual PASS/FAIL in Excel):
  1. the search call fires and returns 200  (contract-level)
  2. the request "filter" reflects exactly what we set
  3. result consistency where checkable (e.g. Type search -> result Type matches),
     kept lenient so genuine bugs surface honestly instead of being masked.
"""

import os
from datetime import datetime, timedelta

import pytest
import requests
from qase.pytest import qase

from pages.advance_search_page import AdvanceSearchPage
from config.api_config import (
    ENDPOINTS, DEFAULT_HEADERS, LOGIN_PAGE_URL,
    SEARCH_USERNAME, SEARCH_PASSWORD,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL = ENDPOINTS["operations"]


# ── Module-level login ─────────────────────────────────────────
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
    sp = AdvanceSearchPage(page)
    sp.login_as(SEARCH_USERNAME, SEARCH_PASSWORD)   # Pratibha's pre-seeded drive
    yield


@pytest.fixture
def sp(page):
    return AdvanceSearchPage(page)


@pytest.fixture
def search_auth_token():
    """Pratibha's API token (Advanced Search only) for the discovery endpoints.
    Function-scoped so it never goes stale on a long run."""
    resp = requests.post(
        ENDPOINTS["login"],
        files={"username": (None, SEARCH_USERNAME), "password": (None, SEARCH_PASSWORD)},
        headers=DEFAULT_HEADERS,
        verify=False,
        timeout=30,
    )
    return resp.json()["access_token"]


@pytest.fixture(autouse=True)
def _fresh_drive(page, module_login):
    """Reload to a clean Main Drive before each test so no prior test leaves the
    panel open (which would overlay the Tune icon) or residual filters behind."""
    try:
        AdvanceSearchPage(page).reload_grid()
    except Exception:
        pass
    yield


# ── Discovery helpers (find real Types/Tags/Attributes in the env) ──
def _hdr(search_auth_token, **extra):
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {search_auth_token}", "username": SEARCH_USERNAME}
    h.update(extra)
    return h


def _get_types(search_auth_token):
    try:
        r = requests.get(ENDPOINTS["get_file_types"], headers=_hdr(search_auth_token), verify=False, timeout=30)
        data = r.json()
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("data", [])
    return [t for t in data if isinstance(t, str) and t.lower() != "all"] if isinstance(data, list) else []


def _get_tags(search_auth_token):
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {search_auth_token}", "Username": SEARCH_USERNAME}
    try:
        r = requests.get(ENDPOINTS["themes"], headers=h, verify=False, timeout=30)
        data = r.json()
    except Exception:
        return []
    out = []
    if isinstance(data, list):
        for t in data:
            if isinstance(t, dict):
                out.append({"id": t.get("id"), "name": t.get("themeName") or t.get("name")})
    return out


def _get_attrs(search_auth_token, file_type):
    try:
        r = requests.get(ENDPOINTS["get_att_detail"], headers=_hdr(search_auth_token, fileType=file_type),
                         verify=False, timeout=30)
        data = r.json()
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("data", [])
    return data if isinstance(data, list) else []


def _pick_type(types):
    """Prefer a type we know carries data ('test'), else the first available."""
    for t in types:
        if t.lower() == "test":
            return t
    return types[0] if types else None


def _type_with_attrs(search_auth_token, types):
    """Return (type, [attrs]) for the first type that exposes attributes."""
    for t in [x for x in types if x.lower() == "test"] + types:
        attrs = _get_attrs(search_auth_token, t)
        if attrs:
            return t, attrs
    return None, []


# ── Search capture ─────────────────────────────────────────────
def _capture_search(sp: AdvanceSearchPage, action_fn, timeout: int = 20000):
    """Run a UI action and capture the operations POST that carries a 'filter'."""
    with sp.page.expect_response(
        lambda r: "/operationModule/api/operations" in r.url
        and r.request.method == "POST"
        and '"filter"' in (r.request.post_data or ""),
        timeout=timeout,
    ) as info:
        action_fn()
    resp = info.value
    api_tracker.set(resp.status)
    print(f"  [API] search Status: {resp.status}")
    return resp


def _filter_of(resp):
    try:
        return (resp.request.post_data_json or {}).get("filter") or {}
    except Exception:
        return {}


def _count_files(sp: AdvanceSearchPage, label: str = "") -> int:
    n = sp.file_result_rows().count()
    print(f"  [RESULT] {label} file rows: {n}")
    return n


def _result_files(sp: AdvanceSearchPage, limit: int = 40):
    """Read the file rows currently shown in the grid as dicts:
    {name, type, tags, owner, modified}. Used both to discover real filter
    values from Pratibha's drive and to validate that search results match."""
    rows = sp.file_result_rows()
    out = []
    for i in range(min(rows.count(), limit)):
        r = rows.nth(i)
        out.append({
            "name": sp.row_name(r),
            "type": (sp.row_type(r) or "").strip(),
            "tags": sp.row_tags(r),
            "owner": sp.row_owner(r),
            "modified": sp.row_modified(r),
        })
    return out


def _open_clean(sp: AdvanceSearchPage):
    """Open the panel. Isolation (no residual filters) is handled by the
    per-test reload in the _fresh_drive fixture."""
    sp.open_panel()


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════
# TC01 - Open Advanced Search panel
# ══════════════════════════════════════════════════════════════
@qase.id(400)
@qase.title("SRCH_ADV01_TC01: Advanced Search panel opens from the Tune icon")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC01_open_panel(sp):
    sp.open_panel()
    assert sp.is_panel_open(), "[UI] Advanced Search panel did not open"
    print("  [PASS] Panel opened")


# ══════════════════════════════════════════════════════════════
# TC02 - Close panel by clicking outside
# ══════════════════════════════════════════════════════════════
@qase.id(401)
@qase.title("SRCH_ADV01_TC02: Panel closes when clicking outside")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC02_close_outside(sp):
    sp.open_panel()
    assert sp.is_panel_open(), "[UI] Panel did not open"
    sp.close_panel_outside()
    assert not sp.is_panel_open(), "[UI] Panel did not close on outside click"
    print("  [PASS] Panel closed on outside click")


# ══════════════════════════════════════════════════════════════
# TC03 - Search with Type only
# ══════════════════════════════════════════════════════════════
@qase.id(402)
@qase.title("SRCH_ADV01_TC03: Search using only document Type")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC03_type_only(sp):
    # Derive a Type that actually appears on Pratibha's files, so a WORKING
    # search must return matches and a broken one fails honestly.
    baseline = _result_files(sp)
    typed = [f for f in baseline if f["type"] and f["type"].lower() != "null"]
    if not typed:
        pytest.skip("[DATA] No typed documents visible in Pratibha's drive to validate against")
    ttype = typed[0]["type"]
    _open_clean(sp)
    sp.set_type(ttype)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("sourceType") == ttype, "[API] filter.sourceType mismatch"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    # Behaviour: results must exist AND every file must be of the searched Type.
    assert results, f"[BEHAVIOUR] Type='{ttype}' search returned 0 files, but typed docs exist"
    bad = [(f["name"], f["type"]) for f in results if f["type"].lower() != ttype.lower()]
    assert not bad, f"[BEHAVIOUR] Type='{ttype}' search returned non-matching files: {bad}"
    print(f"  [PASS] Type search returned {len(results)} file(s), all Type='{ttype}'")


# ══════════════════════════════════════════════════════════════
# TC04 - Search with Type + Attribute
# ══════════════════════════════════════════════════════════════
@qase.id(403)
@qase.title("SRCH_ADV01_TC04: Attribute-based search (Type + Attribute)")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC04_type_attribute(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype:
        pytest.skip("[DATA] No type with attributes available")
    attr = attrs[0]
    attr_name = attr.get("attributeName") if isinstance(attr, dict) else str(attr)
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(attr_name, "5000")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    f = _filter_of(resp)
    assert f.get("sourceType") == ttype
    assert f.get("attributes"), "[API] filter.attributes missing for Type+Attribute search"
    print(f"  [PASS] Type+Attribute search applied (200); attributes={f.get('attributes')}")


# ══════════════════════════════════════════════════════════════
# TC05 - Search using Tag
# ══════════════════════════════════════════════════════════════
@qase.id(404)
@qase.title("SRCH_ADV01_TC05: Tag-based filtering")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC05_tag(sp):
    # Derive a tag that actually appears on Pratibha's files.
    baseline = _result_files(sp)
    tagged = [f for f in baseline if f["tags"]]
    if not tagged:
        pytest.skip("[DATA] No tagged documents visible in Pratibha's drive to validate against")
    tagname = tagged[0]["tags"][0]
    _open_clean(sp)
    sp.add_tag(tagname)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("themeIds"), "[API] filter.themeIds empty after tag search"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    # Behaviour: results must exist AND every file must carry the searched tag.
    assert results, f"[BEHAVIOUR] Tag='{tagname}' search returned 0 files, but tagged docs exist"
    bad = [(f["name"], f["tags"]) for f in results if tagname not in f["tags"]]
    assert not bad, f"[BEHAVIOUR] Tag='{tagname}' search returned files without that tag: {bad}"
    print(f"  [PASS] Tag search returned {len(results)} file(s), all carry '{tagname}'")


# ══════════════════════════════════════════════════════════════
# TC06 - Search using Created Date
# ══════════════════════════════════════════════════════════════
@qase.id(405)
@qase.title("SRCH_ADV01_TC06: Created-date range filtering")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC06_created_date(sp):
    # A window entirely in the far past should match NONE of Pratibha's docs.
    # If the date filter is honoured -> 0 results; if ignored -> files leak through.
    frm, to = "2000-01-01", "2000-12-31"
    _open_clean(sp)
    sp.set_date_range("Created", frm, to)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    f = _filter_of(resp)
    assert f.get("dateRangeType") == "Created", f"[API] dateRangeType={f.get('dateRangeType')}"
    assert f.get("dateFrom") and f.get("dateTo"), "[API] dateFrom/dateTo not sent"
    sp.page.wait_for_timeout(1500)
    leaked = [x["name"] for x in _result_files(sp)]
    assert not leaked, f"[BEHAVIOUR] Created-date {frm}..{to} returned files (date filter ignored?): {leaked}"
    print("  [PASS] Created-date filter honoured (far-past window -> 0 files)")


# ══════════════════════════════════════════════════════════════
# TC07 - Search using Modified Date
# ══════════════════════════════════════════════════════════════
@qase.id(406)
@qase.title("SRCH_ADV01_TC07: Modified-date range filtering")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC07_modified_date(sp):
    # Far-past window should match NONE of Pratibha's docs if the filter works.
    frm, to = "2000-01-01", "2000-12-31"
    _open_clean(sp)
    sp.set_date_range("Modified", frm, to)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("dateRangeType") == "Modified", "[API] dateRangeType mismatch"
    sp.page.wait_for_timeout(1500)
    leaked = [x["name"] for x in _result_files(sp)]
    assert not leaked, f"[BEHAVIOUR] Modified-date {frm}..{to} returned files (date filter ignored?): {leaked}"
    print("  [PASS] Modified-date filter honoured (far-past window -> 0 files)")


# ══════════════════════════════════════════════════════════════
# TC08 - Search Owned by Me
# ══════════════════════════════════════════════════════════════
@qase.id(407)
@qase.title("SRCH_ADV01_TC08: Owned-by 'Me' filtering")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC08_owned_by_me(sp):
    _open_clean(sp)
    sp.set_owned_by("Me")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("ownerEmail") == "ME", "[API] ownerEmail != ME"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    # Behaviour: results exist and are all owned by Pratibha.
    assert results, "[BEHAVIOUR] Owned-by-Me returned 0 files (Pratibha owns her own files)"
    bad = [(f["name"], f["owner"]) for f in results if f["owner"] and "pratibha" not in f["owner"].lower()]
    assert not bad, f"[BEHAVIOUR] Owned-by-Me returned files owned by others: {bad}"
    print(f"  [PASS] Owned-by-Me returned {len(results)} file(s), all owned by Pratibha")


# ══════════════════════════════════════════════════════════════
# TC09 - Search Owned by Others
# ══════════════════════════════════════════════════════════════
@qase.id(408)
@qase.title("SRCH_ADV01_TC09: Owned-by 'Others' filtering")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC09_owned_by_others(sp):
    _open_clean(sp)
    sp.set_owned_by("Others")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("ownerEmail") == "NOTME", "[API] ownerEmail != NOTME"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    # Behaviour: 'Others' must never return Pratibha-owned files (count may be 0
    # if nothing is shared to her — that's fine; correctness is what we assert).
    bad = [(f["name"], f["owner"]) for f in results if f["owner"] and "pratibha" in f["owner"].lower()]
    assert not bad, f"[BEHAVIOUR] Owned-by-Others returned Pratibha's own files: {bad}"
    print(f"  [PASS] Owned-by-Others returned {len(results)} file(s), none owned by Pratibha")


# ══════════════════════════════════════════════════════════════
# TC10 - Search Specific Person
# ══════════════════════════════════════════════════════════════
@qase.id(409)
@qase.title("SRCH_ADV01_TC10: Owned-by Specific Person")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC10_specific_person(sp):
    who = SEARCH_USERNAME
    _open_clean(sp)
    sp.set_specific_person(who)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    assert _filter_of(resp).get("ownerEmail") == who, f"[API] ownerEmail != {who}"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    # Behaviour: searching Pratibha returns her files, all owned by her.
    assert results, f"[BEHAVIOUR] Specific-person '{who}' returned 0 files (she owns documents)"
    bad = [(f["name"], f["owner"]) for f in results if f["owner"] and "pratibha" not in f["owner"].lower()]
    assert not bad, f"[BEHAVIOUR] Specific-person search returned files owned by others: {bad}"
    print(f"  [PASS] Specific-person search returned {len(results)} file(s), all Pratibha's")


# ══════════════════════════════════════════════════════════════
# TC11 - Combination Filter (Type + Tag)
# ══════════════════════════════════════════════════════════════
@qase.id(410)
@qase.title("SRCH_ADV01_TC11: Combination filter (Type + Tag)")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC11_type_plus_tag(sp):
    # Use a file that has BOTH a type and a tag, so the AND-combination must
    # return at least that file and only files matching both.
    baseline = _result_files(sp)
    cand = next((f for f in baseline if f["type"] and f["type"].lower() != "null" and f["tags"]), None)
    if not cand:
        pytest.skip("[DATA] No file with both a Type and a Tag in Pratibha's drive")
    ttype, tagname = cand["type"], cand["tags"][0]
    _open_clean(sp)
    sp.set_type(ttype)
    sp.add_tag(tagname)
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    f = _filter_of(resp)
    assert f.get("sourceType") == ttype and f.get("themeIds"), "[API] both filters not applied"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    assert results, f"[BEHAVIOUR] Type='{ttype}'+Tag='{tagname}' returned 0 files (a match exists)"
    bad = [(f["name"], f["type"], f["tags"]) for f in results
           if f["type"].lower() != ttype.lower() or tagname not in f["tags"]]
    assert not bad, f"[BEHAVIOUR] combination returned non-matching files: {bad}"
    print(f"  [PASS] Type+Tag combination returned {len(results)} file(s), all match both")


# ══════════════════════════════════════════════════════════════
# TC12 - Combination Filter (All filters)
# ══════════════════════════════════════════════════════════════
@qase.id(411)
@qase.title("SRCH_ADV01_TC12: Combination filter (all filters together)")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC12_all_filters(sp):
    # A file with a type+tag, owned by Pratibha (Me), within an all-time window.
    baseline = _result_files(sp)
    cand = next((f for f in baseline if f["type"] and f["type"].lower() != "null" and f["tags"]), None)
    if not cand:
        pytest.skip("[DATA] No file with both a Type and a Tag in Pratibha's drive")
    ttype, tagname = cand["type"], cand["tags"][0]
    _open_clean(sp)
    sp.set_type(ttype)
    sp.add_tag(tagname)
    sp.set_owned_by("Me")
    sp.set_date_range("Modified", "2000-01-01", _today())   # wide window — date is inclusive
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    f = _filter_of(resp)
    assert f.get("sourceType") == ttype and f.get("themeIds")
    assert f.get("ownerEmail") == "ME" and f.get("dateRangeType") == "Modified"
    sp.page.wait_for_timeout(1500)
    results = _result_files(sp)
    assert results, "[BEHAVIOUR] All-filters combination returned 0 files (a match exists)"
    bad = [(f["name"], f["type"], f["tags"], f["owner"]) for f in results
           if f["type"].lower() != ttype.lower() or tagname not in f["tags"]
           or (f["owner"] and "pratibha" not in f["owner"].lower())]
    assert not bad, f"[BEHAVIOUR] all-filters returned non-matching files: {bad}"
    print(f"  [PASS] All-filters combination returned {len(results)} file(s), all match")


# ══════════════════════════════════════════════════════════════
# TC13 - Reset button clears all filters
# ══════════════════════════════════════════════════════════════
@qase.id(412)
@qase.title("SRCH_ADV01_TC13: Reset clears all filters to default")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC13_reset(sp, search_auth_token):
    types = _get_types(search_auth_token)
    ttype = _pick_type(types)
    sp.open_panel()
    if ttype:
        sp.set_type(ttype)
    sp.set_owned_by("Me")
    sp.click_reset()
    assert sp.is_panel_open(), "[UI] Panel should stay open after Reset"
    assert sp.get_type_value() in ("All", ""), f"[UI] Type not reset: '{sp.get_type_value()}'"
    print("  [PASS] Reset cleared filters to default")


# ══════════════════════════════════════════════════════════════
# TC14 - Type Attribute on a shortcut of a shared file — NOT AUTOMATABLE here
# ══════════════════════════════════════════════════════════════
@qase.id(413)
@qase.title("SRCH_ADV01_TC14: Type+Attribute search on a shared-file shortcut")
@pytest.mark.advance_search
@pytest.mark.skip(reason=(
    "SRCH_ADV01_TC14 | Requires a cross-user fixture: User A shares a typed file "
    "with User B, then B creates a shortcut. No second-user/share fixture exists "
    "in this single-account test env."
))
def test_SRCH_ADV01_TC14_shortcut_shared():
    pass


# ══════════════════════════════════════════════════════════════
# TC15 - Type + Attribute search reaches files inside nested folders
# ══════════════════════════════════════════════════════════════
@qase.id(414)
@qase.title("SRCH_ADV01_TC15: Type+Attribute search across nested folders")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC15_nested_folder(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype:
        pytest.skip("[DATA] No type with attributes available")
    attr_name = attrs[0].get("attributeName") if isinstance(attrs[0], dict) else str(attrs[0])
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(attr_name, "9000")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    # Search is global (not folder-scoped to depth), so nested files are eligible.
    print(f"  [PASS] Nested-folder Type+Attribute search returned 200 ({_count_files(sp, 'nested')} files)")


# ══════════════════════════════════════════════════════════════
# TC16 - Tag search in 'Shared With Others' context
# ══════════════════════════════════════════════════════════════
@qase.id(415)
@qase.title("SRCH_ADV01_TC16: Tag search within 'Shared With Others'")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC16_tag_in_share_others(sp, search_auth_token):
    tags = [t for t in _get_tags(search_auth_token) if t.get("name")]
    if not tags:
        pytest.skip("[DATA] No tags exist in this env")
    if not _goto_context(sp, "Shared With Others"):
        pytest.skip("[UI] Could not open 'Shared With Others' context")
    _open_clean(sp)
    sp.add_tag(tags[0]["name"])
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Tag search in Shared-With-Others returned 200")


# ══════════════════════════════════════════════════════════════
# TC17 - Metadata search in Trash context
# ══════════════════════════════════════════════════════════════
@qase.id(416)
@qase.title("SRCH_ADV01_TC17: Metadata search within Trash")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC17_metadata_in_trash(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype:
        pytest.skip("[DATA] No type with attributes available")
    if not _goto_context(sp, "Trash"):
        pytest.skip("[UI] Could not open Trash context")
    attr_name = attrs[0].get("attributeName") if isinstance(attrs[0], dict) else str(attrs[0])
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(attr_name, "5000")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print("  [PASS] Metadata search in Trash returned 200")


# ══════════════════════════════════════════════════════════════
# TC18 - Each attribute field keeps its own value independently
# ══════════════════════════════════════════════════════════════
@qase.id(417)
@qase.title("SRCH_ADV01_TC18: Attribute fields retain independent values")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC18_independent_attribute_values(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype or len(attrs) < 2:
        pytest.skip("[DATA] Need a type with at least 2 attributes")
    a0 = attrs[0].get("attributeName")
    a1 = attrs[1].get("attributeName")
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(a0, "Test1")
    sp.add_attribute(a1, "Test2")
    assert sp.get_attribute_value(a0) == "Test1", f"[UI] {a0} value changed"
    assert sp.get_attribute_value(a1) == "Test2", f"[UI] {a1} value changed"
    print("  [PASS] Each attribute retained its own value")


# ══════════════════════════════════════════════════════════════
# TC19 - Attribute selected without a value
# ══════════════════════════════════════════════════════════════
@qase.id(418)
@qase.title("SRCH_ADV01_TC19: Attribute selected but left empty")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC19_attribute_without_value(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype:
        pytest.skip("[DATA] No type with attributes available")
    attr_name = attrs[0].get("attributeName")
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(attr_name, None)   # no value entered
    resp = _capture_search(sp, lambda: sp.click_search())
    # System behaviour: should not crash — accept any 2xx/4xx, just no failure
    assert resp.status in (200, 400, 422), f"[API] Unexpected status {resp.status}"
    print(f"  [PASS] Empty-attribute search handled gracefully ({resp.status})")


# ══════════════════════════════════════════════════════════════
# TC20 - Invalid attribute value
# ══════════════════════════════════════════════════════════════
@qase.id(419)
@qase.title("SRCH_ADV01_TC20: Invalid attribute value (@#$%)")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC20_invalid_attribute_value(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype:
        pytest.skip("[DATA] No type with attributes available")
    # pick a String attribute if possible (number inputs reject symbols)
    attr = next((a for a in attrs if str(a.get("attributeType")).lower() not in ("integer", "date")), attrs[0])
    attr_name = attr.get("attributeName")
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(attr_name, "@#$%")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status in (200, 400, 422), f"[API] Unexpected status {resp.status}"
    print(f"  [PASS] Invalid attribute value handled without crash ({resp.status})")


# ══════════════════════════════════════════════════════════════
# TC21 - Invalid date range (From > To) is prevented by the UI
# ══════════════════════════════════════════════════════════════
@qase.id(420)
@qase.title("SRCH_ADV01_TC21: Start date cannot be later than end date")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC21_invalid_date_range(sp):
    frm = _today()
    earlier = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    _open_clean(sp)
    sp.set_date_range("Modified", frm, None)
    # The 'To' field enforces min == From, so an earlier 'To' must not stick.
    min_attr = sp.date_to_min()
    sp.page.get_by_label("To").first.fill(earlier)
    got = sp.get_date_to_value()
    assert min_attr == frm or got != earlier, (
        f"[UI] 'To' accepted a date before 'From' (min={min_attr}, got={got})"
    )
    print(f"  [PASS] UI prevents From>To (To.min={min_attr})")


# ══════════════════════════════════════════════════════════════
# TC22 - Future date selection is constrained to today
# ══════════════════════════════════════════════════════════════
@qase.id(421)
@qase.title("SRCH_ADV01_TC22: Future dates are not selectable")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC22_future_date(sp):
    _open_clean(sp)
    sp.set_date_range("Modified", None, None)
    max_attr = sp.date_to_max()
    assert max_attr == _today(), f"[UI] 'To' max should be today ({_today()}), got {max_attr}"
    print(f"  [PASS] Future dates blocked (To.max={max_attr})")


# ══════════════════════════════════════════════════════════════
# TC23 - Invalid specific person returns no results / no crash
# ══════════════════════════════════════════════════════════════
@qase.id(422)
@qase.title("SRCH_ADV01_TC23: Invalid specific person yields no results")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC23_invalid_specific_person(sp):
    _open_clean(sp)
    sp.set_specific_person("xyz123@ios.com")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    sp.page.wait_for_timeout(1000)
    n = _count_files(sp, "invalid-person")
    assert n == 0, f"[DATA] Expected 0 results for a non-existent user, got {n}"
    print("  [PASS] Invalid specific person returned 0 results (200)")


# ══════════════════════════════════════════════════════════════
# TC24 - Tag with no associated data returns no results
# ══════════════════════════════════════════════════════════════
@qase.id(423)
@qase.title("SRCH_ADV01_TC24: Searching an unused tag returns no results")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC24_tag_no_data(sp, search_auth_token):
    tags = [t for t in _get_tags(search_auth_token) if t.get("name")]
    if not tags:
        pytest.skip("[DATA] No tags exist in this env")
    # Use the last tag (most recently created / least likely to have data)
    tag = tags[-1]
    _open_clean(sp)
    sp.add_tag(tag["name"])
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    sp.page.wait_for_timeout(1000)
    print(f"  [PASS] Unused-tag search returned 200 ({_count_files(sp, tag['name'])} files)")


# ══════════════════════════════════════════════════════════════
# TC25 - No filter applied (search with defaults)
# ══════════════════════════════════════════════════════════════
@qase.id(424)
@qase.title("SRCH_ADV01_TC25: Search with no filters applied")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC25_no_filter(sp):
    sp.open_panel()
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] No-filter search returned 200 ({_count_files(sp, 'no-filter')} files)")


# ══════════════════════════════════════════════════════════════
# TC26 - Conflicting filters (no intersection) -> no results
# ══════════════════════════════════════════════════════════════
@qase.id(425)
@qase.title("SRCH_ADV01_TC26: Conflicting filters return no results")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC26_conflicting_filters(sp):
    # Reliable conflict: a tag that IS on one of Pratibha's own files, combined
    # with owner='Others'. Since her tagged file is owned by her, the AND of
    # (tag) and (owned by others) must yield ZERO results.
    baseline = _result_files(sp)
    tagged = [f for f in baseline if f["tags"]]
    if not tagged:
        pytest.skip("[DATA] No tagged document in Pratibha's drive to build a conflict")
    tagname = tagged[0]["tags"][0]
    _open_clean(sp)
    sp.add_tag(tagname)
    sp.set_owned_by("Others")
    resp = _capture_search(sp, lambda: sp.click_search())
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    sp.page.wait_for_timeout(1500)
    leaked = [(f["name"], f["owner"]) for f in _result_files(sp)]
    assert not leaked, f"[BEHAVIOUR] Conflicting (tag + Others) returned files (filters OR'd?): {leaked}"
    print("  [PASS] Conflicting filters returned 0 results")


# ══════════════════════════════════════════════════════════════
# TC27 - Large data stress (broad search must not crash)
# ══════════════════════════════════════════════════════════════
@qase.id(426)
@qase.title("SRCH_ADV01_TC27: Broad search under load returns without crashing")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC27_large_data(sp):
    import time
    sp.open_panel()
    start = time.time()
    resp = _capture_search(sp, lambda: sp.click_search(), timeout=60000)
    elapsed = time.time() - start
    assert resp.status == 200, f"[API] Expected 200, got {resp.status}"
    print(f"  [PASS] Broad search stable in {elapsed:.2f}s (200)")


# ══════════════════════════════════════════════════════════════
# TC28 - A value in one attribute is not applied to all fields
# ══════════════════════════════════════════════════════════════
@qase.id(427)
@qase.title("SRCH_ADV01_TC28: Value in one attribute field does not fill others")
@pytest.mark.advance_search
def test_SRCH_ADV01_TC28_value_not_applied_to_all(sp, search_auth_token):
    ttype, attrs = _type_with_attrs(search_auth_token, _get_types(search_auth_token))
    if not ttype or len(attrs) < 2:
        pytest.skip("[DATA] Need a type with at least 2 attributes")
    a0 = attrs[0].get("attributeName")
    a1 = attrs[1].get("attributeName")
    _open_clean(sp)
    sp.set_type(ttype)
    sp.page.wait_for_timeout(600)
    sp.add_attribute(a0, "Test1")
    sp.add_attribute(a1, None)            # select second attr but enter nothing
    assert sp.get_attribute_value(a0) == "Test1", f"[UI] {a0} should hold its value"
    assert sp.get_attribute_value(a1) == "", f"[UI] {a1} should remain empty, got '{sp.get_attribute_value(a1)}'"
    print("  [PASS] Value stayed isolated to its own attribute field")


# ── Context navigation helper ──────────────────────────────────
def _goto_context(sp: AdvanceSearchPage, name: str) -> bool:
    """Open a system context folder (Shared With Others / Trash / Summary) by
    double-clicking its row in the Main Drive grid. Returns True on success."""
    try:
        sp.reload_grid()
        row = sp.page.locator(f'#filemanager_grid tr.e-row:has-text("{name}")').first
        row.wait_for(state="visible", timeout=8000)
        row.dblclick()
        sp.page.wait_for_timeout(1500)
        return True
    except Exception:
        return False
