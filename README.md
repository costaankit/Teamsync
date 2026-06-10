# TEAMSYNC Automation Framework

End-to-end test automation for **IMIR** (Intelligent Maintenance Information Repository) — a document management system. Combined **UI + API** testing using a single page-object model per module.

**Test Environment:** `http://frontdms-teamsync.apps.lab.ocp.lan/teamsync/home`

---

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.10+ |
| Browser automation | Playwright (`pytest-playwright`) |
| Test runner | pytest |
| API client | `requests` |
| Excel reporting | `openpyxl` (writes Pass/Fail back to `Teamsync_new_testcases.xlsx`) |
| HTML reports | `pytest-html` |
| Test case management | Qase (optional, via `qase-pytest`) |
| CI | Jenkins (`Jenkinsfile` in repo root) |

---

## Project structure

```
TEAMSYNC/
├── Jenkinsfile                    Jenkins pipeline (OpenShift deploy verify + tests)
├── conftest.py                    pytest fixtures, browser config, Excel reporter hooks
├── pytest.ini                     pytest config
├── cmdfile.txt                    Common pytest command-line invocations
├── requirements.txt               Python deps
│
├── config/
│   └── api_config.py              Endpoints, credentials, test users, folder IDs
│
├── pages/                         Page Object Model — one file per module
│   ├── login_page.py
│   ├── upload_page.py             (also provides login + popup-dismiss to other modules)
│   ├── creation_page.py
│   ├── delete_page.py
│   ├── rename_page.py
│   ├── move_page.py
│   ├── copy_paste_page.py
│   ├── share_page.py
│   └── shortcut_page.py
│
├── tests/                         Tests grouped by module
│   ├── login/
│   ├── upload/
│   ├── creation/
│   ├── delete/
│   ├── rename/
│   ├── move/
│   ├── copy_paste/
│   ├── share/
│   └── shortcut/
│
├── utils/
│   └── excel_reporter.py          Writes test outcomes back into the workbook
│
├── Data Set/
│   ├── Teamsync_new_testcases.xlsx     Source of truth — one sheet per module
│   └── Document_with_all_extension/    Fixture files (PDF, DOCX, MP4, ZIP, ...) — gitignored
│
└── reports/                       Auto-generated HTML reports
```

---

## Test coverage (9 modules, ~247 test cases)

| Module | Sheet | Tests | Notes |
|---|---|---|---|
| Login | Login | 19 | Valid/invalid credentials, masking, redirect |
| Upload | Upload Test Cases | 67 | 30+ file types, size limits, drag-drop, retry |
| Creation | Creation Test Cases | 23 | Folder + DOCX creation, validation |
| Delete | Delete | 11 | File/folder/bulk delete + confirmation |
| Rename | Rename | 14 | Files + folders, validation, special chars |
| Move | Move | 13 | Single/bulk move, destination picker, snackbar |
| Copy-Paste | Copy-paste | 11 | Same-folder, different types, large files |
| Share | Share | 70 | 22 core + 36 parametrized file types + 12 advanced |
| Create Shortcut | Create Shortcut | 19 | Shared With Me → My Drive, open via shortcut |

The Excel workbook is the **single source of truth** — each module sheet contains the test case ID, description, expected result, and the columns that the framework populates with each run (Script Status, Script Error, Time stamp).

---

## Architecture

### Page Object Model

Each module has a dedicated page object (`pages/<module>_page.py`) that encapsulates locators and high-level UI flows for that module. Non-login page objects compose with `UploadPage` for shared behaviour (login, popup dismissal, file manager toolbar wait).

### Test design

Most tests are **combined UI + API**:
1. API call → assert status code
2. UI action → verify visible result (snackbar, grid row, etc.)

API tests live in the same module as their UI siblings — co-located, not split.

### Seeding strategy

Each test seeds its own minimal data (a docx, a folder) via API and uses that. Tests are **independent** — any test can run in isolation. Avoids drive-pollution dependencies.

### Robustness

- Welcome popup dismissal + DocuTalk chatbot widget hidden via CSS injection
- Login flow retries if Sign In click is intercepted
- Virtualised grid scrolled to find rows that aren't in the rendered DOM
- Excel reporter handles open-workbook conflicts gracefully

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Playwright browser
playwright install chromium

