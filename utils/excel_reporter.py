"""
Excel Reporter — writes pytest results back into Teamsync_new_testcases.xlsx

Updates these columns of each test row:
  • Script Status (K) — "Pass" / "Fail" / "Skipped"
        Color-coded: light green / BRIGHT RED / light yellow
  • Script error  (L) — Error message for failed tests, skip reason for skipped.
                        Includes HTTP status code if an API call failed
                        (e.g. "HTTP 415 Unsupported Media Type | AssertionError: ...")
  • Time stamp    (M) — When the test ran + how long it took
                        Format: "2026-05-12 14:23:45 (2.34s)"

Also updates the Automation summary table at the bottom of each sheet:
  • Total Test Cases / Executed / Passed / Failed / Blocked / Not Executed

Header rows differ per sheet — the reporter auto-detects by searching for
"Test Case ID" in column B.
"""

import re
import shutil
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment


# ── Excel file location ───────────────────────────────────────
EXCEL_PATH = Path(__file__).parent.parent / "Data Set" / "Teamsync_new_testcases.xlsx"

# ── TC ID prefix → Excel sheet name ───────────────────────────
SHEET_MAP = {
    "TC_Login":    "Login",
    "TC_UpLoad":   "Upload Test Cases",
    "TC_Creation": "Creation Test Cases",
    "TC_Delete":   "Delete",
    "TC_Rename":   "Rename",
    "TC_Move":     "Move",
    "TC_Share":    "Share",
    "TC_CP":       "Copy-paste",
    "TC_Shortcut": "Create Shortcut",
}

# ── Excel column indices (1-based for openpyxl) ───────────────
# In the new format: B=TC ID, K=Script Status, L=Script error, M=Time stamp
COL_TC_ID         = 2    # B
COL_SCRIPT_STATUS = 11   # K
COL_SCRIPT_ERROR  = 12   # L
COL_TIMESTAMP     = 13   # M

# ── Cell styling for each outcome ─────────────────────────────
# Bright red used for failed tests so they're easy to notice (user request)
STYLES = {
    "passed":  {"text": "Pass",    "fill": "C6EFCE", "font": "006100", "white": False},
    "failed":  {"text": "Fail",    "fill": "FF6B6B", "font": "FFFFFF", "white": True},
    "skipped": {"text": "Skipped", "fill": "FFEB9C", "font": "9C5700", "white": False},
}

# Soft-red fill for failed-test Script error cells
FAIL_ERROR_FILL = PatternFill("solid", fgColor="FFE0E0")   # soft red bg for readability
# Soft-green fill for passed-test Script error cells (shows the HTTP code in green)
PASS_ERROR_FILL = PatternFill("solid", fgColor="C6EFCE")   # same green as the status cell

# Outcome priority — higher number wins when test has multiple phases
PRIORITY = {"passed": 1, "skipped": 2, "failed": 3}

# Regex to extract Test Case ID from a pytest test function name
# Matches:  test_TC_Login_01_valid_login → TC_Login_01
#           test_TC_UpLoad_08_minimum    → TC_UpLoad_08
TC_ID_PATTERN = re.compile(
    r"(TC_(?:Login|UpLoad|Creation|Delete|Rename|Move|Share|CP|Shortcut)_\d+)",
    re.IGNORECASE,
)

# Summary table label rows
SUMMARY_LABELS = {
    "total":        "Total Test Cases",
    "executed":     "Executed Test Cases",
    "passed":       "Passed Test Cases",
    "failed":       "Failed Test Cases",
    "blocked":      "Blocked Test Cases",
    "not_executed": "Not Executed Test Cases",
}


# ─────────────────────────────────────────────────────────────
# API status tracker (module-level singleton)
# ─────────────────────────────────────────────────────────────
class _ApiStatusTracker:
    """Holds the most recent API HTTP status code recorded by `_print()`.

    Tests already call `_print(response)` after every API call. `_print()`
    calls `api_tracker.set(response.status_code)`, which the conftest hook
    reads via `consume()` after each test ends.
    """
    def __init__(self):
        self._current_code: Optional[int] = None

    def set(self, code: int) -> None:
        self._current_code = int(code)

    def consume(self) -> Optional[int]:
        code = self._current_code
        self._current_code = None
        return code


