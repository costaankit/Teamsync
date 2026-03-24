"""
IMIR Login Page - Page Object Model
App: Intelligent Maintenance Information Repository (IMIR)
URL: http://frontdms-teamsync.apps.lab.ocp.lan/
"""

from playwright.sync_api import Page, expect


class LoginPage:

    def __init__(self, page: Page):
        self.page     = page
        self.url      = "http://frontdms-teamsync.apps.lab.ocp.lan/"

        # ── Exact locators from IMIR HTML inspection ──────────
        self.username_field = page.locator("input[name='username']")
        self.password_field = page.locator("input[name='password']")
        self.sign_in_button = page.locator("button[type='submit']")

    def open(self):
        """Open the IMIR login page and wait for it to fully load"""
        self.page.goto(self.url)
        self.page.wait_for_load_state("networkidle")
        # Wait for username field to be ready
        self.username_field.wait_for(state="visible", timeout=15000)

    def login(self, username: str, password: str):
        """Fill credentials and click SIGN IN"""
        self.username_field.click()
        self.username_field.fill(username)
        self.password_field.click()
        self.password_field.fill(password)
        self.sign_in_button.click()

    def get_page_title(self):
        return self.page.title()

    def is_sign_in_button_visible(self):
        return self.sign_in_button.is_visible()