# 3. Make sure fixture files exist
# Place test files in: Data Set/Document_with_all_extension/
# Names must match UPLOAD_FILES in config/api_config.py
```

### Credentials

Edit `config/api_config.py`:
```python
VALID_USERNAME = "ankit@gmail.com"
VALID_PASSWORD = "test"
```

Or override via environment variables in CI.

---

## Running tests

### Full suite
```bash
pytest tests/login/ tests/upload/ tests/share tests/creation/ tests/rename/ tests/move/ tests/copy_paste tests/delete/ tests/shortcut/ -v
```

### A single module
```bash
pytest tests/share/ -v
```

### A single test
```bash
pytest tests/copy_paste/test_copy_paste.py::test_TC_CP_001_copy_paste_same_folder -v
```

### Watching the browser (headed mode)
```bash
pytest tests/login/ -v --headed
```

### With short failure summary
```bash
pytest tests/ -v --tb=line
```

### Filter by marker
```bash
pytest tests/ -m share -v          # only share tests
pytest tests/ -m "share or move"   # multiple modules
```

### Push results to Qase
```bash
pytest tests/ --qase-mode=testops --qase-testops-api-token=YOUR_TOKEN --qase-testops-project=TA
```

---

## Reporting

Every run produces three artifacts:

1. **HTML report** at `reports/IMIR_Full_Report_<timestamp>.html` (self-contained, shareable)
2. **Excel update** — Pass/Fail/Skipped + error + timestamp written back to `Teamsync_new_testcases.xlsx`
3. **Qase test run** (if `--qase-mode=testops` is passed)

The Excel reporter maps test IDs by prefix:
| Prefix | Sheet |
|---|---|
| `TC_Login_` | Login |
| `TC_UpLoad_` | Upload Test Cases |
| `TC_Creation_` | Creation Test Cases |
| `TC_Delete_` | Delete |
| `TC_Rename_` | Rename |
| `TC_Move_` | Move |
| `TC_CP_` | Copy-paste |
| `TC_Share_` | Share |
| `TC_Shortcut_` | Create Shortcut |

---

## CI — Jenkins

The repository includes a `Jenkinsfile` that:
1. Verifies the `frontdms` + `gateway-deployment` deploys are rolled out on OpenShift (`oc rollout status`)
2. Checks Python + Playwright versions
3. Runs the full test suite
4. Publishes the HTML report via Jenkins `publishHTML`

The Jenkins agent runs on Linux (RHEL/OpenShift) with Python 3.9, so type hints use `Optional[X]` instead of `X | None` for compatibility.

---

## Known issues (server-side, NOT framework bugs)

The framework catches several real backend issues. These appear as test failures but are not caused by the tests:

| Test | Server returns | Should return |
|---|---|---|
| `TC_Login_06/09/18` | 500 for invalid creds | 401 / 400 |
| `TC_UpLoad_07/16/20` | `OutOfMemoryError` on 480 MB upload | 200 (JVM heap too small) |
| `TC_MOVE_03/12` | 400 on bulk move | 200 (payload format mismatch) |
| `TC_Share_13/14` | 200 for empty/invalid username | 400 (no input validation) |
| `TC_Shortcut_16` | 200 for non-existent fileId | 4xx (no input validation) |

Send these to the backend team — the framework is doing its job by surfacing them.

---

## File fixtures

For Upload, Share, and Copy-Paste file-type tests, fixture files live in:
```
Data Set/Document_with_all_extension/
```

This folder is **gitignored** (would push ~1.3 GB of binary files otherwise). To bootstrap, populate the folder locally — the test entries are defined in `UPLOAD_FILES` inside `config/api_config.py`.

The 50 MB fixture (`large_50mb.bin`) is generated as a sparse file — see `Data Set/Document_with_all_extension/large_50mb.bin`.

Missing fixtures cause the relevant tests to **skip** with a clear `[SEED] Fixture missing` message.

---

## Skipped tests — by intent

Some tests are deliberately skipped because they cannot be automated from a single-user, single-browser context:

| Category | Examples | Reason |
|---|---|---|
| Recipient-side share tests | `TC_Share_60–67` | Needs a 2nd browser logged in as recipient |
| Notification tests | `TC_Share_59/69` | No notification API exposed |
| Network failure | `TC_Share_18`, `TC_Shortcut_11` | Can't simulate deterministically |
| Owner-revoke flows | `TC_Shortcut_17/19` | Needs 2nd user + explicit unshare API |
| Editor internals | Most `TC_Creation_10–23` | Need editor selectors that aren't yet known |

---

## License / authorship

Internal project — Costa Cloud / Appolo Systems. Maintained by Ankit Tiwari.
