"""
IMIR Rename Page - Page Object Model
Handles the rename flow: right-click a grid row -> 'Rename' context menu item
-> MUI dialog with a text input -> RENAME confirm button.

Rename API : POST /api/operationModule/api/operations  (action="rename")
             { action, path, name, newName, data:[{...}], showFileExtension }

Composition over inheritance: holds an UploadPage for login / popup / toolbar /
file upload, and a virtual-grid scroll helper (the grid only renders ~20 rows).
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class RenamePage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # login, popup, upload, toolbar

        # ── Context-menu rename item (right-click menu) ────────
        self.rename_menu_item = page.locator('#filemanager_cm_rename')

        # ── Rename dialog: text input + RENAME confirm button ──
        self.rename_input = page.locator(
            '.MuiDialog-root input[type="text"], [role="dialog"] input[type="text"]'
        ).first
        # RENAME button = MUI button containing the DoneIcon SVG (most specific)
        self.rename_confirm_btn = page.locator(
            '.MuiDialog-root button:has(svg[data-testid="DoneIcon"]), '
            '[role="dialog"] button:has(svg[data-testid="DoneIcon"])'
        ).first

        # ── Inline dialog error + snackbar ─────────────────────
        self.dialog_error = page.locator(
            '.MuiDialog-root .Mui-error, [role="dialog"] .Mui-error, '
            '.MuiFormHelperText-root.Mui-error'
        ).first
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

    # ── Row finders + virtual scroll ───────────────────────────
    def find_row_by_name(self, name: str):
        return self.page.locator(f'tr.e-row:has-text("{name}")').first

    @staticmethod
    def row_filename(row) -> str:
        try:
            return row.locator('.e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return "<unknown>"

    def scroll_until_visible(self, locator, max_scrolls: int = 40):
        """Scroll the virtualised grid until `locator` is visible. Returns it or None."""
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

    # ── Rename flow ────────────────────────────────────────────
    def open_context_menu(self, row) -> None:
        """Right-click a grid row to open the context menu."""
        name_cell = row.locator('.e-fe-text').first
        name_cell.click(button="right")
        self.page.wait_for_timeout(500)

    def click_rename(self) -> None:
        """Click the 'Rename' item in the context menu."""
        self.rename_menu_item.wait_for(state="visible", timeout=5000)
        self.rename_menu_item.click()
        self.page.wait_for_timeout(300)

    def set_new_name(self, new_name: str) -> None:
        """Clear the rename input and type the new name.
        For files the dialog shows the base name WITHOUT extension; IMIR
        re-appends the extension on submit (showFileExtension=true)."""
        self.rename_input.wait_for(state="visible", timeout=5000)
        self.rename_input.fill(new_name)

    def confirm_rename(self) -> None:
        self.rename_confirm_btn.wait_for(state="visible", timeout=5000)
        self.rename_confirm_btn.click()
        self.page.wait_for_timeout(400)

    def open_rename_dialog(self, row) -> None:
        """Right-click the row and open the rename dialog (no submit)."""
        self.open_context_menu(row)
        self.click_rename()

    def is_confirm_disabled(self) -> bool:
        try:
            return self.rename_confirm_btn.is_disabled()
        except Exception:
            return False

    def get_dialog_error(self) -> str:
        try:
            self.dialog_error.wait_for(state="visible", timeout=2000)
            return self.dialog_error.inner_text().strip()
        except Exception:
            return ""

    def get_snackbar_text(self, timeout: int = 5000) -> str:
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""

    def close_dialog(self) -> None:
        """Best-effort dialog close (Escape) for negative tests."""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
        except Exception:
            pass
