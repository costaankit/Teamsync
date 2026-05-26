"""
IMIR Move Page - Page Object Model
Handles row selection + Move toolbar button + destination-picker dialog.

Move API : POST /api/dms_service_LM/api/moveFile
           { "fileIds": ["<src_id>"], "targetFolderId": "<dst_id>" }

UI flow  : tick row checkbox (.e-checkbox-wrapper) -> Move toolbar button
           enables (#filemanager_tb_move) -> click opens destination picker
           (MUI cards with FolderIcon) -> pick destination -> confirm.
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class MovePage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # delegate login + popup + toolbar wait

        # ── Toolbar Move button (enabled after a row is selected) ─
        self.move_toolbar_btn = page.locator('#filemanager_tb_move')

        # ── Destination-picker dialog ─────────────────────────────
        # The picker shows MUI cards (each = one destination folder) with a
        # FolderIcon SVG and a name like "My Drive". A ChevronRightIcon means
        # the folder is navigable (has children).
        self.picker_root          = page.locator('.MuiDialog-root, [role="dialog"]').filter(
            has=page.locator('svg[data-testid="FolderIcon"]')
        ).first
        self.picker_folder_cards  = page.locator('.MuiCard-root').filter(
            has=page.locator('svg[data-testid="FolderIcon"]')
        )
        # The actual confirm button is typically a Move/OK at the bottom of the
        # picker; we resolve it dynamically since the exact label varies.
        self.picker_confirm_btn   = page.locator(
            '.MuiDialog-root button:has-text("MOVE"), '
            '.MuiDialog-root button:has-text("OK"), '
            '[role="dialog"] button:has-text("MOVE"), '
            '[role="dialog"] button:has-text("OK")'
        ).first
        self.picker_cancel_btn    = page.locator(
            '.MuiDialog-root button:has-text("CANCEL"), '
            '[role="dialog"] button:has-text("CANCEL")'
        ).first

        # ── Snackbar/toast (success/error feedback) ─────────────
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

    # ── Row finders + virtual-grid scroll ──────────────────────
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

    # ── Selection + move UI flow ───────────────────────────────
    def select_row(self, row) -> None:
        """Tick the row's checkbox so the toolbar Move button enables.
        If the click happens to TOGGLE-OFF a previously-selected row, the
        move button stays disabled — in that case we click once more to
        re-select."""
        self._up._dismiss_popup()
        cb = row.locator('.e-checkbox-wrapper').first
        cb.click()
        self.page.wait_for_timeout(300)
        try:
            if not self.move_toolbar_btn.is_enabled():
                cb.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def select_rows(self, rows) -> int:
        """Tick multiple checkboxes (virtual-grid safe). Returns count ticked."""
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

    def is_move_button_visible(self) -> bool:
        try:
            return self.move_toolbar_btn.is_visible()
        except Exception:
            return False

    def is_move_button_enabled(self) -> bool:
        try:
            return self.move_toolbar_btn.is_enabled()
        except Exception:
            return False

    def click_move_toolbar(self) -> None:
        """Click the toolbar Move button to open the destination picker."""
        self.move_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.move_toolbar_btn.click(timeout=5000)
        self.page.wait_for_timeout(400)

    def wait_for_picker(self, timeout: int = 5000) -> bool:
        """Wait until the destination-picker dialog (with folder cards) appears."""
        try:
            self.picker_root.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def pick_destination_by_name(self, name: str) -> bool:
        """Click a destination folder card by its visible name (e.g. 'My Drive')."""
        card = self.picker_folder_cards.filter(has_text=name).first
        try:
            card.wait_for(state="visible", timeout=3000)
            card.click(timeout=3000)
            self.page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def confirm_picker(self) -> None:
        try:
            self.picker_confirm_btn.wait_for(state="visible", timeout=3000)
            self.picker_confirm_btn.click(timeout=3000)
            self.page.wait_for_timeout(400)
        except Exception:
            pass

    def cancel_picker(self) -> None:
        try:
            self.picker_cancel_btn.wait_for(state="visible", timeout=3000)
            self.picker_cancel_btn.click(timeout=3000)
            self.page.wait_for_timeout(300)
        except Exception:
            try:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
            except Exception:
                pass

    # ── Snackbar inspection ───────────────────────────────────
    def get_snackbar_text(self, timeout: int = 5000) -> str:
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""
