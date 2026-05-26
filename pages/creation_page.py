"""
IMIR Creation Page - Page Object Model
Handles folder creation through the file manager UI.

Folder creation flow (from screenshots + HTML):
  Step 1 → Click toolbar dropdown button (#filemanager_tb_uploads) - opens menu
  Step 2 → Click "New Folder" menu item (aria-label="New Folder")
  Step 3 → "ENTER FOLDER NAME" dialog appears with text input
  Step 4 → Type the folder name → click SUBMIT button (data-testid="DoneIcon")
  Step 5 → New folder appears in the file manager
"""

from playwright.sync_api import Page
from config.api_config import LOGIN_PAGE_URL, VALID_USERNAME, VALID_PASSWORD
from pages.login_page import LoginPage


class CreationPage:

    def __init__(self, page: Page):
        self.page = page
        self._popup_dismissed = False

        # ── Toolbar locators (same dropdown as Upload) ─────────
        self.cancel_popup_btn   = page.locator('[data-testid="CancelIcon"]').first
        self.upload_toolbar_btn = page.locator('#filemanager_tb_uploads')
        self.new_folder_item    = page.locator('[aria-label="New Folder"]')
        self.new_docx_item      = page.locator('[aria-label="Word (docx)"]')

        # ── Dialog locators (shared by New Folder + New DOCX) ──
        # MUI text input inside the dialog — same control for both flows
        self.folder_name_input  = page.locator(
            '.MuiDialog-root input[type="text"], [role="dialog"] input[type="text"]'
        ).first
        self.docx_name_input    = self.folder_name_input   # same element, alias for clarity
        self.submit_btn         = page.locator(
            'button[type="submit"]:has([data-testid="DoneIcon"])'
        ).first
        self.dialog_cancel_btn  = page.get_by_role("button", name="CANCEL")

    # ── Auth + open file manager ──────────────────────────────
    def login_and_open(self):
        """Reach the file manager view — robust against post-logout state."""
        if "teamsync/home" not in self.page.url:
            lp = LoginPage(self.page)
            lp.open()
            lp.login(VALID_USERNAME, VALID_PASSWORD)
            self.page.wait_for_url("**/teamsync/home**", timeout=30000)

        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        self._dismiss_popup()

        try:
            self.upload_toolbar_btn.wait_for(state="visible", timeout=20000)
            return
        except Exception:
            pass

        # Recovery: reload and retry
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
        """Dismiss landing popup once per session + hide DocuTalk chatbot every call."""
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
            self._popup_dismissed = True

    def _close_stuck_dialog(self):
        """Close any leftover dialogs from a previous test."""
        try:
            backdrop = self.page.locator(".MuiBackdrop-root").first
            if backdrop.is_visible():
                backdrop.click()
                self.page.wait_for_timeout(200)
        except Exception:
            pass

    # ── Folder creation flow ──────────────────────────────────
    def open_dropdown(self):
        """Click the toolbar dropdown that contains 'New Folder' / 'File Upload'."""
        self._close_stuck_dialog()
        self.upload_toolbar_btn.wait_for(state="visible", timeout=5000)
        try:
            self.upload_toolbar_btn.click()
        except Exception:
            # Recover by reloading if dialogs intercept the click
            print("  [DEBUG] Toolbar click blocked, reloading...")
            self.page.reload()
            self.page.wait_for_load_state("load")
            self._dismiss_popup()
            self.upload_toolbar_btn.wait_for(state="visible", timeout=5000)
            self.upload_toolbar_btn.click()

    def click_new_folder(self):
        """Click the 'New Folder' menu item in the dropdown."""
        self.new_folder_item.wait_for(state="visible", timeout=5000)
        self.new_folder_item.click()

    def fill_folder_name(self, name: str):
        """Type the folder name into the dialog input."""
        self.folder_name_input.wait_for(state="visible", timeout=5000)
        self.folder_name_input.fill(name)

    def submit_folder(self):
        """Click the SUBMIT button to create the folder."""
        self.submit_btn.wait_for(state="visible", timeout=5000)
        self.submit_btn.click()

    def create_folder_ui(self, name: str):
        """Full UI flow: open dropdown → click New Folder → type name → submit."""
        self.open_dropdown()
        self.click_new_folder()
        self.fill_folder_name(name)
        self.submit_btn.wait_for(state="visible", timeout=5000)
        self.submit_btn.click()

    # ── DOCX creation flow ────────────────────────────────────
    def click_new_docx(self):
        """Click the 'Word (docx)' menu item in the toolbar dropdown."""
        self.new_docx_item.wait_for(state="visible", timeout=5000)
        self.new_docx_item.click()

    def fill_docx_name(self, name: str):
        """Type the DOCX filename into the 'Enter File Name' dialog."""
        self.docx_name_input.wait_for(state="visible", timeout=5000)
        self.docx_name_input.fill(name)

    def create_docx_ui(self, name: str):
        """Full UI flow: open dropdown → click Word (docx) → type name → submit.
        Creates a new empty DOCX file and (in the app) opens it in the editor.
        """
        self.open_dropdown()
        self.click_new_docx()
        self.fill_docx_name(name)
        self.submit_btn.wait_for(state="visible", timeout=5000)
        self.submit_btn.click()

    # ── Result verification ───────────────────────────────────
    def wait_for_folder_in_manager(self, name: str, timeout: int = 15000) -> bool:
        """Return True if the folder name appears in the file manager list.
        Tries grid-row first (most reliable), falls back to broad text match.
        Scrolls the row into view so off-screen matches still count.
        """
        # Try grid row with exact text — works for newly-created folders that
        # render as <tr class="e-row"> with the name in a cell.
        row = self.page.locator(f'tr.e-row:has-text("{name}")').first
        try:
            row.wait_for(state="attached", timeout=timeout)
            try:
                row.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            return True
        except Exception:
            pass
        # Fallback: any element with that text
        try:
            self.page.locator(f"text={name}").first.wait_for(state="visible", timeout=3000)
            return True
        except Exception:
            return False

    def get_dialog_error(self) -> str:
        """Return any inline error message from the folder name dialog (empty if none)."""
        try:
            err = self.page.locator(
                '.MuiDialog-root .Mui-error, .MuiFormHelperText-root.Mui-error'
            ).first
            err.wait_for(state="visible", timeout=2000)
            return err.inner_text().strip()
        except Exception:
            return ""

    def is_submit_disabled(self) -> bool:
        """Return True if the submit button is disabled (empty name etc.)."""
        try:
            return self.submit_btn.is_disabled()
        except Exception:
            return False
