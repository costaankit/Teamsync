# TEAMSYNC — Automation Framework Documentation

> Hybrid UI + API test framework for the **IMIR** (Intelligent Maintenance Information Repository)
> document management application.
>
> **Generated:** 2026-04-27
> **Owner:** Ankit Tiwari
> **Test Repository:** `c:\Users\ish\Desktop\TEAMSYNC`

---

## 1. What this framework does

A single command runs all login + upload test cases against IMIR, exercising
**both** the REST API and the browser UI in the same test, then publishing a
combined HTML report and a Qase test run.

| Layer | Tool | Purpose |
|-------|------|---------|
| Browser UI | Playwright (sync) | Drives the real Chromium browser exactly like a human |
| HTTP API  | `requests` library | Sends multipart-form requests directly to IMIR endpoints |
| Test runner | pytest 8.4.2 | Discovers, parametrises and orchestrates the tests |
| Reporting | pytest-html + Qase Pytest plugin | Local HTML report + cloud test-run dashboard |
| Pattern | Page Object Model | UI selectors and actions are isolated in `pages/` |

---

## 2. Repository layout

```
TEAMSYNC/
│
├── conftest.py                 # Session-wide fixtures: browser, page, auth_token, auto-logout
├── pytest.ini                  # markers + default verbose flag
├── qase.config.json            # Qase project settings (project = "TA")
│
├── config/
│   └── api_config.py           # All URLs, endpoints, credentials, file paths in one place
│
├── pages/
│   ├── login_page.py           # POM: login form, logout dropdown
│   └── upload_page.py          # POM: upload toolbar, file/folder upload, delete, replace
│
├── tests/
│   ├── login/test_login.py     # 19 login test cases (TC_Login_01–19)
│   └── upload/test_upload.py   # 67 upload test cases (TC_UpLoad_01–67)
│
├── Data Set/
│   └── Document_with_all_extension/   # 40+ files for upload tests + Upload folder/
│       └── Upload folder/             # 2 .docx files for folder-upload test
│
├── reports/                    # Auto-created; one timestamped HTML per run
└── docs/                       # This document
```

---

## 3. The application under test

| Item | Value |
|------|-------|
| App name | IMIR — Intelligent Maintenance Information Repository |
| Base URL | `http://frontdms-teamsync.apps.lab.ocp.lan` |
| Auth flow | Username + password → Bearer token (Keycloak-issued JWT) |
| File-store backend | MinIO (`minio-service.teamsync.svc.cluster.local`) |
| Hosting | OpenShift cluster (router timeouts apply to long uploads) |

### Endpoints exercised by the framework (in `config/api_config.py`)

| Key | Method + path | Used by |
|-----|---------------|---------|
| `login` | `POST /api/tenants/public/users/login` | All login tests, session token |
| `logout` | `POST /api/tenants/logout` | `auto_logout` fixture |
| `upload` | `POST /api/dmsUploadModule/api/upload` | All upload tests |
| `file_open` | `GET /api/dms_service_LM/api/getFileOpenURL` | TC_12 (open document) |
| `download` | `POST /api/dms_service_LM/api/download` | TC_13 (download) |
| `operations` | `POST /api/operationModule/api/operations` | TC_14 (delete) |

---

## 4. Architecture & key design decisions

### 4.1 Single browser, single tab, single session
`conftest.py` defines **session-scoped** `context` and `page` fixtures so every
test in the run reuses **one** Chromium tab. This trimmed the original suite from
~30 minutes to a few minutes by eliminating per-test browser startup.

```python
@pytest.fixture(scope="session")
def context(browser, browser_context_args): ...

@pytest.fixture(scope="session")
def page(context): ...
```

### 4.2 One Bearer token for the whole run
`auth_token` is a session fixture that logs in **once** via the API and hands
out the JWT to every API-driven test. Saves an extra login round-trip per case.

### 4.3 Selective auto-logout
`auto_logout` is `autouse=True` but only triggers for tests under `tests/login/`
(detected via `request.node.fspath`). Upload tests deliberately keep the
session open so a `module_login` fixture can sign in once for all 67 cases.

