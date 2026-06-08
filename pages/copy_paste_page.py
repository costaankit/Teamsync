"""
IMIR Copy-Paste Page - Page Object Model
Handles row selection + Copy toolbar button + Paste toolbar button.

API behaviour: Copy click fires NO request. Paste click fires
  POST /api/operationModule/api/operations with action="copy".

UI flow  : tick row checkbox (.e-checkbox-wrapper) -> Copy toolbar button
           (#filemanager_tb_copy) -> Paste enables (#filemanager_tb_paste)
           -> click Paste -> duplicate appears in same folder with "(1)" suffix.
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class CopyPastePage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # delegate login + popup + toolbar wait

        # ── Toolbar Copy + Paste buttons ──────────────────────────
        self.copy_toolbar_btn  = page.locator('#filemanager_tb_copy')
        self.paste_toolbar_btn = page.locator('#filemanager_tb_paste')

        # ── Snackbar / toast (success or error feedback) ──────────
        self.snackbar = page.locator(
            '[role="alert"], .MuiSnackbar-root, [class*="snackbar"], [class*="toast"]'
        ).first

    # ── Auth + page bootstrap ──────────────────────────────────
    def login_and_open(self):
        self._up.login_and_open()

    def reload_grid(self):
        self.page.reload()
        self.page.wait_for_load_state("load")
        self._up._popup_dismissed = False
        self._up._dismiss_popup()
        self._up.upload_toolbar_btn.wait_for(state="visible", timeout=10000)
        self.page.wait_for_timeout(800)

    # ── Row finders ──────────────────────────────────────────
    def find_row_by_name(self, name: str):
        return self.page.locator(f'tr.e-row:has-text("{name}")').first

    def find_first_file_row(self):
        loc = self.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon:not(.e-fe-folder))')
        return self.scroll_until_visible(loc)

    def find_first_folder_row(self):
        loc = self.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon.e-fe-folder)')
        return self.scroll_until_visible(loc)

    def find_user_rows(self, count: int = 3):
        cands = self.page.locator('tr.e-row:not(.Restricted)')
        total = cands.count()
        return [cands.nth(i) for i in range(min(count, total))]

    @staticmethod
    def row_filename(row) -> str:
        try:
            return row.locator('.e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return "<unknown>"

    def scroll_until_visible(self, locator, max_scrolls: int = 40):
        """Sweep the virtualised grid until `locator` is visible. Returns it or None."""
        content = self.page.locator('#filemanager_grid .e-content').first
        try:
            content.evaluate("el => { el.scrollTop = 0; }")
            self.page.wait_for_timeout(300)
        except Exception:
            pass
        for _ in range(max_scrolls):
            if locator.count() > 0:
                try:
                    el = locator.first
                    el.scroll_into_view_if_needed(timeout=2000)
                    if el.is_visible():
                        return el
                except Exception:
                    pass
            try:
                before = content.evaluate("el => el.scrollTop")
                content.evaluate("el => { el.scrollTop = el.scrollTop + el.clientHeight; }")
                self.page.wait_for_timeout(300)
                after = content.evaluate("el => el.scrollTop")
                if after == before:
                    break
            except Exception:
                break
        return locator.first if locator.count() > 0 else None

    # ── Selection ──────────────────────────────────────────────
    def select_row(self, row) -> None:
        """Tick a single row's checkbox so the toolbar Copy button enables."""
        self._up._dismiss_popup()
        cb = row.locator('.e-checkbox-wrapper').first
        cb.click()
        self.page.wait_for_timeout(300)
        try:
            if not self.copy_toolbar_btn.is_enabled():
                cb.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def select_rows(self, rows) -> int:
        """Tick multiple row checkboxes (virtual-grid safe). Returns count ticked."""
        self._up._dismiss_popup()
        ticked = 0
        for r in rows:
            try:
                r.scroll_into_view_if_needed(timeout=3000)
                cb = r.locator('.e-checkbox-wrapper').first
                cb.wait_for(state="visible", timeout=3000)
                cb.click()
                ticked += 1
                self.page.wait_for_timeout(120)
            except Exception:
                continue
        self.page.wait_for_timeout(400)
        return ticked

    # ── Copy / Paste toolbar ──────────────────────────────────
    def is_copy_button_enabled(self) -> bool:
        try:
            return self.copy_toolbar_btn.is_enabled()
        except Exception:
            return False

    def is_paste_button_enabled(self) -> bool:
        """Paste starts disabled (e-overlay class + aria-disabled=true).
        After a Copy click it should become enabled."""
        try:
            aria = self.paste_toolbar_btn.get_attribute("aria-disabled")
            return aria != "true"
        except Exception:
            return False

    def click_copy(self) -> None:
        """Click the toolbar Copy button. NO API call fires on this click —
        the app stages the selection in its client-side clipboard."""
        self._up._dismiss_popup()
        self.copy_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.copy_toolbar_btn.click(timeout=5000)
        self.page.wait_for_timeout(400)

    def click_paste(self) -> None:
        """Click the toolbar Paste button. Fires the operations API with
        action=copy. Caller should monitor the response if API status is needed."""
        self._up._dismiss_popup()
        self.paste_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.paste_toolbar_btn.click(timeout=5000)
        self.page.wait_for_timeout(500)

    def copy_and_paste(self, row) -> None:
        """Convenience: select → copy → paste (waits between steps)."""
        self.select_row(row)
        self.click_copy()
        self.click_paste()

    # ── Result verification ───────────────────────────────────
    def wait_for_duplicate(self, original_name: str, timeout: int = 10000) -> bool:
        """Wait for a duplicate row matching the "(1)" naming pattern.
        e.g. original 'water_detailed.docx' -> duplicate 'water_detailed(1).docx'.
        Returns True if found within timeout."""
        if "." in original_name:
            base, ext = original_name.rsplit(".", 1)
            dup_pattern = f"{base}(1).{ext}"
        else:
            dup_pattern = f"{original_name}(1)"
        loc = self.page.locator(f'tr.e-row:has-text("{dup_pattern}")').first
        try:
            loc.wait_for(state="attached", timeout=timeout)
            return True
        except Exception:
            return False

    def count_rows_with_name_prefix(self, prefix: str) -> int:
        """Count grid rows whose visible filename contains `prefix`.
        Useful for verifying N copies exist."""
        return self.page.locator(f'tr.e-row:has-text("{prefix}")').count()

    # ── Snackbar ──────────────────────────────────────────────
    def get_snackbar_text(self, timeout: int = 5000) -> str:
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""
