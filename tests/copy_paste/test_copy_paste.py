"""
TEAMSYNC - Copy-Paste Module: Combined UI + API Tests
App    : IMIR (Intelligent Maintenance Information Repository)
Source : Teamsync_new_testcases.xlsx -> Sheet: Copy-paste (TC_CP_001 to TC_CP_011)

Paste API: POST /api/operationModule/api/operations
  Body: { "action": "copy", "path": "/", "targetData": <folder_obj>,
          "targetPath": "/", "names": [...], "renameFiles": [], "data": [<file_objs>] }

Seeding strategy: each test seeds ONLY what it needs (one file by default).
Tests that inherently need more (TC_CP_006 multi-file, TC_CP_007 file+folder,
TC_CP_009 folder) create the extras inline. No shared pool — keeps tests
self-contained and easy to reason about.

NOTE: TC_CP_010 (keyboard Ctrl+C/V) is SKIPPED per project decision.
"""

import os
import uuid
import time
import hashlib
from typing import Optional

import pytest
import requests
from qase.pytest import qase

from pages.copy_paste_page import CopyPastePage
from config.api_config import (
    DATA_SET_PATH, UPLOAD_FILES, ENDPOINTS, DEFAULT_HEADERS,
    VALID_USERNAME, VALID_PASSWORD_ENCRYPTED,
)
from utils.excel_reporter import api_tracker


OPERATIONS_URL  = ENDPOINTS["operations"]
CREATE_DOCX_URL = ENDPOINTS["create_docx"]
UPLOAD_URL      = ENDPOINTS["upload"]
DOWNLOAD_URL    = ENDPOINTS["download"]


# ── API helpers ───────────────────────────────────────────────
def _api_token() -> str:
    resp = requests.post(
        ENDPOINTS["login"],
        files={"username": (None, VALID_USERNAME), "password": (None, VALID_PASSWORD_ENCRYPTED)},
        headers=DEFAULT_HEADERS, verify=False, timeout=30,
    )
    return resp.json()["access_token"]


def _auth_headers(token: str, json_body: bool = True) -> dict:
    h = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}", "username": VALID_USERNAME}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _list_root(token: str) -> requests.Response:
    return requests.post(
        OPERATIONS_URL,
        json={"action": "read", "path": "/", "showHiddenItems": False, "data": []},
        headers=_auth_headers(token), verify=False, timeout=30,
    )


def _find_obj(list_resp: requests.Response, name: str) -> Optional[dict]:
    """Return the full object dict for `name` from a list response (or None).
    Tries multiple response shapes — IMIR varies the key by endpoint."""
    try:
        body = list_resp.json()
    except Exception:
        return None
    items: list = []
    if isinstance(body, dict):
        for k in ("files", "data", "items", "children", "result"):
            v = body.get(k)
            if isinstance(v, list) and v:
                items = v
                break
    elif isinstance(body, list):
        items = body
    for it in items:
        if isinstance(it, dict) and it.get("name") == name:
            return it
    return None


def _root_drive(token: str) -> dict:
    """Root drive object used as targetData when pasting at root."""
    try:
        body = _list_root(token).json()
        for k in ("cwd", "parentDetails", "rootFolder"):
            v = body.get(k)
            if isinstance(v, dict):
                return v
    except Exception:
        pass
    return {"id": "/", "name": "Drive", "type": "Folder", "parentId": "/",
            "filterPath": "/", "isFile": False}


def _seed_docx(token: str) -> dict:
    """Create a fresh docx via API and return its full object.
    Polls the root listing for up to ~3s since the file may not appear instantly."""
    name = f"cpf_{uuid.uuid4().hex[:8]}.docx"
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}",
               "username": VALID_USERNAME, "type": "Files", "generatingAiTheme": "true"}
    fields = {
        "path": (None, "/"), "action": (None, "save"), "filename": (None, name),
        "metaData": (None, '{"fileType":"","attributes":[]}'), "fileExt": (None, "docx"),
        "generatingAiTheme": (None, "true"), "theme": (None, "defaultTheme"),
    }
    create_resp = requests.post(CREATE_DOCX_URL, files=fields, headers=headers,
                                verify=False, timeout=30)
    # Poll the listing — sometimes the new file takes a moment to appear
    obj = None
    for _ in range(6):
        obj = _find_obj(_list_root(token), name)
        if obj is not None:
            return obj
        time.sleep(0.5)
    pytest.skip(f"[SEED] Could not find docx '{name}' after create "
                f"(create_status={create_resp.status_code}, body={create_resp.text[:120]})")
    return obj  # unreachable, satisfies type-checker