### 4.4 Page Object Model
Every UI selector lives inside `pages/login_page.py` or `pages/upload_page.py`.
Tests call high-level methods (`up.upload_file(src)`, `up.delete_selected_file()`)
and never touch raw locators — selectors can change in one place without
touching the test layer.

### 4.5 One document per test (the upload-counting fix)
Originally each upload test fired **two** uploads (one via `requests`, one via
the browser). After the user flagged duplicates, `_ui_upload(up, src)` was
rewritten to:

1. Register a `page.on("response")` listener on the upload endpoint
2. Drive only the UI upload (which itself fires the API request)
3. Capture **all** responses fired during the flow (including the retry call
   that the Keep Both / Replace dialog produces)
4. Return the most-meaningful response — prefer the last 200, otherwise the
   last response so callers see the real error

This guarantees one physical document per test while still giving us API-grade
status-code assertions.

### 4.6 Strict assertions instead of permissive ranges
Earlier versions used `assert status in [200, 400, None]` which silently passed
on real failures. Now every "valid upload" test goes through `_assert_upload_ok`
which fails on anything other than 200, surfacing real backend issues
(e.g. MinIO outage) instead of hiding them.

### 4.7 Negative-observability tests (TC_22, 23, 25, 47, 48, 63, 64)
Server failures (500, 408, network drop) cannot be triggered on demand from the
test client. For these cases the framework adopts a **symptom-based** strategy:

- Perform the normal action (upload / download / delete)
- Pass when no red-error toast appears
- Fail when a red toast appears (the user-facing symptom of the failure)

Strict error-only selectors (`.e-toast-danger, .e-toast-error, [class*='error-toast']`)
are used so success toasts (`File has been deleted.`) do not produce false
positives.

### 4.8 Robust file selection
After many runs there are dozens of `test (1).docx`, `test (2).docx`… in the
manager. Helpers like `_pick_test_docx_row(up)` filter rows by **partial**
text-match for both `"test"` and `".docx"` and grab `.last`, ensuring we
always operate on a real, scrolled-into-view row instead of skipping when
exact matches go off-screen.

---

## 5. Test inventory

### 5.1 Login module (`tests/login/test_login.py`)

| Count | Status |
|-------|--------|
| 19 total | 17 active · 2 skipped |

| Skipped | Reason |
|---------|--------|
| TC_Login_04 — Remember Me | Checkbox not present in current UI |
| TC_Login_12 — Locked account | No locked account fixture in test env |

### 5.2 Upload module (`tests/upload/test_upload.py`)

| Count | Status |
|-------|--------|
| 67 total | 49 active · 18 skipped |

#### Active groups

| Range | Theme |
|-------|-------|
| TC_01–06, 08, 09, 15, 65 | Valid format / size happy paths via UI |
| TC_07, 16, 20 | 480 MB file (within 500 MB limit) — `save` and `replace` actions |
| TC_10 | Multi-upload UI capability (1 document via UI) |
| TC_11 | Replace dialog — second upload uses `action='replace'` |
| TC_12, 13, 14 | Open / download / delete a previously-uploaded file |
| TC_17, 26–30, 32, 33, 39, 62 | Blocked formats (.exe, .bat, .js, .abc, .html, no-ext) |
| TC_18, 31 | Filename / content edge cases (empty file, uppercase ext) |
| TC_22, 23, 25, 47, 48, 63, 64 | Negative-observability (no-red-alert) checks |
| TC_24 | Expired session token returns 401/403 |
| TC_37, 40 | Supported archive (zip) and image (svg) — strict 200 |
| TC_50–55 | Filename edge cases: special chars, leading/trailing space, unicode, emoji, very long |
| TC_56 | Duplicate filename returns 409/400 |
| TC_57 | Upload toolbar button is visible |
| TC_19 | Folder upload (uses dataset folder + 2 docx files) |
| TC_60 | Cancel upload from UPLOAD FILES modal |
| TC_66, 67 | (Wired to TC_14 + skipped duplicates) |

#### Currently skipped (18)

