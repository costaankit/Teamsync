"""
IMIR Upload Page - Page Object Model
Handles navigation to file manager and file upload actions.

Full UI upload flow (from screenshots):
  Step 1 → Click Upload toolbar button → dropdown opens
  Step 2 → Click "File Upload" → OS file chooser dialog opens
  Step 3 → File is selected → "UPLOAD FILES" modal appears
  Step 4 → Click orange UPLOAD button → progress shows bottom-right
  Step 4a → If duplicate exists → "Keep Both / Replace / Skip" dialog → click Keep Both
  Step 5 → "Files Uploaded Successfully" green toast confirms completion
"""

from playwright.sync_api import Page
from config.api_config import LOGIN_PAGE_URL, VALID_USERNAME, VALID_PASSWORD
from pages.login_page import LoginPage


class UploadPage:

    def __init__(self, page: Page):
        self.page = page
        self._popup_dismissed = False   # track so we skip the wait after first dismiss

        # ── Toolbar locators ───────────────────────────────────
        self.cancel_popup_btn   = page.locator('[data-testid="CancelIcon"]').first
        self.upload_toolbar_btn = page.locator('#filemanager_tb_uploads')
        self.file_upload_item   = page.locator('[aria-label="File Upload"]')
        self.folder_upload_item = page.locator('[aria-label="Folder Upload"]')

        # ── UPLOAD FILES modal locators ────────────────────────
        self.modal_upload_btn  = page.locator('button:has([data-testid="CloudUploadIcon"])')
        self.modal_cancel_btn  = page.get_by_role("button", name="CANCEL")

        # ── Duplicate file dialog locators ─────────────────────
        self.keep_both_btn = page.get_by_role("button", name="Keep Both")
        self.replace_btn   = page.get_by_role("button", name="Replace")

        # ── Progress & result locators ─────────────────────────
        self.upload_progress = page.get_by_text("Uploading", exact=False)
        self.success_toast   = page.get_by_text("Files Uploaded Successfully")

        # ── Delete locators ────────────────────────────────────
        self.delete_toolbar_btn = page.locator('#filemanager_tb_delete')
        # Confirm DELETE button inside the MUI popup — distinct from toolbar by text + dialog scope
        self.delete_confirm_btn = page.locator(
            '.MuiDialog-root button:has-text("DELETE"), [role="dialog"] button:has-text("DELETE")'
        ).first

    def login_and_open(self):
        """Login (if not already) and dismiss popup to reach the file manager.
        Robust against flaky page loads — retries with reload if toolbar is slow.
        """
        if "teamsync/home" not in self.page.url:
            lp = LoginPage(self.page)
            lp.open()
            lp.login(VALID_USERNAME, VALID_PASSWORD)
            # Wait for navigation, but don't hard-fail if the URL pattern is
            # unexpected — the toolbar wait below is the real success check.
            # Some redirects may land on /teamsync/home/files or similar.
            try:
                self.page.wait_for_url("**/teamsync/**", timeout=30000)
            except Exception:
                pass
            # If still on login page, the Sign In click may have been intercepted
            # by a dialog. Try once more after dismissing dialogs.
            if "teamsync" not in self.page.url:
                try:
                    self.page.evaluate("""() => {
                        document.querySelectorAll('.MuiDialog-root, #Bot, .docutalk-bot-container')
                            .forEach(el => el.remove());
                    }""")
                except Exception:
                    pass
                try:
                    lp.sign_in_button.click(timeout=5000)
                    self.page.wait_for_url("**/teamsync/**", timeout=30000)
                except Exception:
                    pass

        # Let the home page settle before searching for the file manager toolbar
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        self._dismiss_popup()

        # First attempt — 20s for toolbar to mount
        try:
            self.upload_toolbar_btn.wait_for(state="visible", timeout=20000)
            return
        except Exception:
            pass

        # Retry once with a reload — handles post-logout session quirks where
        # /teamsync/home loads but the file manager component never mounts
        print("  [DEBUG] Toolbar not visible — reloading and retrying...")
        self._popup_dismissed = False
        self.page.reload()
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        self._dismiss_popup()
        self.upload_toolbar_btn.wait_for(state="visible", timeout=20000)

    def _dismiss_popup(self):
        """
        Dismiss the landing page popup + hide the DocuTalk chatbot widget.
        Welcome popup: dismissed once per session (cheap on repeat).
        Chatbot widget: hidden via CSS on every call — it can re-mount after
        page reloads or navigations and intercept pointer events on the grid.
        """
        try:
            self.page.add_style_tag(content=(
                "#Bot, .docutalk-bot-container "
                "{ display: none !important; pointer-events: none !important; }"
            ))
        except Exception:
            pass
        if self._popup_dismissed:
            return
        try:
            self.cancel_popup_btn.wait_for(state="visible", timeout=1500)
            self.cancel_popup_btn.click()
            self.page.wait_for_timeout(200)
            self._popup_dismissed = True
        except Exception:
            self._popup_dismissed = True   # popup wasn't there — still mark as done

    def _close_stuck_modal(self):
        """
        Close any open dialogs (UPLOAD FILES modal, MUI dialogs, etc).
        Tries multiple approaches to ensure all blocking elements are dismissed.
        """
        try:
            # Try UPLOAD FILES modal cancel button
            if self.modal_cancel_btn.is_visible():
                self.modal_cancel_btn.click()
                self.page.wait_for_timeout(200)
        except Exception:
            pass

        try:
            # Close MUI dialogs (Material-UI backdrop click)
            backdrop = self.page.locator(".MuiBackdrop-root").first
            if backdrop.is_visible():
                backdrop.click()
                self.page.wait_for_timeout(200)
        except Exception:
            pass

    def open_upload_menu(self):
        """Click the Upload dropdown button in the toolbar."""
        self.upload_toolbar_btn.wait_for(state="visible", timeout=5000)
        try:
            self.upload_toolbar_btn.click()
        except Exception:
            # If click fails (dialogs blocking), reload and retry
            print("  [DEBUG] Upload button click blocked, reloading page...")
            self.page.reload()
            self.page.wait_for_load_state("load")
            self._dismiss_popup()
            self.upload_toolbar_btn.wait_for(state="visible", timeout=5000)
            self.upload_toolbar_btn.click()

    def upload_file(self, filepath: str, on_duplicate: str = "keep_both"):
        """
        Full upload flow:
          1. Close any stuck modal from a previous test
          2. Open upload dropdown
          3. Click 'File Upload' → OS file chooser opens
          4. Set file in chooser → UPLOAD FILES modal appears
          5. Click orange UPLOAD button
          6. If duplicate dialog appears → click 'Keep Both' (default) or 'Replace'
        on_duplicate: "keep_both" (default) | "replace" — TC_11 uses "replace"
        """
        self._close_stuck_modal()
        self.open_upload_menu()

        with self.page.expect_file_chooser() as fc_info:
            self.file_upload_item.wait_for(state="visible", timeout=3000)
            self.file_upload_item.click()
        fc_info.value.set_files(filepath)

        try:
            self.modal_upload_btn.wait_for(state="visible", timeout=5000)
            self.modal_upload_btn.click()
        except Exception:
            return

        try:
            if on_duplicate == "replace":
                self.replace_btn.wait_for(state="visible", timeout=2000)
                self.replace_btn.click()
                print("  [UI] Duplicate detected — clicked 'Replace'")
            else:
                self.keep_both_btn.wait_for(state="visible", timeout=2000)
                self.keep_both_btn.click()
                print("  [UI] Duplicate detected — clicked 'Keep Both'")
        except Exception:
            pass

    def upload_folder(self, folder_path: str):
        """
        Folder upload flow (TC_19):
          1. Close any stuck modal
          2. Open upload dropdown
          3. Click 'Folder Upload' menu item → OS folder chooser opens
          4. Pass the DIRECTORY path (webkitdirectory input) → UPLOAD FILES modal appears
          5. Click orange UPLOAD button
        """
        import os as _os
        if not _os.path.isdir(folder_path):
            raise RuntimeError(f"Folder not found: {folder_path}")

        self._close_stuck_modal()
        self.open_upload_menu()

        with self.page.expect_file_chooser() as fc_info:
            self.folder_upload_item.wait_for(state="visible", timeout=3000)
            self.folder_upload_item.click()
        # webkitdirectory inputs accept a single directory path, not a file list
        fc_info.value.set_files(folder_path)
        print(f"  [UI] Folder upload pointed at '{_os.path.basename(folder_path)}'")

        try:
            self.modal_upload_btn.wait_for(state="visible", timeout=5000)
            self.modal_upload_btn.click()
        except Exception:
            return

        try:
            self.keep_both_btn.wait_for(state="visible", timeout=2000)
            self.keep_both_btn.click()
            print("  [UI] Duplicate detected during folder upload — clicked 'Keep Both'")
        except Exception:
            pass

    def cancel_upload_modal(self, filepath: str) -> bool:
        """
        Cancel upload flow (TC_60):
          1. Close any stuck modal
          2. Open upload dropdown → click 'File Upload' → OS file chooser
          3. Set file → UPLOAD FILES modal appears
          4. Click CANCEL button on the modal (data-testid='CancelIcon' inside MUI button)
        Returns True if cancel was clicked and modal dismissed, False otherwise.
        """
        self._close_stuck_modal()
        self.open_upload_menu()

        with self.page.expect_file_chooser() as fc_info:
            self.file_upload_item.wait_for(state="visible", timeout=3000)
            self.file_upload_item.click()
        fc_info.value.set_files(filepath)

        try:
            self.modal_upload_btn.wait_for(state="visible", timeout=5000)
        except Exception:
            return False

        # CANCEL button on the UPLOAD FILES modal
        try:
            self.modal_cancel_btn.wait_for(state="visible", timeout=3000)
            self.modal_cancel_btn.click()
            self.page.wait_for_timeout(500)
            return True
        except Exception:
            return False

    def select_file_in_manager(self, filename: str, timeout: int = 8000) -> bool:
        """Click on a file row in the file manager to select it."""
        try:
            file_row = self.page.locator(f"text={filename}").first
            file_row.wait_for(state="visible", timeout=timeout)
            file_row.click()
            self.page.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def open_selected_file(self, filename: str, timeout: int = 8000) -> bool:
        """Double-click a file row to open it (triggers getFileOpenURL API)."""
        try:
            file_row = self.page.locator(f"text={filename}").first
            file_row.wait_for(state="visible", timeout=timeout)
            file_row.dblclick()
            self.page.wait_for_timeout(500)
            return True
        except Exception:
            return False

    def delete_selected_file(self) -> bool:
        """
        Click toolbar Delete button → confirm DELETE in popup.
        Assumes a file row is already selected.
        """
        try:
            self.delete_toolbar_btn.wait_for(state="visible", timeout=5000)
            self.delete_toolbar_btn.click()
            self.page.wait_for_timeout(300)
            self.delete_confirm_btn.wait_for(state="visible", timeout=3000)
            self.delete_confirm_btn.click()
            self.page.wait_for_timeout(500)
            return True
        except Exception:
            return False

    def wait_for_upload_complete(self, timeout=15000) -> bool:
        """
        Wait for 'Files Uploaded Successfully' green toast.
        Default timeout reduced to 15s — small files complete in 2-5s,
        larger files in under 15s on a local network.
        Returns True if upload succeeded, False if toast never appeared.
        """
        try:
            self.success_toast.wait_for(state="visible", timeout=timeout)
            print("  [UI] 'Files Uploaded Successfully' toast visible ✓")
            return True
        except Exception:
            print("  [UI] Success toast not visible — upload may have failed or been blocked")
            return False

    def is_upload_button_visible(self) -> bool:
        return self.upload_toolbar_btn.is_visible()

    def wait_for_file_in_manager(self, filename: str, timeout=10000) -> bool:
        """Wait until uploaded file name appears in the file manager list."""
        try:
            self.page.locator(f"text={filename}").first.wait_for(
                state="visible", timeout=timeout
            )
            return True
        except Exception:
            return False

    def get_error_toast(self) -> str:
        """Return error toast text if visible, else empty string."""
        try:
            toast = self.page.locator(
                ".e-toast-danger, .e-toast-error, [class*='error-toast'], [role='alert']"
            ).first
            toast.wait_for(state="visible", timeout=3000)
            return toast.inner_text()
        except Exception:
            return ""
