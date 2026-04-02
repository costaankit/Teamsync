from playwright.sync_api import Page, expect
class upload:

    def __init__(self, page: Page):


        # ── Exact locators from IMIR HTML inspection ──────────
        self.dtClose = page.locator("svg[data-testid='CancelIcon']")
        self.uploadIcon = page.locator("//button[@id='filemanager_tb_uploads']/span")
        self.fileUploadOption = page.locator("//div[@id='filemanager_tb_uploads-popup']/ul/li[text()='File Upload']")
        

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