| TC | Reason |
|----|--------|
| TC_21 | Preview modal selector unknown |
| TC_34 | Requires custom MIME header crafting |
| TC_35 | Need an encrypted test file |
| TC_36 | Need a password-protected PDF |
| TC_38 | Need a nested ZIP test file |
| TC_41, 42, 45 | Unblockable until a >500 MB or borderline file is added to the dataset |
| TC_43 | Very-large-file upload — risky in CI, run manually |
| TC_46 | Cannot simulate slow network in automated test |
| TC_49 | KNOWN FAIL — IMIR has no resume-upload feature |
| TC_58 | KNOWN FAIL — drag-and-drop returns 400 (documented bug) |
| TC_59 | Progress-bar selector unknown |
| TC_61 | Retry UI not identified |
| TC_66 | Metadata API endpoint unknown |
| TC_67 | Belongs to Delete module (covered by TC_14) |

---

## 6. Helpers and conventions

### 6.1 In `conftest.py`

| Object | Type | Scope | Purpose |
|--------|------|-------|---------|
| `ApiClient` | class | per-call | `requests.post` with friendly error messages |
| `api_client` | fixture | function | injects `ApiClient` |
| `context` / `page` | fixture | session | one Chromium tab for the entire run |
| `auth_token` | fixture | session | logs in once via API, hands out the JWT |
| `auto_logout` | fixture | function (autouse) | logs out only after login-module tests |
| `pytest_configure` | hook | once | timestamps the HTML report and registers markers |

### 6.2 In `tests/upload/test_upload.py`

| Helper | Purpose |
|--------|---------|
| `_f(key)` | resolves a key in `UPLOAD_FILES` to its absolute path |
| `_unique(ext)` | UUID-suffixed filename to dodge accidental duplicates |
| `_upload_api(...)` | direct multipart POST to the upload endpoint |
| `_print(response)` | pretty-prints status, time, and a slice of the body |
| `_ui_upload(up, src, on_duplicate=...)` | UI-driven upload + multi-response capture |
| `_ui_status(resp)` | safe `.status` extraction from a Playwright Response |
| `_assert_upload_ok(resp, ctx)` | strict 200 assertion with descriptive failure |
| `_pick_test_docx_row(up)` | resilient row picker for `test*.docx` files |

### 6.3 In `pages/upload_page.py`

| Method | Used by |
|--------|---------|
| `login_and_open()` | module fixture in `tests/upload` |
| `_dismiss_popup()` | once-per-session landing-popup handler |
| `_close_stuck_modal()` | reliability shim before each upload |
| `open_upload_menu()` | clicks the toolbar Upload button + recovers on click block |
| `upload_file(filepath, on_duplicate)` | full file-upload flow with Keep Both / Replace branch |
| `upload_folder(folder_path)` | folder-upload variant for TC_19 |
| `cancel_upload_modal(filepath)` | TC_60 — cancels at the UPLOAD FILES modal |
| `select_file_in_manager(filename)` | clicks file row by visible text |
| `open_selected_file(filename)` | double-clicks a row (TC_12) |
| `delete_selected_file()` | toolbar Delete + DELETE confirmation popup |
| `wait_for_upload_complete(timeout)` | waits for "Files Uploaded Successfully" toast |
| `wait_for_file_in_manager(filename)` | post-upload visibility check |
| `get_error_toast()` | broad error-toast read (used by TC_25/47/48/63/64) |

---

## 7. Configuration

### 7.1 `config/api_config.py`

- **Base URL & endpoints** — single source of truth, no hardcoded URLs in tests
- **`DATA_SET_PATH`** — absolute path that survives Windows `\` ↔ `/` quirks
- **`UPLOAD_FOLDER_PATH`** — points at the dataset's `Upload folder`
- **`UPLOAD_FILES`** — dict mapping logical keys (`png`, `pdf`, `over_limit`,
  `test_docx`, etc.) to the actual filenames in the dataset
- **`UPLOAD_EXTRA_HEADERS`** — Type, username, AI metadata flags required by IMIR
- **`DEFAULT_HEADERS`** — `appName`, `Origin`
- **Credentials** — `VALID_USERNAME`, `VALID_PASSWORD`, plus negative-test
  identifiers (`WRONG_USERNAME`, `DISABLED_USER`, `INVALID_EMAIL` …)

### 7.2 `pytest.ini`

```ini
[pytest]
addopts = -v
testpaths = tests
markers =
    login: Combined UI + API tests for Login module
    upload: Combined UI + API tests for Upload module
    qase: Qase test case mapping
