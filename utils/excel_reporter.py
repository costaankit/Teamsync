"""
Excel Reporter — writes pytest results back into Teamsync_testcases.xlsx

Updates the STATUS column (col J) of each test row with:
  • "Pass"    — green fill   — test passed
  • "Fail"    — red fill     — test failed
  • "Skipped" — yellow fill  — test was skipped (e.g. setup failed)

Matches test functions to Excel rows by Test Case ID (col B).
Example: test_TC_Login_01_xxx  →  row where col B = "TC_Login_01"
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill, Font


# ── Excel file location ───────────────────────────────────────
EXCEL_PATH = Path(__file__).parent.parent / "Data Set" / "Teamsync_testcases.xlsx"

# ── TC ID prefix → Excel sheet name ───────────────────────────
SHEET_MAP = {
    "TC_Login":  "Login",
    "TC_UpLoad": "Upload Test Cases",
}

# ── Excel column indices (1-based for openpyxl) ───────────────
COL_TC_ID  = 2    # B — Test Case ID
COL_STATUS = 10   # J — STATUS (Pass/Fail/Skipped)

# ── Cell styling for each outcome ─────────────────────────────
STYLES = {
    "passed":  {"text": "Pass",    "fill": "C6EFCE", "font": "006100"},  # green
    "failed":  {"text": "Fail",    "fill": "FFC7CE", "font": "9C0006"},  # red
    "skipped": {"text": "Skipped", "fill": "FFEB9C", "font": "9C5700"},  # yellow
}

# Outcome priority — higher number wins when test has multiple phases
PRIORITY = {"passed": 1, "skipped": 2, "failed": 3}

# Regex to extract Test Case ID from a pytest test function name
# Matches:  test_TC_Login_01_valid_login  →  TC_Login_01
#           test_TC_UpLoad_08_minimum     →  TC_UpLoad_08
TC_ID_PATTERN = re.compile(r"(TC_(?:Login|UpLoad)_\d+)", re.IGNORECASE)


class ExcelReporter:
    """Collects pytest outcomes during a run and writes them to Excel at the end."""

    def __init__(self, excel_path: Path = EXCEL_PATH):
        self.excel_path = Path(excel_path)
        self.results: dict[str, str] = {}   # { "TC_Login_01": "passed", ... }

    # ── Called by pytest hook for every test phase ────────────
    def record(self, test_name: str, outcome: str) -> None:
        match = TC_ID_PATTERN.search(test_name)
        if not match:
            return
        tc_id = match.group(1)
        prev = self.results.get(tc_id)
        # Keep the highest-priority outcome (failed > skipped > passed)
        if prev is None or PRIORITY.get(outcome, 0) > PRIORITY.get(prev, 0):
            self.results[tc_id] = outcome

    # ── Called by pytest sessionfinish hook ───────────────────
    def write_results(self) -> None:
        if not self.results:
            print("\n[Excel Reporter] No test results captured — skipping update.")
            return

        if not self.excel_path.exists():
            print(f"\n[Excel Reporter] Excel file not found: {self.excel_path}")
            return

        if self._is_locked():
            self._print_locked_warning()
            return

        # Backup before writing (safety net)
        self._make_backup()

        try:
            wb = openpyxl.load_workbook(self.excel_path)
        except Exception as e:
            print(f"\n[Excel Reporter] Failed to open workbook: {e}")
            return

        per_sheet_count = {}
        not_found = []

        for tc_id, outcome in self.results.items():
            sheet_name = self._sheet_for(tc_id)
            if not sheet_name or sheet_name not in wb.sheetnames:
                not_found.append(tc_id)
                continue
            ws = wb[sheet_name]
            row = self._find_row(ws, tc_id)
            if row is None:
                not_found.append(tc_id)
                continue
            self._write_cell(ws, row, outcome)
            per_sheet_count[sheet_name] = per_sheet_count.get(sheet_name, 0) + 1

        try:
            wb.save(self.excel_path)
        except PermissionError:
            self._print_locked_warning()
            return
        except Exception as e:
            print(f"\n[Excel Reporter] Error saving Excel: {e}")
            return

        self._print_summary(per_sheet_count, not_found)

    # ── Internal helpers ──────────────────────────────────────
    def _sheet_for(self, tc_id: str) -> str | None:
        for prefix, sheet in SHEET_MAP.items():
            if tc_id.startswith(prefix):
                return sheet
        return None

    def _find_row(self, ws, tc_id: str) -> int | None:
        target = tc_id.strip().lower()
        for row in range(1, ws.max_row + 1):
            value = ws.cell(row=row, column=COL_TC_ID).value
            if value and str(value).strip().lower() == target:
                return row
        return None

    def _write_cell(self, ws, row: int, outcome: str) -> None:
        style = STYLES.get(outcome, STYLES["skipped"])
        cell = ws.cell(row=row, column=COL_STATUS)
        cell.value = style["text"]
        cell.fill  = PatternFill("solid", fgColor=style["fill"])
        cell.font  = Font(color=style["font"], bold=True)

    def _is_locked(self) -> bool:
        lock_file = self.excel_path.parent / f"~${self.excel_path.name}"
        return lock_file.exists()

    def _make_backup(self) -> None:
        backup = self.excel_path.with_name(self.excel_path.stem + ".backup.xlsx")
        try:
            shutil.copy2(self.excel_path, backup)
        except Exception as e:
            print(f"[Excel Reporter] Backup skipped: {e}")

    def _print_locked_warning(self) -> None:
        print("\n" + "=" * 70)
        print("[Excel Reporter] WARNING: Cannot update Teamsync_testcases.xlsx")
        print("    The file is currently OPEN in Microsoft Excel.")
        print("    Close Excel and re-run the tests to update PASS/FAIL status.")
        print("    Results captured this run (would have been written):")
        for tc_id, outcome in sorted(self.results.items()):
            print(f"      {tc_id:18s} -> {STYLES[outcome]['text']}")
        print("=" * 70)

    def _print_summary(self, per_sheet_count: dict, not_found: list) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = sum(per_sheet_count.values())
        passed  = sum(1 for v in self.results.values() if v == "passed")
        failed  = sum(1 for v in self.results.values() if v == "failed")
        skipped = sum(1 for v in self.results.values() if v == "skipped")

        print("\n" + "=" * 70)
        print(f"[Excel Reporter] OK: Updated {total} test cases - {timestamp}")
        for sheet, count in per_sheet_count.items():
            print(f"   - {sheet:25s} : {count:3d} rows")
        print(f"   Outcomes: {passed} Pass | {failed} Fail | {skipped} Skipped")
        if not_found:
            print(f"   WARN: {len(not_found)} TC IDs not found in Excel: "
                  f"{', '.join(not_found[:5])}"
                  + ("..." if len(not_found) > 5 else ""))
        print(f"   File: {self.excel_path}")
        print("=" * 70)
