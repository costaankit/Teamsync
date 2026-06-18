"""
IMIR Advanced Search - Page Object Model

The Advanced Search panel opens from the Tune icon in the Main Drive search bar
and exposes filters: Type, Type Attribute (per-type metadata), Tags, Date Range
(Created/Modified + From/To), and Owned By (Anyone/Me/Others/Specific Person).

Clicking SEARCH fires:  POST /operationModule/api/operations  with action="read"
and a "filter" object — results render in the normal #filemanager_grid, so we
reuse the grid to read result rows (Type column, Tags chips, file name).

Composition: holds an UploadPage for login / landing-popup / toolbar handling.
The panel inputs are MUI Autocompletes with no ids, so selectors key off the
visible row label ("Type", "Tags", "Owned By", …) and button text.
"""

from playwright.sync_api import Page

from pages.upload_page import UploadPage


class AdvanceSearchPage:

    def __init__(self, page: Page):
        self.page = page
        self._up  = UploadPage(page)

        # ── Search-bar trigger (opens the Advanced Search panel) ──
        self.tune_icon = page.locator('svg[data-testid="TuneIcon"]').first

        # ── Panel anchor (heading) ─────────────────────────────
        self.panel_heading = page.get_by_role("heading", name="Advanced Search").first

        # ── Action buttons ─────────────────────────────────────
        self.search_btn = page.get_by_role("button", name="SEARCH").first
        self.reset_btn  = page.get_by_role("button", name="RESET").first

    # ── Auth + bootstrap ───────────────────────────────────────
    def login_and_open(self):
        self._up.login_and_open()

    def login_as(self, username: str, password: str):
        """Log in as a specific user (Advanced Search uses Pratibha's seeded
        drive). Mirrors UploadPage.login_and_open but with explicit creds."""
        from pages.login_page import LoginPage
        if "teamsync/home" not in self.page.url:
            lp = LoginPage(self.page)
            lp.open()
            lp.login(username, password)
            try:
                self.page.wait_for_url("**/teamsync/**", timeout=30000)
            except Exception:
                pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        self._up._popup_dismissed = False
        self._up._dismiss_popup()
        self._up.upload_toolbar_btn.wait_for(state="visible", timeout=20000)

    def reload_grid(self):
        self.page.reload()
        self.page.wait_for_load_state("load")
        self._up._popup_dismissed = False
        self._up._dismiss_popup()
        self._up.upload_toolbar_btn.wait_for(state="visible", timeout=15000)
        self.page.wait_for_timeout(800)

    # ── Panel open / close ─────────────────────────────────────
    def _find_tune_icon(self):
        for sel in (
            '[data-testid="TuneIcon"]',
            'svg[data-testid="TuneIcon"]',
            'button:has(svg[data-testid="TuneIcon"])',
        ):
            loc = self.page.locator(sel).first
            try:
                if loc.count() > 0:
                    loc.wait_for(state="attached", timeout=2000)
                    return loc
            except Exception:
                continue
        return None

    def _search_diag(self) -> str:
        try:
            return (
                f"tuneByTestId={self.page.locator('[data-testid=\"TuneIcon\"]').count()} "
                f"svgTestIds={self.page.locator('svg[data-testid]').count()} "
                f"searchInputs={self.page.locator('input[placeholder*=\"earch\"], input[type=\"search\"]').count()} "
                f"panelOpen={self.is_panel_open()} url={self.page.url}"
            )
        except Exception as e:
            return f"diag-error {e}"

    def open_panel(self) -> None:
        self._up._dismiss_popup()
        if self.is_panel_open():
            return   # already open — idempotent
        icon = self._find_tune_icon()
        if icon is None:
            raise AssertionError(f"[UI] Advanced Search (Tune) icon not found. {self._search_diag()}")
        try:
            icon.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            icon.click(timeout=4000)
        except Exception:
            icon.click(force=True)
        self.panel_heading.wait_for(state="visible", timeout=8000)
        self.page.wait_for_timeout(400)

    def is_panel_open(self) -> bool:
        try:
            return self.panel_heading.is_visible()
        except Exception:
            return False

    def close_panel_outside(self) -> None:
        """Close the panel by clicking outside it (on the grid header area)."""
        try:
            self.page.locator('#filemanager_grid .e-gridheader').first.click(
                position={"x": 5, "y": 5}, timeout=4000
            )
        except Exception:
            # Fallback: Escape (the component resets + closes on Esc)
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(400)

    # ── Field helpers ──────────────────────────────────────────
    def _row_input(self, label: str):
        """Input inside the panel Grid row whose label Typography == `label`."""
        return self.page.locator(
            f'div.MuiGrid-container:has(div.MuiGrid-item p:text-is("{label}")) input'
        ).first

    def _date_inputs(self):
        """The two date inputs in the Date Range row: [From, To]."""
        return self.page.locator('input[type="date"]')

    def _pick_option(self, text: str, exact: bool = False) -> None:
        """Click an MUI Autocomplete option from the open popper."""
        opt = self.page.get_by_role("option", name=text, exact=exact).first
        opt.wait_for(state="visible", timeout=5000)
        opt.click()
        self.page.wait_for_timeout(250)

    # ── Type ───────────────────────────────────────────────────
    def set_type(self, type_name: str) -> None:
        inp = self._row_input("Type")
        inp.click()
        inp.fill(type_name)
        self.page.wait_for_timeout(300)
        self._pick_option(type_name)

    def get_type_value(self) -> str:
        try:
            return self._row_input("Type").input_value()
        except Exception:
            return ""

    # ── Type Attribute (only present when Type != All) ─────────
    def add_attribute(self, attr_name: str, value: str = None) -> None:
        inp = self._row_input("Type Attribute")
        inp.click()
        inp.fill(attr_name)
        self.page.wait_for_timeout(300)
        self._pick_option(attr_name)
        if value is not None:
            self._row_input(attr_name).fill(value)

    def get_attribute_value(self, attr_name: str) -> str:
        try:
            return self._row_input(attr_name).input_value()
        except Exception:
            return ""

    # ── Tags (multi) ───────────────────────────────────────────
    def add_tag(self, tag_name: str) -> None:
        inp = self._row_input("Tags")
        inp.click()
        inp.fill(tag_name)
        self.page.wait_for_timeout(300)
        self._pick_option(tag_name)

    # ── Date Range ─────────────────────────────────────────────
    def set_date_range(self, range_type: str, date_from: str = None, date_to: str = None) -> None:
        """range_type: 'Created' | 'Modified'; dates: 'YYYY-MM-DD'."""
        # Date Range Type is the only NON-date input in the "Date Range" row.
        self._row_input("Date Range").click()
        self.page.wait_for_timeout(200)
        self._pick_option(range_type)
        self.page.wait_for_timeout(300)
        dates = self._date_inputs()
        if date_from is not None:
            dates.nth(0).fill(date_from)
        if date_to is not None:
            dates.nth(1).fill(date_to)

    def date_to_max(self) -> str:
        try:
            return self._date_inputs().nth(1).get_attribute("max") or ""
        except Exception:
            return ""

    def date_to_min(self) -> str:
        try:
            return self._date_inputs().nth(1).get_attribute("min") or ""
        except Exception:
            return ""

    def get_date_to_value(self) -> str:
        try:
            return self._date_inputs().nth(1).input_value()
        except Exception:
            return ""

    # ── Owned By ───────────────────────────────────────────────
    def set_owned_by(self, value: str) -> None:
        """value: 'Anyone' | 'Me' | 'Others' | 'Specific Person'."""
        inp = self._row_input("Owned By")
        inp.click()
        self.page.wait_for_timeout(200)
        self._pick_option(value)

    def set_specific_person(self, name_or_email: str) -> None:
        self.set_owned_by("Specific Person")
        f = self.page.get_by_placeholder("Enter name or email ID").first
        f.wait_for(state="visible", timeout=4000)
        f.fill(name_or_email)

    # ── Actions ────────────────────────────────────────────────
    def click_search(self) -> None:
        self.search_btn.wait_for(state="visible", timeout=5000)
        self.search_btn.click()

    def click_reset(self) -> None:
        self.reset_btn.wait_for(state="visible", timeout=5000)
        self.reset_btn.click()
        self.page.wait_for_timeout(400)

    # ── Result grid ────────────────────────────────────────────
    def file_result_rows(self):
        """Non-system FILE rows in the result grid (excludes folders + Restricted)."""
        return self.page.locator(
            '#filemanager_grid tr.e-row:not(.Restricted):has(.e-fe-icon:not(.e-fe-folder))'
        )

    def all_result_rows(self):
        return self.page.locator('#filemanager_grid tr.e-row:not(.Restricted)')

    @staticmethod
    def row_type(row) -> str:
        try:
            return row.locator('td[data-colindex="4"] .e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return ""

    @staticmethod
    def row_tags(row):
        try:
            chips = row.locator('td[data-colindex="5"] .MuiChip-label')
            return [chips.nth(i).inner_text().strip() for i in range(chips.count())]
        except Exception:
            return []

    @staticmethod
    def row_name(row) -> str:
        try:
            return row.locator('td[data-colindex="2"] .e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return ""

    @staticmethod
    def row_owner(row) -> str:
        try:
            return row.locator('td[data-colindex="3"] .e-fe-text').first.inner_text(timeout=2000).strip()
        except Exception:
            return ""

    @staticmethod
    def row_modified(row) -> str:
        try:
            return row.locator('td[data-colindex="7"] .e-fe-dateModified').first.inner_text(timeout=2000).strip()
        except Exception:
            return ""