```

### 7.3 `qase.config.json`

- Mode: `testops` with `report` fallback
- Project key: `TA`
- Run title: "IMIR Login Automation Run"

---

## 8. Reporting

| Output | Generated by | Location |
|--------|--------------|----------|
| HTML report | `pytest-html` (configured in `pytest_configure`) | `reports/IMIR_Full_Report_<timestamp>.html` |
| Qase cloud run | `qase-pytest` plugin | `https://app.qase.io/run/TA/dashboard/<run_id>` |
| Console log | pytest `-v` | stdout — every test prints its API status, time, and body slice |

The HTML file is **self-contained** (assets inlined) and **timestamped**, so
historical reports never overwrite each other and can be opened on any
machine without external dependencies.

---

## 9. How to run

### Prerequisites

```bash
pip install pytest pytest-playwright pytest-html qase-pytest requests
playwright install chromium
```

### Common commands

| Goal | Command |
|------|---------|
| All tests (login + upload) | `python -m pytest tests/ -v` |
| Only login | `python -m pytest tests/login/ -v` |
| Only upload | `python -m pytest tests/upload/ -v` |
| Combined login + upload | `python -m pytest tests/login/test_login.py tests/upload/test_upload.py -v` |
| Marker-driven | `python -m pytest -m "login or upload" -v` |
| Stop on first failure | `python -m pytest tests/ -x` |
| One specific case | `python -m pytest tests/upload/test_upload.py::test_TC_UpLoad_07_file_at_max_limit -v -s` |
| A subset by keyword | `python -m pytest tests/upload/ -k "UpLoad_22 or UpLoad_23" -v` |

The full upload module takes roughly 9 minutes; the login module under 1 minute.
Times grow when 480 MB files are part of the run (TC_07, TC_16, TC_20 use a
600 s timeout each).

---

## 10. Known environment caveats

| Caveat | Impact | Workaround |
|--------|--------|------------|
| MinIO outage | Real 400 from upload endpoint | Tests fail honestly — restore MinIO |
| OpenShift router 60 s default | Large-file uploads time out | TC_07/16/20 raise client timeout to 600 s |
| Qase free-tier run limit | `403 — limit of active runs` | Close/abort old runs in dashboard |
| File chooser blocks `.exe/.bat/.js/.abc/no-ext` | UI can't drive these formats | Those TCs are API-only |
| Keep-Both creates `test (N).docx` duplicates | Exact-name selectors miss the row | Use `_pick_test_docx_row()` (broad match + `.last`) |

---

## 11. Evolution timeline (high-level)

| Phase | Key change |
|-------|------------|
| Initial | One browser per test → ran ~30 minutes |
| Single-tab refactor | Session-scoped `page` fixture → run time slashed |
| Login module | 19 cases, auto-logout fixture, multipart auth |
| Upload module — first pass | 67 cases mapped to Excel master sheet |
| Magic-byte fix | TC_08 switched to real `test.docx` from the dataset |
| 500 MB limit | TC_07/16/20 expectations corrected, 600 s timeout |
| One-document-per-test | `_ui_upload` rewrite with multi-response capture |
| Strict assertions | Removed lenient `[200, 400, None]` ranges; introduced `_assert_upload_ok` |
| Folder upload + cancel modal | TC_19 + TC_60 implemented |
| Replace flow | TC_11 (`action='replace'` + Replace button), TC_20 (replace 480 MB) |
| Negative observability | TC_22/23/25/47/48/63/64 enabled with red-alert symptom checks |
| Resilient row picker | `_pick_test_docx_row` to handle IMIR's auto-rename |

---

## 12. Maintenance checklist

When the application changes, the most likely files to update — in priority
order:

1. **`config/api_config.py`** — new endpoint, credential, or dataset file
2. **`pages/upload_page.py`** / **`pages/login_page.py`** — when DOM selectors move
3. **`tests/upload/test_upload.py`** / **`tests/login/test_login.py`** —
   when expected status codes or flows change
4. **`qase.config.json`** — when migrating Qase project / token
5. **`pytest.ini`** — when adding new test markers