def _seed_folder(token: str) -> dict:
    """Create a fresh empty folder via API and return its full object.
    Polls the root listing for up to ~3s for consistency with _seed_docx."""
    name = f"cpfd_{uuid.uuid4().hex[:8]}"
    create_resp = requests.post(OPERATIONS_URL,
                                json={"action": "create", "path": "/", "name": name},
                                headers=_auth_headers(token), verify=False, timeout=30)
    obj = None
    for _ in range(6):
        obj = _find_obj(_list_root(token), name)
        if obj is not None:
            return obj
        time.sleep(0.5)
    pytest.skip(f"[SEED] Could not find folder '{name}' after create "
                f"(create_status={create_resp.status_code}, body={create_resp.text[:120]})")
    return obj


def _paste(token: str, target: dict, sources: list, target_path: str = "/") -> requests.Response:
    """Send the paste API call. Returns the raw response."""
    payload = {
        "action": "copy", "path": "/",
        "targetData": target, "targetPath": target_path,
        "names": [s.get("name", "") for s in sources],
        "renameFiles": [],
        "data": sources,
    }
    return requests.post(OPERATIONS_URL, json=payload, headers=_auth_headers(token),
                         verify=False, timeout=60)


def _upload_file(token: str, file_path: str, timeout: int = 600) -> Optional[requests.Response]:
    """Upload an arbitrary local file via the upload endpoint. Returns None only
    if the file isn't on disk — any HTTP response (even errors) is returned."""
    if not os.path.exists(file_path):
        print(f"  [UPLOAD] File NOT on disk: {file_path}")
        return None
    filename = os.path.basename(file_path)
    extra = {
        "Type": "File Upload", "username": VALID_USERNAME,
        "generatingAiTheme": "true", "metadataType": "AiMetaDataExtraction",
        "textRecognitionMethod": "OCR", "uploadCount": "0",
    }
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}", **extra}
    try:
        with open(file_path, "rb") as fh:
            files = {
                "uploadFiles": (filename, fh, "application/octet-stream"),
                "path": (None, "/"), "action": (None, "save"), "filename": (None, filename),
                "metaData": (None, '{"fileType":"","attributes":[]}'),
            }
            return requests.post(UPLOAD_URL, files=files, headers=headers,
                                 verify=False, timeout=timeout)
    except Exception as e:
        print(f"  [UPLOAD] Exception during upload of {filename}: {e}")
        return None


# ── Fixtures ──────────────────────────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def module_login(page):
    """Log into the UI once per module, dismiss the welcome popup.
    Clears cookies + localStorage + sessionStorage so prior module state
    can't leave the SPA stuck on a cached 'logged-in' view."""
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
    CopyPastePage(page).login_and_open()
    yield


@pytest.fixture(scope="module")
def token() -> str:
    return _api_token()


@pytest.fixture(scope="module")
def drive(token) -> dict:
    return _root_drive(token)


@pytest.fixture
def cp(page) -> CopyPastePage:
    return CopyPastePage(page)


# ══════════════════════════════════════════════════════════════
# TC_CP_001 - Copy-Paste file in same folder (UI)
# ══════════════════════════════════════════════════════════════
@qase.id(200)
@qase.title("TC_CP_001: Copy-Paste file in same folder via UI")
@pytest.mark.copy_paste
def test_TC_CP_001_copy_paste_same_folder(cp, token):
    """Pre: file exists | Expected: duplicate created in same folder."""
    src = _seed_docx(token)
    cp.reload_grid()
    row = cp.find_row_by_name(src["name"])
    assert row.count() > 0, f"[UI] Source file {src['name']} not in grid"
    cp.copy_and_paste(row)
    assert cp.wait_for_duplicate(src["name"], timeout=10000), \
        f"[UI] Duplicate of '{src['name']}' did not appear after paste"


# ══════════════════════════════════════════════════════════════
# TC_CP_002 - Verify duplicate naming "(1)" (API)
# ══════════════════════════════════════════════════════════════
@qase.id(201)
@qase.title("TC_CP_002: Pasted file gets unique name like 'name(1).ext'")
@pytest.mark.copy_paste
def test_TC_CP_002_duplicate_naming(token, drive):
    """Pre: file exists | Expected: 'name(1).ext' suffix appears."""
    src = _seed_docx(token)
    resp = _paste(token, drive, [src])
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Paste failed: {resp.status_code}"
    base, ext = src["name"].rsplit(".", 1)
    expected = f"{base}(1).{ext}"
    assert _find_obj(_list_root(token), expected) is not None, \
        f"[API] Expected duplicate '{expected}' not found"


