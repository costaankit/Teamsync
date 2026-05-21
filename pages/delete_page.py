"""
IMIR Delete Page - Page Object Model
Handles row selection, toolbar Delete button, confirmation popup
(DELETE / CANCEL) and snackbar inspection for the Delete module.

Composition over inheritance: we hold an UploadPage instance for things that
aren't delete-specific (login, dismiss landing popup, file-manager toolbar
visibility) so the Delete page object stays focused on delete actions.
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class DeletePage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # delegate login / popup / toolbar wait

        # ── Toolbar Delete button (file manager) ───────────────
        self.delete_toolbar_btn = page.locator('#filemanager_tb_delete')

        # ── Confirmation popup buttons ─────────────────────────
        # The popup has a yellow DELETE button (text + DeleteIcon SVG) and a
        # primary-blue CANCEL button (text + CloseIcon SVG). We use text+text
        # within a dialog scope so we never pick up other dialogs.
        self.delete_confirm_btn = page.locator(
            '.MuiDialog-root button:has-text("DELETE"), '
            '[role="dialog"] button:has-text("DELETE")'
        ).first
        self.delete_cancel_btn  = page.locator(
            '.MuiDialog-root button:has(svg[data-testid="CloseIcon"]), '
            '[role="dialog"] button:has(svg[data-testid="CloseIcon"])'
        ).first

        # ── Generic snackbar/toast (success or error) ──────────
        # Used for TC_09 (success message validation) and TC_10/TC_11 (errors).
        self.snackbar = page.locator(
            '[role="alert"], .MuiSnackbar-root, [class*="snackbar"], [class*="toast"]'
        ).first

    # ── Auth + page bootstrap ──────────────────────────────────
    def login_and_open(self):
        """Login (if not already) and reach the file manager view."""
        self._up.login_and_open()

    def reload_grid(self):
        """Refresh the file manager grid (e.g. after seeding via API)."""
        self.page.reload()
        self.page.wait_for_load_state("load")
        self._up._popup_dismissed = False
        self._up._dismiss_popup()
        self._up.upload_toolbar_btn.wait_for(state="visible", timeout=10000)
        self.page.wait_for_timeout(800)

    # ── Row finders ───────────────────────────────────────────
    def find_row_by_name(self, name: str):
        """First grid row whose visible text contains `name`."""
        return self.page.locator(f'tr.e-row:has-text("{name}")').first

    def find_first_file_row(self):
        """First non-system FILE row (excludes folder icons)."""
        cands = self.page.locator(
            'tr.e-row:not(.Restricted):has(.e-fe-icon:not(.e-fe-folder))'
        )
        if cands.count() == 0:
            return None
        return cands.first

    def find_first_folder_row(self):
        """First non-system FOLDER row (excludes Restricted system folders)."""
        cands = self.page.locator(
            'tr.e-row:not(.Restricted):has(.e-fe-icon.e-fe-folder)'
        )
        if cands.count() == 0:
            return None
        return cands.first

    def find_user_rows(self, count: int = 3):
        """Up to `count` non-system rows (files or folders) for bulk operations."""
        cands = self.page.locator('tr.e-row:not(.Restricted)')
        total = cands.count()
        return [cands.nth(i) for i in range(min(count, total))]

    def find_restricted_row(self, name: str):
        """Locate a RESTRICTED system row by name (Shared With Me / Trash / ...).
        Used by TC_11 to test that protected items cannot be deleted.
        """
        return self.page.locator(f'tr.e-row.Restricted:has-text("{name}")').first

    @staticmethod
    def row_filename(row) -> str:
        """Pull the visible filename out of a grid row (best-effort)."""
        try:
            return row.locator('.e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return "<unknown>"

    def scroll_until_visible(self, locator, max_scrolls: int = 40):
        """Scroll the virtualised file-manager grid until `locator` resolves to
        a visible element, then return it. Returns None if not found.

        Needed because the grid only renders ~20 rows in the DOM at a time, so a
        freshly-created item (sorted to the bottom by Last Modified) won't exist
        in the DOM until we scroll down to it.
        """
        content = self.page.locator('#filemanager_grid .e-content').first
        # Start from the top for a deterministic sweep
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
            # Scroll down by one viewport and re-check
            try:
                before = content.evaluate("el => el.scrollTop")
                content.evaluate("el => { el.scrollTop = el.scrollTop + el.clientHeight; }")
                self.page.wait_for_timeout(300)
                after = content.evaluate("el => el.scrollTop")
                if after == before:
                    break   # reached the bottom — stop sweeping
            except Exception:
                break
        return locator.first if locator.count() > 0 else None

    # ── Selection ─────────────────────────────────────────────
    def select_row(self, row) -> None:
        """Tick a single row's checkbox so the toolbar Delete activates."""
        row.locator('.e-checkbox-wrapper').first.click()
        self.page.wait_for_timeout(300)

    def select_rows(self, rows) -> int:
        """Tick multiple row checkboxes for bulk delete.

        The file-manager grid is virtualised (only ~20 rows are rendered in the
        DOM at a time), so each row is scrolled into view before clicking and
        rows that can't be made interactable are skipped rather than failing.

        Returns the number of checkboxes actually ticked.
        """
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
                # Virtualised out / not interactable — skip it
                continue
        self.page.wait_for_timeout(400)
        return ticked

    # ── Toolbar + confirmation popup ──────────────────────────
    def click_toolbar_delete(self) -> None:
        self.delete_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.delete_toolbar_btn.click()
        self.page.wait_for_timeout(300)

    def wait_for_confirm_popup(self) -> None:
        """Use the DELETE button as the popup-presence anchor (more reliable
        than a generic dialog selector — IMIR has multiple hidden dialogs)."""
        self.delete_confirm_btn.wait_for(state="visible", timeout=5000)

    def confirm_delete(self) -> None:
        self.wait_for_confirm_popup()
        self.delete_confirm_btn.click()
        self.page.wait_for_timeout(500)

    def cancel_delete(self) -> None:
        self.delete_cancel_btn.wait_for(state="visible", timeout=5000)
        self.delete_cancel_btn.click()
        self.page.wait_for_timeout(300)

    def delete_selected(self) -> None:
        """Full delete flow: toolbar Delete + DELETE in confirmation popup."""
        self.click_toolbar_delete()
        self.confirm_delete()

    # ── Snackbar / toast ──────────────────────────────────────
    def get_snackbar_text(self, timeout: int = 5000) -> str:
        """Wait for any snackbar/toast and return its text (empty if none)."""
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""
