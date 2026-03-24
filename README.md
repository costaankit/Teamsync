<<<<<<< HEAD
# Teamsyn
This project is created to automate end to end project of teamsync v1
=======
# TEAMSYNC Automation Framework
**App:** IMIR - Intelligent Maintenance Information Repository (Indian Air Force)
**Stack:** Python + Playwright + pytest + Qase + GitHub Actions

---

## Project Structure
```
TEAMSYNC/
├── tests/
│   ├── ui/test_login_ui.py      # UI tests (Playwright)
│   └── api/test_login_api.py    # API tests (requests)
├── pages/login_page.py          # Page Object Model
├── reports/                     # Auto-generated reports
├── .github/workflows/tests.yml  # CI/CD pipeline
├── conftest.py
├── pytest.ini
├── requirements.txt
└── .env                         # Your credentials (never commit!)
```

---

## Setup
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Run Tests

### UI tests only
```bash
pytest tests/ui/ -v --headed
```

### API tests only
```bash
pytest tests/api/ -v
```

### All tests + HTML report
```bash
pytest tests/ -v
```
Report saved to: `reports/report.html`

### All tests + send to Qase dashboard
```bash
pytest tests/ --qase-mode=testops --qase-testops-api-token=YOUR_TOKEN --qase-testops-project=TEAMSYNC
```

---

## Before Running
1. Open `tests/ui/test_login_ui.py` and update:
   - `VALID_USERNAME` = your real IMIR username
   - `VALID_PASSWORD` = your real IMIR password

2. Open `.env` and paste your Qase API token

---

## Qase Test Case Mapping
| Qase ID | Test | Type |
|---------|------|------|
| TEAMSYNC-1 | Valid login | UI |
| TEAMSYNC-2 | Wrong password | UI |
| TEAMSYNC-3 | Empty username | UI |
| TEAMSYNC-4 | Empty fields | UI |
| TEAMSYNC-5 | Invalid username | UI |
| TEAMSYNC-6 | Page title check | UI |
| TEAMSYNC-7 | API valid login | API |
| TEAMSYNC-8 | API invalid login | API |
| TEAMSYNC-9 | API missing fields | API |
| TEAMSYNC-10 | API response time | API |
>>>>>>> c7934a4 (Initial TEAMSYNC automation framework)
