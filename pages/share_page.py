"""
IMIR Share Page - Page Object Model
Handles row selection + Share toolbar button + 'Share with users' dialog.

Share API: POST /api/dms_service_LM/api/shareWithUsers
  Headers (besides Bearer): fileId, isSharedToDepartment, roleNameDisplay
  Body  : { "accessRight": "EDITOR" | "VIEWER" | "COMMENTOR",
            "message": "...", "notify": true, "usernames": [...] }

UI flow  : tick row checkbox → Share toolbar (#filemanager_tb_share) →
           'Share with users' dialog → type recipient → click green Confirm →
           pick role → click SEND.
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class SharePage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)   # delegate login + popup + toolbar wait

        # ── Toolbar Share button (enabled after row select) ──────
        self.share_toolbar_btn = page.locator('#filemanager_tb_share')

        # ── Share dialog locators ────────────────────────────────
        self.share_dialog = page.locator(
            '.MuiDialog-root, [role="dialog"]'
        ).filter(has_text="Share with users").first
        self.recipient_input = page.locator(
            '[role="dialog"] input[aria-autocomplete="list"], '
            '.MuiDialog-root input[aria-autocomplete="list"]'
        ).first
        # Green check icon that appears after typing a valid user
        self.confirm_user_icon = page.locator(
            'svg[data-testid="CheckCircleIcon"][aria-label*="Confirm"]'
        ).first
        # Role dropdown / chips — UI may show one of several variations
        self.role_selector = page.locator(
            '[role="dialog"] [role="combobox"], '
            '[role="dialog"] [aria-haspopup="listbox"], '
            '.MuiDialog-root .MuiSelect-select'
        ).first
        # SEND button at bottom of dialog
        self.send_btn = page.locator(
            'button:has-text("SEND"), button:has(svg[data-testid="SendIcon"])'
        ).first
        # Snackbar feedback
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
        """Tick a single row so the toolbar Share button enables."""
        self._up._dismiss_popup()
        cb = row.locator('.e-checkbox-wrapper').first
        cb.click()
        self.page.wait_for_timeout(300)
        try:
            if not self.share_toolbar_btn.is_enabled():
                cb.click()
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    def select_rows(self, rows) -> int:
        """Tick multiple rows for bulk-share scenarios."""
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

    # ── Share toolbar + dialog ────────────────────────────────
    def is_share_button_visible(self) -> bool:
        try:
            return self.share_toolbar_btn.is_visible()
        except Exception:
            return False

    def is_share_button_enabled(self) -> bool:
        try:
            aria = self.share_toolbar_btn.get_attribute("aria-disabled")
            return aria != "true"
        except Exception:
            return False

    def click_share_toolbar(self) -> None:
        self._up._dismiss_popup()
        self.share_toolbar_btn.wait_for(state="visible", timeout=5000)
        self.share_toolbar_btn.click(timeout=5000)
        self.page.wait_for_timeout(400)

    def wait_for_dialog(self, timeout: int = 5000) -> bool:
        try:
            self.share_dialog.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def add_recipient(self, email_or_name: str) -> bool:
        """Type the recipient and click the green Confirm icon. Returns True if
        a confirm icon appeared and was clicked."""
        try:
            self.recipient_input.click(timeout=3000)
            self.recipient_input.fill(email_or_name)
            self.page.wait_for_timeout(800)   # let autocomplete suggestions populate
            self.confirm_user_icon.wait_for(state="visible", timeout=3000)
            self.confirm_user_icon.click(timeout=3000)
            self.page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def set_role(self, role: str) -> bool:
        """Pick a role from the dropdown. Accepts 'VIEWER'/'EDITOR'/'COMMENTOR'.
        Best-effort — different MUI variants render differently."""
        try:
            self.role_selector.click(timeout=3000)
            self.page.wait_for_timeout(300)
            opt = self.page.locator(
                f'[role="option"]:has-text("{role.capitalize()}"), '
                f'li:has-text("{role.capitalize()}")'
            ).first
            opt.click(timeout=3000)
            self.page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def click_send(self) -> None:
        self.send_btn.wait_for(state="visible", timeout=5000)
        self.send_btn.click(timeout=5000)
        self.page.wait_for_timeout(500)

    def get_snackbar_text(self, timeout: int = 5000) -> str:
        try:
            self.snackbar.wait_for(state="visible", timeout=timeout)
            return self.snackbar.inner_text().strip()
        except Exception:
            return ""