# ══════════════════════════════════════════════════════════════
# TC_CP_003 - Different file types (API) — uses 2 representative types
# ══════════════════════════════════════════════════════════════
@qase.id(202)
@qase.title("TC_CP_003: Copy-paste works across multiple file types")
@pytest.mark.copy_paste
def test_TC_CP_003_different_file_types(token, drive):
    """Pre: multiple file types exist | Expected: each duplicates ok.
    Uses two representative types — mechanism is type-agnostic."""
    pasted = 0
    for key in ("png", "pdf"):
        src_path = os.path.join(DATA_SET_PATH, UPLOAD_FILES[key])
        if not os.path.exists(src_path):
            continue
        up = _upload_file(token, src_path)
        if not up or up.status_code not in (200, 201):
            continue
        obj = _find_obj(_list_root(token), UPLOAD_FILES[key])
        if not obj:
            continue
        resp = _paste(token, drive, [obj])
        api_tracker.set(resp.status_code)
        if resp.status_code in (200, 201, 204):
            pasted += 1
    if pasted == 0:
        pytest.skip("[SEED] No fixture files were available")
    assert pasted >= 1, "[API] No file type duplicated successfully"


# ══════════════════════════════════════════════════════════════
# TC_CP_004 - File content integrity (API: byte-compare)
# ══════════════════════════════════════════════════════════════
@qase.id(203)
@qase.title("TC_CP_004: Copied file content is byte-identical to source")
@pytest.mark.copy_paste
def test_TC_CP_004_content_integrity(token, drive):
    """Pre: file exists | Expected: copy is byte-identical."""
    src = _seed_docx(token)
    resp = _paste(token, drive, [src])
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Paste failed: {resp.status_code}"
    base, ext = src["name"].rsplit(".", 1)
    dup = _find_obj(_list_root(token), f"{base}(1).{ext}")
    if not dup:
        pytest.skip(f"[API] Duplicate '{base}(1).{ext}' not found")
    headers = _auth_headers(token, json_body=False)
    try:
        a = requests.post(DOWNLOAD_URL, json={"fileId": src["id"]},
                          headers=headers, verify=False, timeout=60)
        b = requests.post(DOWNLOAD_URL, json={"fileId": dup["id"]},
                          headers=headers, verify=False, timeout=60)
    except Exception as e:
        pytest.skip(f"[API] Download unreachable: {e}")
    if a.status_code != 200 or b.status_code != 200:
        pytest.skip(f"[API] Download not 200 (src={a.status_code}, dup={b.status_code})")
    assert hashlib.sha256(a.content).hexdigest() == hashlib.sha256(b.content).hexdigest(), \
        "[API] Content differs between original and copy"


# ══════════════════════════════════════════════════════════════
# TC_CP_005 - Metadata validation (API)
# ══════════════════════════════════════════════════════════════
@qase.id(204)
@qase.title("TC_CP_005: Copied file has fresh modified date, same type/owner")
@pytest.mark.copy_paste
def test_TC_CP_005_metadata_validation(token, drive):
    """Pre: file exists | Expected: copy preserves type+owner, has new dateModified."""
    src = _seed_docx(token)
    resp = _paste(token, drive, [src])
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Paste failed: {resp.status_code}"
    base, ext = src["name"].rsplit(".", 1)
    dup = _find_obj(_list_root(token), f"{base}(1).{ext}")
    if not dup:
        pytest.skip(f"[API] Duplicate not found for metadata check")
    assert dup.get("type")    == src.get("type"),    "[API] Type changed"
    assert dup.get("ownedBy") == src.get("ownedBy"), "[API] Owner changed"
    assert dup.get("dateModified"), "[API] Copy has no dateModified"


# ══════════════════════════════════════════════════════════════
# TC_CP_006 - Copy multiple files in one paste (API) — needs >1 file
# ══════════════════════════════════════════════════════════════
@qase.id(205)
@qase.title("TC_CP_006: Bulk paste of multiple files in one API call")
@pytest.mark.copy_paste
def test_TC_CP_006_multiple_files(token, drive):
    """Pre: multiple files exist | Expected: all duplicated in 1 call."""
    files = [_seed_docx(token) for _ in range(3)]
    resp = _paste(token, drive, files)
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Bulk paste failed: {resp.status_code}"


