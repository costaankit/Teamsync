"""
IMIR Tag (Theme) - Page Object Model

A "tag" is a theme. Flows captured from the live app:

  Create tag : toolbar #filemanager_tb_theme -> name input (maxlength 20) -> Save
               -> POST /dms_service_LM/api/themes  {themeName, color}
  Assign tag : right-click a row -> context menu #filemanager_cm_edittag ("Add Tag")
               -> Autocomplete dropdown -> pick tag -> SAVE
               -> POST /dms_service_LM/api/change-file-themes  {fileId, themeIds[]}
  Tags show in the grid as MUI chips (with colour) in the Tags column (colindex 5);
  each chip has a delete (X) icon to remove the tag from the file.

Composition: holds a DeletePage (grid/row/checkbox/scroll/login helpers) and its
UploadPage (landing-popup / toolbar). MUI controls have no ids, so selectors key
off labels / button text / Syncfusion element ids.
"""

from playwright.sync_api import Page

from pages.delete_page import DeletePage


class TagPage:

    def __init__(self, page: Page):
        self.page = page
        self._dp  = DeletePage(page)
        self._up  = self._dp._up

        # ── Create-tag toolbar button ──────────────────────────
        self.create_tag_btn = page.locator('#filemanager_tb_theme')

        # ── Context-menu "Add Tag" item ────────────────────────
        self.add_tag_menu_item = page.locator('#filemanager_cm_edittag')

        # ── Assign dialog: tag Autocomplete + SAVE ─────────────
        self.tag_autocomplete = page.locator('#checkboxes-tags-demo')
        self.assign_save_btn = page.locator(
            '.MuiDialog-root button:has-text("SAVE"), [role="dialog"] button:has-text("SAVE")'
        ).first

    # ── Auth + bootstrap (delegated) ───────────────────────────
    def login_and_open(self):
        self._dp.login_and_open()

    def reload_grid(self):
        self._dp.reload_grid()

    # ── Delegated grid/row helpers ─────────────────────────────
    def find_first_file_row(self):
        return self._dp.find_first_file_row()

    def find_first_folder_row(self):
        return self._dp.find_first_folder_row()

    def find_row_by_name(self, name: str):
        return self._dp.find_row_by_name(name)

    def scroll_until_visible(self, locator, max_scrolls: int = 40):
        return self._dp.scroll_until_visible(locator, max_scrolls)

    @staticmethod
    def row_name(row) -> str:
        return DeletePage.row_filename(row)

    # ── Create tag ─────────────────────────────────────────────
    def open_create_tag(self) -> None:
        self._up._dismiss_popup()
        self.create_tag_btn.wait_for(state="visible", timeout=8000)
        self.create_tag_btn.click()
        self.page.wait_for_timeout(400)

    def is_create_tag_input_visible(self) -> bool:
        try:
            return self._tag_name_input().is_visible()
        except Exception:
            return False

    def _tag_name_input(self):
        """The tag-name field (a maxlength=20 MUI input shown after Create Tags)."""
        return self.page.locator('input.MuiInputBase-input[maxlength="20"]').first

    def type_tag_name(self, name: str) -> None:
        inp = self._tag_name_input()
        inp.wait_for(state="visible", timeout=5000)
        inp.click()
        inp.fill(name)

    def get_tag_input_value(self) -> str:
        try:
            return self._tag_name_input().input_value()
        except Exception:
            return ""

    def save_new_tag(self) -> None:
        """Submit the create-tag form. Tries a few save affordances since the
        create popover has no stable id."""
        for sel in (
            'button:has-text("SAVE")',
            'button:has-text("ADD")',
            'button:has(svg[data-testid="DoneIcon"])',
            'button[type="submit"]',
        ):
            btn = self.page.locator(sel).first
            try:
                if btn.is_visible():
                    btn.click(timeout=3000)
                    self.page.wait_for_timeout(300)
                    return
            except Exception:
                continue
        # Fallback: press Enter in the name field
        try:
            self._tag_name_input().press("Enter")
        except Exception:
            pass

    # ── Assign tag ─────────────────────────────────────────────
    def open_add_tag_dialog(self, row) -> None:
        """Right-click a row and pick 'Add Tag' from the context menu."""
        self._up._dismiss_popup()
        row.scroll_into_view_if_needed(timeout=3000)
        row.click(button="right")
        self.page.wait_for_timeout(400)
        self.add_tag_menu_item.wait_for(state="visible", timeout=5000)
        self.add_tag_menu_item.click()
        self.page.wait_for_timeout(500)

    def is_add_tag_menu_visible(self, row) -> bool:
        try:
            self._up._dismiss_popup()
            row.scroll_into_view_if_needed(timeout=3000)
            row.click(button="right")
            self.page.wait_for_timeout(400)
            visible = self.add_tag_menu_item.is_visible()
            # close the menu
            self.page.keyboard.press("Escape")
            return visible
        except Exception:
            return False

    def select_tag_in_dialog(self, tag_name: str) -> None:
        """Open the Autocomplete dropdown and choose a tag option by name."""
        self.tag_autocomplete.wait_for(state="visible", timeout=5000)
        # open the dropdown
        try:
            self.page.locator('.MuiAutocomplete-popupIndicator').first.click(timeout=3000)
        except Exception:
            self.tag_autocomplete.click()
        self.page.wait_for_timeout(300)
        opt = self.page.get_by_role("option", name=tag_name, exact=False).first
        opt.wait_for(state="visible", timeout=5000)
        opt.click()
        self.page.wait_for_timeout(300)

    def save_assign(self) -> None:
        self.assign_save_btn.wait_for(state="visible", timeout=5000)
        self.assign_save_btn.click()
        self.page.wait_for_timeout(300)

    # ── Tag chips in the grid (Tags column = colindex 5) ───────
    @staticmethod
    def row_tag_chips(row):
        try:
            chips = row.locator('td[data-colindex="5"] .MuiChip-label')
            return [chips.nth(i).inner_text().strip() for i in range(chips.count())]
        except Exception:
            return []

    @staticmethod
    def row_tag_color(row) -> str:
        """Background colour style of the first tag chip on the row (TC_20)."""
        try:
            chip = row.locator('td[data-colindex="5"] .MuiChip-root').first
            return chip.get_attribute("style") or ""
        except Exception:
            return ""

    def remove_first_chip(self, row) -> None:
        """Click the delete (X) icon on the row's first tag chip. The X is hidden
        until the chip is hovered, so hover first (then force-click as fallback)."""
        chip = row.locator('td[data-colindex="5"] .MuiChip-root').first
        chip.scroll_into_view_if_needed(timeout=3000)
        try:
            chip.hover(timeout=2000)
            self.page.wait_for_timeout(200)
        except Exception:
            pass
        chip_x = row.locator('td[data-colindex="5"] .MuiChip-deleteIcon').first
        try:
            chip_x.click(timeout=3000)
        except Exception:
            chip_x.click(force=True)
        self.page.wait_for_timeout(300)

    # ── Snackbar / toast ───────────────────────────────────────
    def get_snackbar_text(self, timeout: int = 5000) -> str:
        """Read any toast/snackbar text (broad — covers MUI Snackbar/Alert and
        common toast libs). Returns '' if none appears."""
        sels = (
            '[role="alert"], .MuiSnackbar-root, .MuiAlert-root, .MuiAlert-message, '
            '[class*="snackbar"], [class*="toast"], .Toastify__toast, .e-toast'
        )
        try:
            loc = self.page.locator(sels).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc.inner_text().strip()
        except Exception:
            return ""