api_tracker = _ApiStatusTracker()


def format_status_code(code: Optional[int]) -> str:
    """'200 OK' / '415 Unsupported Media Type' / '' if no code."""
    if code is None:
        return ""
    try:
        return f"{code} {HTTPStatus(code).phrase}"
    except ValueError:
        return str(code)


# ─────────────────────────────────────────────────────────────
# Main reporter
# ─────────────────────────────────────────────────────────────
class ExcelReporter:
    """Collects pytest outcomes during a run and writes them to Excel at the end."""

    def __init__(self, excel_path: Path = EXCEL_PATH):
        self.excel_path = Path(excel_path)
        # { "TC_Login_01": {"outcome": .., "api_code": .., "error": .., "duration": .., "timestamp": ..}, ... }
        self.results: dict[str, dict] = {}

    # ── Called by pytest hook for every test phase ────────────
    def record(
        self,
        test_name: str,
        outcome: str,
        api_code: Optional[int] = None,
        error: Optional[str] = None,
        duration: float = 0.0,
    ) -> None:
        match = TC_ID_PATTERN.search(test_name)
        if not match:
            return
        tc_id = match.group(1)
        prev = self.results.get(tc_id)

        if prev is None or PRIORITY.get(outcome, 0) > PRIORITY.get(prev.get("outcome"), 0):
            # New result wins (higher priority) or first record
            self.results[tc_id] = {
                "outcome":   outcome,
                "api_code":  api_code,
                "error":     error,
                "duration":  duration,
                "timestamp": datetime.now(),
            }
        else:
            # Outcome unchanged — fill in missing data
            if api_code is not None and prev.get("api_code") is None:
                prev["api_code"] = api_code
            if error and not prev.get("error"):
                prev["error"] = error
            if duration and not prev.get("duration"):
                prev["duration"] = duration

    # ── Called by pytest sessionfinish hook ───────────────────
    def write_results(self) -> None:
        if not self.results:
            print("\n[Excel Reporter] No test results captured - skipping update.")
            return
        if not self.excel_path.exists():
            print(f"\n[Excel Reporter] Excel file not found: {self.excel_path}")
            return
        if self._is_locked():
            self._print_locked_warning()
            return

        self._make_backup()

        try:
            wb = openpyxl.load_workbook(self.excel_path)
        except Exception as e:
            print(f"\n[Excel Reporter] Failed to open workbook: {e}")
            return

        per_sheet_count: dict[str, int] = {}
        not_found: list[str] = []
        # Track per-sheet counts for the summary table
        per_sheet_outcomes: dict[str, dict[str, int]] = {}

        for tc_id, info in self.results.items():
            sheet_name = self._sheet_for(tc_id)
            if not sheet_name or sheet_name not in wb.sheetnames:
                not_found.append(tc_id)
                continue
            ws = wb[sheet_name]
            row = self._find_row(ws, tc_id)
            if row is None:
                not_found.append(tc_id)
                continue
            self._write_row(ws, row, info)
            per_sheet_count[sheet_name] = per_sheet_count.get(sheet_name, 0) + 1
            buckets = per_sheet_outcomes.setdefault(sheet_name, {})
            buckets[info["outcome"]] = buckets.get(info["outcome"], 0) + 1

        # Update Automation summary tables on each affected sheet
        for sheet_name, buckets in per_sheet_outcomes.items():
            self._update_summary_table(wb[sheet_name], buckets)

        try:
            wb.save(self.excel_path)
        except PermissionError:
            self._print_locked_warning()
            return
        except Exception as e:
            print(f"\n[Excel Reporter] Error saving Excel: {e}")
            return

        self._print_summary(per_sheet_count, not_found)

    # ── Internal: row / column finders ────────────────────────
    def _sheet_for(self, tc_id: str) -> Optional[str]:
        # Case-insensitive prefix match — Excel uses TC_delete_NN (lowercase d)
        # but tests may use TC_Delete_NN. Either should resolve to the same sheet.
        tc_lower = tc_id.lower()
        for prefix, sheet in SHEET_MAP.items():
            if tc_lower.startswith(prefix.lower()):
                return sheet
        return None

    def _find_row(self, ws, tc_id: str) -> Optional[int]:
        target = tc_id.strip().lower()
        for row in range(1, ws.max_row + 1):
            value = ws.cell(row=row, column=COL_TC_ID).value
            if value and str(value).strip().lower() == target:
                return row
        return None

    # ── Internal: cell writes ─────────────────────────────────
    def _write_row(self, ws, row: int, info: dict) -> None:
        outcome  = info["outcome"]
        api_code = info.get("api_code")
        error    = info.get("error")
        duration = info.get("duration") or 0.0
        timestamp = info.get("timestamp") or datetime.now()

        # ── Col K — Script Status (Pass/Fail/Skipped with color) ──
        style = STYLES.get(outcome, STYLES["skipped"])
        status_cell = ws.cell(row=row, column=COL_SCRIPT_STATUS)
        status_cell.value = style["text"]
        status_cell.fill  = PatternFill("solid", fgColor=style["fill"])
        status_cell.font  = Font(color=style["font"], bold=True)
        status_cell.alignment = Alignment(horizontal="center", vertical="center")

        # ── Col L — Script error / status code (colored by outcome) ──
        error_cell = ws.cell(row=row, column=COL_SCRIPT_ERROR)
        error_text = self._build_error_text(outcome, api_code, error)
        error_cell.value = error_text
        if outcome == "failed":
            # Soft red background on the error cell for quick scanning
            error_cell.fill = FAIL_ERROR_FILL
            error_cell.font = Font(color="9C0006", bold=False)
        elif outcome == "passed":
            # Soft green background for pass — shows the HTTP code in green so
            # the reader can scan the column for healthy responses at a glance.
            error_cell.fill = PASS_ERROR_FILL
            error_cell.font = Font(color="006100", bold=False)
        else:
            # Skipped — clear any previous formatting so re-runs don't leave stale colours
            error_cell.fill = PatternFill(fill_type=None)
            error_cell.font = Font()

        # ── Col M — Time stamp (when + duration) ──
        ts_cell = ws.cell(row=row, column=COL_TIMESTAMP)
        ts_cell.value = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({duration:.2f}s)"
        ts_cell.alignment = Alignment(horizontal="center", vertical="center")

    def _build_error_text(self, outcome: str, api_code: Optional[int], error: Optional[str]) -> str:
        """Return what to write in the Script error column.
          • passed  → "HTTP 200 OK"  (status code recorded for passing tests too)
          • failed  → "HTTP 4xx ... | <first line of traceback>"
          • skipped → skip reason / "Skipped"
        """
        if outcome == "passed":
            # For passing tests, still record the API status code that was observed
            if api_code is not None:
                return f"HTTP {format_status_code(api_code)}"
            return ""
        parts = []
        if api_code is not None:
            parts.append(f"HTTP {format_status_code(api_code)}")
        if error:
            # Trim long traces — keep the first useful line plus type
            short = error.strip().splitlines()[0][:300]
            parts.append(short)
        return " | ".join(parts) if parts else ("Skipped" if outcome == "skipped" else "Failed")

    # ── Internal: Automation summary table ────────────────────
    def _update_summary_table(self, ws, buckets: dict[str, int]) -> None:
        """Find the Automation summary section on `ws` and fill counts.

        The summary section structure varies per sheet — the column where the
        "Automation" label sits differs (col H/I/J). We find it by:
          1. Locating the row containing the word "Automation"
          2. From that row, locating the column with "Total Test Cases"
          3. Writing counts to the column immediately to the right
        """
        # Locate the Automation header
        auto_row = auto_label_col = None
        for row_idx in range(1, ws.max_row + 1):
            for cell in ws[row_idx]:
                if cell.value and str(cell.value).strip().lower() == "automation":
                    auto_row = row_idx
                    # The labels (Total/Executed/...) are in a column AFTER the "Automation" cell
                    # on the same row. Find the column where "Total Test Cases" sits.
                    for c in ws[row_idx]:
                        if (c.column > cell.column and c.value and
                            "Total Test Cases" in str(c.value)):
                            auto_label_col = c.column
                            break
                    break
            if auto_row:
                break

        if not auto_row or not auto_label_col:
            return   # no summary table on this sheet — skip

        value_col = auto_label_col + 1

        # Build mapping {row -> bucket_key} by scanning labels under the header
        passed  = buckets.get("passed",  0)
        failed  = buckets.get("failed",  0)
        skipped = buckets.get("skipped", 0)
        executed = passed + failed
        # Total test rows in this sheet (count TC_xxx_NN entries)
        total_rows = self._count_test_rows(ws)
        not_executed = max(0, total_rows - executed - skipped)

        counts = {
            "total":        total_rows,
            "executed":     executed,
            "passed":       passed,
            "failed":       failed,
            "blocked":      skipped,           # @pytest.mark.skip == blocked
            "not_executed": not_executed,
        }

        # Walk down from the Automation header row, matching label text → write count
        # Use exact match (not substring) so "Not Executed Test Cases" doesn't
        # accidentally match the "Executed Test Cases" entry first.
        for offset in range(0, 10):
            label_cell = ws.cell(row=auto_row + offset, column=auto_label_col)
            if not label_cell.value:
                continue
            label_text = str(label_cell.value).strip().lower()
            for key, label in SUMMARY_LABELS.items():
                if label.lower() == label_text:
                    ws.cell(row=auto_row + offset, column=value_col).value = counts[key]
                    ws.cell(row=auto_row + offset, column=value_col).alignment = \
                        Alignment(horizontal="center", vertical="center")
                    break

    def _count_test_rows(self, ws) -> int:
        """Count how many test case rows exist on this sheet (col B starts with TC_)."""
        count = 0
        for row_idx in range(1, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=COL_TC_ID).value
            if value and re.match(r"TC_\w+_\d+", str(value).strip()):
                count += 1
        return count

    # ── Internal: file utilities ──────────────────────────────
    def _is_locked(self) -> bool:
        lock_file = self.excel_path.parent / f"~${self.excel_path.name}"
        return lock_file.exists()

    def _make_backup(self) -> None:
        backup = self.excel_path.with_name(self.excel_path.stem + ".backup.xlsx")
        try:
            shutil.copy2(self.excel_path, backup)
        except Exception as e:
            print(f"[Excel Reporter] Backup skipped: {e}")

    # ── Internal: console output ──────────────────────────────
    def _print_locked_warning(self) -> None:
        print("\n" + "=" * 70)
        print("[Excel Reporter] WARNING: Cannot update Teamsync_new_testcases.xlsx")
        print("    The file is currently OPEN in Microsoft Excel.")
        print("    Close Excel and re-run the tests to update PASS/FAIL status.")
        print("    Results captured this run (would have been written):")
        for tc_id, info in sorted(self.results.items()):
            outcome = info["outcome"]
            tag = STYLES[outcome]["text"]
            code = format_status_code(info.get("api_code")) or "-"
            dur = f"{info.get('duration', 0.0):.2f}s"
            print(f"      {tc_id:18s} -> {tag:8s}  API: {code:30s} Time: {dur}")
        print("=" * 70)

    def _print_summary(self, per_sheet_count: dict, not_found: list) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total    = sum(per_sheet_count.values())
        passed   = sum(1 for v in self.results.values() if v["outcome"] == "passed")
        failed   = sum(1 for v in self.results.values() if v["outcome"] == "failed")
        skipped  = sum(1 for v in self.results.values() if v["outcome"] == "skipped")

        print("\n" + "=" * 70)
        print(f"[Excel Reporter] OK: Updated {total} test cases - {timestamp}")
        for sheet, count in per_sheet_count.items():
            print(f"   - {sheet:25s} : {count:3d} rows")
        print(f"   Outcomes: {passed} Pass | {failed} Fail | {skipped} Skipped (Blocked)")
        if not_found:
            print(f"   WARN: {len(not_found)} TC IDs not found in Excel: "
                  f"{', '.join(not_found[:5])}"
                  + ("..." if len(not_found) > 5 else ""))
        print(f"   File: {self.excel_path}")
        print("=" * 70)
