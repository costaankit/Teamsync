"""
IMIR Create Shortcut Page - Page Object Model
Handles the 'Shared With Me' workspace navigation + Create Shortcut toolbar
button + destination-picker dialog.

Create Shortcut API: POST /api/dms_service_LM/api/shortcuts
  Body: { "fileIds": ["<source_file_id>"],
          "targetFolderId": "<destination_folder_id>" }

UI flow:
  1. Click the 'Shared With Me' workspace in the left tree
  2. Tick a file row checkbox
  3. Click toolbar Create Shortcut button (#filemanager_tb_shortcut)
  4. Destination-picker dialog opens (MUI cards for each folder)
  5. Pick destination -> click CREATE button
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class ShortcutPage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # delegate login + popup + toolbar wait

        # ── Left tree workspaces ──────────────────────────────────
        self.shared_with_me_node = page.locator(
            'li[title="Shared With Me"], li[data-id="6997edafefbab23233cfbd37"]'
        ).first

        # ── Toolbar Create Shortcut button (enabled after row select) ──
        self.shortcut_toolbar_btn = page.locator('#filemanager_tb_shortcut')

        # ── Destination-picker dialog ─────────────────────────────
        self.picker_dialog = page.locator(
            '.MuiDialog-root, [role="dialog"]'
        ).filter(has=page.locator('p:has-text("My Drive"), p:has-text("Drive")')).first
        self.picker_drive_cards = page.locator('.MuiCardContent-root p.MuiTypography-body2')
        self.picker_create_btn = page.locator(
            'button:has-text("CREATE"), button:has(svg[data-testid="DoneIcon"])'
        ).first
        self.picker_cancel_btn = page.locator(
            '.MuiDialog-root button:has-text("CANCEL"), '
            '[role="dialog"] button:has-text("CANCEL")'
        ).first

        # ── Snackbar feedback ─────────────────────────────────────
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

    # ── Workspace navigation ──────────────────────────────────
    def open_shared_with_me(self) -> bool:
        """Click the 'Shared With Me' tree node. Returns True if visible+clicked."""
        try:
            self.shared_with_me_node.wait_for(state="visible", timeout=5000)
            self.shared_with_me_node.click(timeout=5000)
            self.page.wait_for_timeout(800)
            return True
        except Exception:
            return False

    # ── Row finders ──────────────────────────────────────────
    def find_row_by_name(self, name: str):
        return self.page.locator(f'tr.e-row:has-text("{name}")').first

    def find_first_file_row(self):
        loc = self.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon:not(.e-fe-folder))')
        return self.scroll_until_visible(loc)

    def find_first_folder_row(self):
        loc = self.page.locator('tr.e-row:not(.Restricted):has(.e-fe-icon.e-fe-folder)')
        return self.scroll_until_visible(loc)

    def scroll_until_visible(self, locator, max_scrolls: int = 40):
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
        self._up._dismiss_popup()
        cb = row.locator('.e-checkbox-wrapper').first
        cb.click()
        self.page.wait_for_timeout(300)
        try:
            if not self.shortcut_toolbar_btn.is_enabled():
                cb.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    # ── Shortcut toolbar + dialog ─────────────────────────────
    def is_shortcut_button_visible(self) -> bool:
        try:
            return self.shortcut_toolbar_btn.is_visible()
        except Exception:
            return False

    def is_shortcut_button_enabled(self) -> bool:
        try:
            aria = self.shortcut_toolbar_btn.get_attribute("aria-disabled")
            return aria != "true"
        except Exception:
            return False

    def click_shortcut_toolbar(self) -> None:
        self._up._dismiss_popup()
        self.shortcut_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.shortcut_toolbar_btn.click(timeout=5000)
        self.page.wait_for_timeout(400)

    def wait_for_picker(self, timeout: int = 5000) -> bool:
        try:
            self.picker_dialog.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def pick_destination_by_name(self, name: str) -> bool:
        """Click a destination drive/folder card by its visible name."""
        try:
            card = self.picker_drive_cards.filter(has_text=name).first
            card.wait_for(state="visible", timeout=3000)
            card.click(timeout=3000)
            self.page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def click_create(self) -> None:
        self.picker_create_btn.wait_for(state="visible", timeout=5000)
        self.picker_create_btn.click(timeout=5000)
        self.page.wait_for_timeout(500)

    def click_cancel(self) -> None:
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

    # ── Snackbar ──────────────────────────────────────────────
    def get_snackbar_text(self, timeout: int = 5000) -> str:
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""
