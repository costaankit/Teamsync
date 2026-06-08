"""
IMIR Login Page - Page Object Model
App: Intelligent Maintenance Information Repository (IMIR)
URL: http://frontdms-teamsync.apps.lab.ocp.lan/
"""

from typing import Optional

from playwright.sync_api import Page
from config.api_config import LOGIN_PAGE_URL


class LoginPage:

    def __init__(self, page: Page):
        self.page           = page
        self.url            = LOGIN_PAGE_URL

        # ── Locators ──────────────────────────────────────────
        self.username_field    = page.locator("input[name='username']")
        self.password_field    = page.locator("input[name='password']")
        self.sign_in_button    = page.locator("button[type='submit']")
        self.error_message     = page.locator(".error-message, [class*='error'], [class*='alert'], [role='alert']")
        self.show_hide_toggle  = page.locator("[class*='password-toggle'], [aria-label*='password'], button:near(input[name='password'])")
        self.remember_me       = page.locator("input[type='checkbox'][name*='remember'], input[id*='remember']")

    def open(self):
        self.page.goto(self.url)
        # "load" fires when DOM + resources are ready
        # "networkidle" is avoided — SPAs keep background connections alive indefinitely
        self.page.wait_for_load_state("load")
        # Hide the chatbot widget if it appears on the login page —
        # it can intercept clicks on the Sign In button.
        try:
            self.page.add_style_tag(content=(
                "#Bot, .docutalk-bot-container "
                "{ display: none !important; pointer-events: none !important; }"
            ))
        except Exception:
            pass
        self.username_field.wait_for(state="visible", timeout=15000)

    def dismiss_blocking_dialogs(self):
        """Remove any open dialogs / overlays that could intercept the Sign In click."""
        try:
            self.page.evaluate("""() => {
                document.querySelectorAll('.MuiDialog-root, #Bot, .docutalk-bot-container')
                    .forEach(el => el.remove());
            }""")
        except Exception:
            pass

    def login(self, username: str, password: str):
        self.dismiss_blocking_dialogs()
        self.username_field.click()
        self.username_field.fill(username)
        self.password_field.click()
        self.password_field.fill(password)
        # Use click with longer timeout — sometimes Sign In is briefly disabled
        # while form validation runs.
        self.sign_in_button.click(timeout=10000)

    def logout(self):
        # Step 1: click the MuiAvatar profile icon (cursor:pointer circle with user initial)
        avatar = self.page.locator("[class*='MuiAvatar-root'][style*='cursor: pointer']")
        avatar.wait_for(state="visible", timeout=10000)
        avatar.click()

        # Step 2: Log Out option appears — click it
        logout_btn = self.page.get_by_text("Log Out", exact=True)
        logout_btn.wait_for(state="visible", timeout=5000)
        logout_btn.click()
        self.page.wait_for_load_state("load")

    def get_error_message(self) -> str:
        try:
            self.error_message.wait_for(state="visible", timeout=5000)
            return self.error_message.inner_text()
        except Exception:
            return ""

    def is_sign_in_button_visible(self) -> bool:
        return self.sign_in_button.is_visible()

    def is_sign_in_button_enabled(self) -> bool:
        return self.sign_in_button.is_enabled()

    def is_password_masked(self) -> bool:
        input_type = self.password_field.get_attribute("type")
        return input_type == "password"

    def get_password_input_type(self) -> Optional[str]:
        return self.password_field.get_attribute("type")

    def get_page_title(self) -> str:
        return self.page.title()