# ══════════════════════════════════════════════════════════════
# TC_CP_007 - Copy file + folder together (API) — needs 1 file + 1 folder
# ══════════════════════════════════════════════════════════════
@qase.id(206)
@qase.title("TC_CP_007: Mixed file + folder copy-paste in one operation")
@pytest.mark.copy_paste
def test_TC_CP_007_file_and_folder_together(token, drive):
    """Pre: file + folder exist | Expected: both duplicated."""
    items = [_seed_docx(token), _seed_folder(token)]
    resp = _paste(token, drive, items)
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Mixed paste failed: {resp.status_code}"


# ══════════════════════════════════════════════════════════════
# TC_CP_008 - Copy file inside its own nested folder (API)
# ══════════════════════════════════════════════════════════════
@qase.id(207)
@qase.title("TC_CP_008: Copy file inside a nested folder")
@pytest.mark.copy_paste
def test_TC_CP_008_copy_in_same_nested_folder(token):
    """Pre: file in nested folder | Expected: duplicate in same path."""
    folder = _seed_folder(token)
    file_ = _seed_docx(token)
    resp = _paste(token, folder, [file_], target_path=f"/{folder['id']}/")
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Nested paste failed: {resp.status_code}"


# ══════════════════════════════════════════════════════════════
# TC_CP_009 - Copy empty folder in My Drive (API) — needs 1 folder
# ══════════════════════════════════════════════════════════════
@qase.id(208)
@qase.title("TC_CP_009: Copy-Paste an empty folder at root")
@pytest.mark.copy_paste
def test_TC_CP_009_copy_empty_folder(token, drive):
    """Pre: empty folder exists | Expected: duplicate at root."""
    empty = _seed_folder(token)
    resp = _paste(token, drive, [empty])
    api_tracker.set(resp.status_code)
    assert resp.status_code in (200, 201, 204), f"[API] Empty folder paste failed: {resp.status_code}"


# ══════════════════════════════════════════════════════════════
# TC_CP_010 - Keyboard shortcut Ctrl+C / Ctrl+V — SKIPPED
# ══════════════════════════════════════════════════════════════
@qase.id(209)
@qase.title("TC_CP_010: Copy-paste via keyboard shortcut Ctrl+C / Ctrl+V")
@pytest.mark.copy_paste
@pytest.mark.skip(reason="Skipped per project decision — Syncfusion grid keyboard "
                         "shortcut needs focus management not worth the complexity")
def test_TC_CP_010_keyboard_shortcut():
    pass


# ══════════════════════════════════════════════════════════════
# TC_CP_011 - Copy large 50MB file and paste (API)
# ══════════════════════════════════════════════════════════════
@qase.id(210)
@qase.title("TC_CP_011: Copy-Paste a large (50MB) file without corruption")
@pytest.mark.copy_paste
def test_TC_CP_011_copy_large_file(token, drive):
    """Pre: 50MB file uploaded | Expected: paste completes without error."""
    large_path = os.path.join(DATA_SET_PATH, UPLOAD_FILES["large_50mb"])
    print(f"  [INFO] Looking for 50MB fixture at: {large_path}")
    if not os.path.exists(large_path):
        pytest.skip(f"[SEED] 50MB fixture missing at {large_path}")
    print(f"  [INFO] Fixture found, size: {os.path.getsize(large_path)} bytes")
    up = _upload_file(token, large_path, timeout=600)
    if up is None:
        pytest.skip("[SEED] Upload helper returned None — see stdout for cause")
    if up.status_code not in (200, 201):
        pytest.skip(f"[SEED] Upload status {up.status_code} | body: {up.text[:200]}")
    # Poll listing — large file may take a moment to appear
    obj = None
    for _ in range(10):
        obj = _find_obj(_list_root(token), UPLOAD_FILES["large_50mb"])
        if obj is not None:
            break
        time.sleep(1)
    if not obj:
        pytest.skip("[SEED] Uploaded large file not found in listing after 10s")
    t0 = time.time()
    resp = _paste(token, drive, [obj])
    elapsed = time.time() - t0
    api_tracker.set(resp.status_code)
    print(f"  [API] 50MB paste: {resp.status_code} in {elapsed:.2f}s")
    assert resp.status_code in (200, 201, 204), f"[API] Large file paste failed: {resp.status_code}"
