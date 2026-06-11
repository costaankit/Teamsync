"""
IMIR Trash Page - Page Object Model
Handles navigating to the Trash workspace (left sidebar tree node), selecting
trashed items, and the Restore / Delete Forever toolbar actions plus the
"DELETE FOREVER" confirmation popup.

Composition over inheritance: a TrashPage holds a DeletePage (which itself holds
an UploadPage) so we reuse all the grid/row/checkbox/scroll helpers and the
login + landing-popup handling, and only add the Trash-specific bits here.

Trash flows captured from the live app:
  • Open Trash  → click sidebar node  → operations(action="read", path="/<trashId>/")
  • Restore     → tick row + Restore  → POST /api/dms_service_LM/api/restoreFiles  (body = ["<fileId>"])
  • Delete fore.→ tick + Delete Forever + confirm → operations(action="delete", path="/<trashId>/")
"""

from playwright.sync_api import Page

from pages.delete_page import DeletePage
from config.api_config import TRASH_FOLDER_ID


class TrashPage:

    def __init__(self, page: Page):
        self.page = page
        self._dp  = DeletePage(page)      # grid/row/checkbox/scroll + login helpers
        self._up  = self._dp._up          # landing-popup / toolbar helpers

        # ── Left sidebar Trash tree node ───────────────────────
        # The node carries title="Trash" and data-id=<trash folder id>. When it
        # is the active node it also gets id="filemanager_tree_active". Match on
        # title OR data-id (more resilient if the title ever changes/localises).
        self.trash_node = page.locator(
            f'#filemanager_tree li.e-list-item[title="Trash"], '
            f'#filemanager_tree li.e-list-item[data-id="{TRASH_FOLDER_ID}"]'
        ).first
        self._last_diag = ""   # last reveal-failure diagnostic, surfaced in errors

        # ── Toolbar buttons (only enabled inside Trash) ────────
        self.restore_btn      = page.locator('#filemanager_tb_restore')
        self.delete_forever_btn = page.locator('#filemanager_tb_deleteforever')

        # ── "DELETE FOREVER" confirmation popup button ─────────
        self.delete_forever_confirm_btn = page.locator(
            '.MuiDialog-root button:has-text("DELETE FOREVER"), '
            '[role="dialog"] button:has-text("DELETE FOREVER")'
        ).first

    # ── Auth + bootstrap (delegated) ───────────────────────────
    def login_and_open(self):
        self._dp.login_and_open()

    def reload_grid(self):
        self._dp.reload_grid()

    def relogin(self):
        """Re-authenticate the BROWSER session from scratch.

        In a full-suite run the session-scoped page is reused across every
        module for 30+ minutes, so by the time Trash navigates the Keycloak
        token can be expired (~15 min TTL — see conftest auth_token). A plain
        reload reuses the stale token, so the nav tree's lazy child-load (incl.
        the Trash node) silently fails. Clearing cookies/storage and logging in
        again hands the browser a fresh token so the tree mounts fully.
        """
        from config.api_config import LOGIN_PAGE_URL
        try:
            self.page.context.clear_cookies()
        except Exception:
            pass
        try:
            self.page.evaluate(
                "() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }"
            )
        except Exception:
            pass
        try:
            self.page.goto(LOGIN_PAGE_URL, wait_until="load", timeout=30000)
        except Exception:
            pass
        self._up._popup_dismissed = False
        self._up.login_and_open()

    # ── Delegated grid/row helpers ─────────────────────────────
    def scroll_until_visible(self, locator, max_scrolls: int = 40):
        return self._dp.scroll_until_visible(locator, max_scrolls)

    def find_first_file_row(self):
        return self._dp.find_first_file_row()

    def find_first_folder_row(self):
        return self._dp.find_first_folder_row()

    def find_user_rows(self, count: int = 50):
        return self._dp.find_user_rows(count)

    def select_row(self, row) -> None:
        # Scroll the (possibly virtualised) row into view first so the checkbox
        # is interactable — otherwise the tick silently misses and the toolbar
        # action fires with nothing selected.
        try:
            row.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        self._dp.select_row(row)

    def select_rows(self, rows) -> int:
        return self._dp.select_rows(rows)

    @staticmethod
    def row_filename(row) -> str:
        return DeletePage.row_filename(row)

    def get_snackbar_text(self, timeout: int = 5000) -> str:
        return self._dp.get_snackbar_text(timeout)

    # ── Trash navigation ───────────────────────────────────────
    def _trash_node_visible(self, timeout: int = 5000) -> bool:
        try:
            self.trash_node.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    # Direct selector for the ROOT (level-1) node's own expand arrow — when the
    # root is collapsed the nested level-2 Trash node is removed from the DOM.
    _ROOT_TOGGLE = (
        '#filemanager_tree > ul > li.e-list-item.e-level-1 '
        '> .e-text-content > .e-icon-expandable'
    )

    def _trash_node_shown(self) -> bool:
        """Instant check: is the Trash node actually VISIBLE (not just present)?
        When the root is collapsed the node sits inside a display:none <ul>, so
        it's in the DOM but hidden — visibility is the signal we want."""
        try:
            return self.trash_node.first.is_visible()
        except Exception:
            return False

    _ROOT_NODE = '#filemanager_tree > ul > li.e-list-item.e-level-1'
    _ROOT_TEXT = (
        '#filemanager_tree > ul > li.e-list-item.e-level-1 '
        '> .e-text-content > .e-list-text'
    )

    def _reveal_trash(self, timeout_ms: int = 16000) -> bool:
        """Poll until the Trash tree node is VISIBLE.

        The left nav tree mounts asynchronously and can land with the level-1
        'Ankit's Drive' root collapsed (hiding the nested level-2 Trash node in a
        display:none <ul>) or with its children not yet loaded. We wait for the
        tree, then:
          • if the root shows an expand arrow → click it to expand;
          • else (root expanded but Trash still not shown) → click the root text
            to (re)load its children;
        re-checking visibility until Trash appears or we time out.
        """
        import time
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                if self._trash_node_shown():
                    return True
                if self.page.locator('#filemanager_tree').count() == 0:
                    self.page.wait_for_timeout(400)
                    continue
                toggle = self.page.locator(self._ROOT_TOGGLE)
                if toggle.count() > 0:                 # root collapsed → expand
                    try:
                        toggle.first.click(timeout=1500)
                        self.page.wait_for_timeout(500)
                    except Exception:
                        pass
                elif self.page.locator(self._ROOT_NODE).count() > 0:
                    # root expanded but Trash not rendered → nudge children load
                    try:
                        self.page.locator(self._ROOT_TEXT).first.click(timeout=1500)
                        self.page.wait_for_timeout(600)
                    except Exception:
                        pass
                if self._trash_node_shown():
                    return True
            except Exception:
                pass
            self.page.wait_for_timeout(400)
        # Timed out — capture what the tree looks like so the failure message
        # carries the real cause (no -s needed).
        self._last_diag = self._tree_diag()
        print(f"  [DEBUG] reveal_trash failed: {self._last_diag}")
        return self._trash_node_shown()

    def _tree_diag(self) -> str:
        """One-line snapshot of the nav-tree state for diagnostics."""
        try:
            titles = self.page.locator('#filemanager_tree li.e-list-item .e-list-text')
            sample = []
            for i in range(min(titles.count(), 8)):
                try:
                    sample.append(titles.nth(i).inner_text(timeout=500).strip()[:20])
                except Exception:
                    continue
            return (
                f"tree={self.page.locator('#filemanager_tree').count()} "
                f"rootL1={self.page.locator(self._ROOT_NODE).count()} "
                f"expandToggle={self.page.locator(self._ROOT_TOGGLE).count()} "
                f"trashNodes={self.trash_node.count()} "
                f"navItems={titles.count()} sample={sample} url={self.page.url}"
            )
        except Exception as e:
            return f"diag-error: {e}"

    def is_trash_visible(self) -> bool:
        """Whether the Trash node is reachable in the left sidebar tree."""
        self._up._dismiss_popup()
        if self._reveal_trash(6000):
            return True
        try:
            self.reload_grid()
        except Exception:
            pass
        if self._reveal_trash(8000):
            return True
        try:
            self.relogin()              # token likely stale in a full-suite run
        except Exception:
            pass
        return self._reveal_trash(12000)

    def get_trash_folder_id(self) -> str:
        """Read the Trash folder id live from the tree node's data-id, falling
        back to the configured TRASH_FOLDER_ID if the attribute can't be read."""
        try:
            val = self.trash_node.get_attribute("data-id", timeout=3000)
            if val:
                return val.strip()
        except Exception:
            pass
        return TRASH_FOLDER_ID

    def open_trash(self) -> None:
        """Click the Trash sidebar node and wait for the grid to settle.

        If the tree node isn't resolvable (e.g. the tab is parked in a view that
        doesn't render it), reload to My Drive first so the full sidebar mounts.
        """
        self._up._dismiss_popup()
        # Retry the reveal+click a few times. Reset escalates: a plain reload
        # first (cheap), then a full re-login (handles an expired token in a
        # long full-suite run, the usual cause of the tree not mounting).
        for attempt in range(3):
            if self._reveal_trash(8000):
                try:
                    node = self.trash_node.first
                    node.scroll_into_view_if_needed(timeout=3000)
                    node.click(timeout=5000)
                    self._wait_grid_after_open()
                    return
                except Exception as e:
                    print(f"  [DEBUG] Trash click failed (attempt {attempt + 1}): {e}")
            try:
                if attempt == 0:
                    self.reload_grid()
                else:
                    self.relogin()      # token likely stale — refresh the session
            except Exception as e:
                print(f"  [DEBUG] reset failed (attempt {attempt + 1}): {e}")
        # Last try — if the node still won't reveal, fail with the tree snapshot
        # embedded so the cause shows up in the test report without -s.
        if not self._reveal_trash(12000):
            raise AssertionError(f"[UI] Could not reveal Trash node. {self._last_diag}")
        node = self.trash_node.first
        node.scroll_into_view_if_needed(timeout=3000)
        node.click(force=True)
        self._wait_grid_after_open()

    def _wait_grid_after_open(self) -> None:
        """Wait for the file-manager grid content to settle after navigation."""
        try:
            self.page.locator('#filemanager_grid .e-content').first.wait_for(
                state="visible", timeout=10000
            )
        except Exception:
            pass
        self.page.wait_for_timeout(1000)
        self._scroll_grid_top()

    def _scroll_grid_top(self) -> None:
        """Reset the virtualised grid to the top so the first page is rendered."""
        try:
            self.page.locator('#filemanager_grid .e-content').first.evaluate(
                "el => { el.scrollTop = 0; }"
            )
            self.page.wait_for_timeout(250)
        except Exception:
            pass

    def count_trash_items(self, max_scrolls: int = 60) -> int:
        """Accurate count of trashed items across ALL pages.

        The grid is virtualised — only ~20 rows live in the DOM at once — so we
        scroll top-to-bottom collecting each row's data-uid and count the
        distinct set. A plain visible-row count would miss later pages and could
        read 0 while items remain (the pagination gap behind the empty-trash bug).
        """
        content = self.page.locator('#filemanager_grid .e-content').first
        uids = set()
        try:
            content.evaluate("el => { el.scrollTop = 0; }")
            self.page.wait_for_timeout(200)
        except Exception:
            pass
        for _ in range(max_scrolls):
            rows = self.page.locator('tr.e-row:not(.Restricted)')
            for i in range(rows.count()):
                try:
                    u = rows.nth(i).get_attribute("data-uid")
                    if u:
                        uids.add(u)
                except Exception:
                    continue
            try:
                before = content.evaluate("el => el.scrollTop")
                content.evaluate("el => { el.scrollTop = el.scrollTop + el.clientHeight; }")
                self.page.wait_for_timeout(200)
                after = content.evaluate("el => el.scrollTop")
                if after == before:
                    break   # reached the bottom
            except Exception:
                break
        return len(uids)

    def has_trash_items(self) -> bool:
        """Fast 'is there anything on the current first page?' check for the
        empty-trash loop — avoids a full scroll-through every iteration."""
        self._scroll_grid_top()
        return len(self.find_user_rows(5)) > 0

    # ── Selection ──────────────────────────────────────────────
    def select_all(self) -> None:
        """Tick the grid header 'select all' checkbox.

        Syncfusion hides the real <input.e-checkselectall> and renders a styled
        wrapper/frame on top, so we click the visible wrapper (falling back to a
        forced click on the frame span) rather than the hidden input.
        """
        self._up._dismiss_popup()
        wrapper = self.page.locator(
            '#filemanager_grid .e-headerchkcelldiv .e-checkbox-wrapper'
        ).first
        try:
            wrapper.wait_for(state="visible", timeout=5000)
            wrapper.click()
        except Exception:
            self.page.locator(
                '#filemanager_grid .e-headerchkcelldiv .e-frame'
            ).first.click(force=True)
        self.page.wait_for_timeout(400)

    # ── Restore ────────────────────────────────────────────────
    def is_restore_enabled(self) -> bool:
        try:
            return self.restore_btn.is_visible() and \
                self.restore_btn.get_attribute("aria-disabled") != "true"
        except Exception:
            return False

    def _resolve_action_dialog(self, texts) -> str:
        """Click the first visible dialog button whose label matches `texts`.
        Restore/conflict flows can pop a MUI dialog that blocks the API call
        until confirmed. Returns the matched label, or "" if no dialog showed.
        """
        for t in texts:
            try:
                btn = self.page.locator(
                    f'.MuiDialog-root button:has-text("{t}"), '
                    f'[role="dialog"] button:has-text("{t}")'
                ).first
                if btn.is_visible():
                    btn.click(timeout=2000)
                    self.page.wait_for_timeout(300)
                    return t
            except Exception:
                continue
        return ""

    def click_restore(self) -> None:
        self.restore_btn.wait_for(state="visible", timeout=5000)
        self.restore_btn.click()
        self.page.wait_for_timeout(400)
        # A restore can raise a confirmation / name-conflict dialog that holds
        # back the restoreFiles call until a choice is made — resolve it.
        label = self._resolve_action_dialog(
            ["RESTORE", "Restore", "Keep Both", "Replace", "YES", "Yes", "OK", "CONFIRM", "Confirm"]
        )
        if label:
            print(f"  [UI] Resolved restore dialog via '{label}'")

    # ── Delete Forever ─────────────────────────────────────────
    def is_delete_forever_enabled(self) -> bool:
        try:
            return self.delete_forever_btn.is_visible() and \
                self.delete_forever_btn.get_attribute("aria-disabled") != "true"
        except Exception:
            return False

    def click_delete_forever(self) -> None:
        self.delete_forever_btn.wait_for(state="visible", timeout=5000)
        self.delete_forever_btn.click()
        self.page.wait_for_timeout(300)

    def wait_for_delete_forever_popup(self) -> None:
        """Use the DELETE FOREVER confirm button as the popup-presence anchor."""
        self.delete_forever_confirm_btn.wait_for(state="visible", timeout=5000)

    def confirm_delete_forever(self) -> None:
        self.wait_for_delete_forever_popup()
        self.delete_forever_confirm_btn.click()
        self.page.wait_for_timeout(500)

    def delete_forever_selected(self) -> None:
        """Full purge flow: toolbar Delete Forever + confirm in the popup."""
        self.click_delete_forever()
        self.confirm_delete_forever()
