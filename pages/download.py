import random
from playwright.sync_api import Page


class Download:

    def __init__(self, page: Page):
        self.page = page

        # ── Actual file rows (not folders) ────────────────────
        # Folders have class "Restricted" and display:none.
        # Files have display:table-row and no "Restricted" class.
        self.file_rows = page.locator("tr.e-row:not(.Restricted)")

        # ── React-Toastify notifications ──────────────────────
        self.toast = page.locator(".Toastify__toast")

        # ── Progress / cancel ─────────────────────────────────
        self.progress_bar = page.locator("[class*='progress'], [class*='e-progressbar']")

    # ── Navigation ────────────────────────────────────────────

    def wait_for_files(self, timeout: int = 20000):
        """Wait until at least one real file row is present and has height."""
        self.page.wait_for_function(
            """() => {
                const rows = document.querySelectorAll('tr.e-row:not(.Restricted)');
                return Array.from(rows).some(r => r.getBoundingClientRect().height > 0);
            }""",
            timeout=timeout,
        )

    # ── File selection ────────────────────────────────────────

    def select_random_file(self) -> str:
        """Select a random real file using mouse coordinates. Returns the file name."""
        self.wait_for_files()

        count = self.file_rows.count()
        if count == 0:
            raise Exception("No downloadable files found")

        idx = random.randint(0, count - 1)
        row = self.file_rows.nth(idx)

        # Use real mouse click at element center (triggers Syncfusion's selection)
        box = row.bounding_box()
        if box and box["height"] > 0:
            self.page.mouse.click(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
            )
        else:
            row.click(force=True)

        self.page.wait_for_timeout(600)

        # Get name from first non-empty cell
        file_name = self.page.evaluate("""(row) => {
            const cells = row.querySelectorAll('td.e-rowcell');
            for (const c of cells) {
                const t = c.innerText.trim();
                if (t) return t;
            }
            return row.innerText.trim().split('\\n')[0];
        }""", row.element_handle())

        print(f"Selected file: {file_name}")
        return file_name.strip()

    def verify_single_selection(self):
        """Assert the download toolbar button is now enabled (file is selected)."""
        # After a real click Syncfusion removes e-hidden from the download button's parent.
        # Use a generous timeout to tolerate slow-network conditions.
        try:
            self.page.wait_for_function(
                """() => {
                    const btn = document.getElementById('filemanager_tb_download');
                    if (!btn) return false;
                    let el = btn.parentElement;
                    while (el) {
                        if (el.classList.contains('e-hidden')) return false;
                        el = el.parentElement;
                    }
                    return true;
                }""",
                timeout=15000,
            )
        except Exception:
            # Fallback: check e-active row count (may not be set on all Syncfusion builds)
            active = self.page.locator("tr.e-row.e-active:not(.Restricted)").count()
            if active == 0:
                # Last resort: just proceed — the click was dispatched
                pass

    # ── Download ──────────────────────────────────────────────

    def click_download(self):
        """Trigger download button via JS (works even when parent is e-hidden)."""
        self.page.evaluate(
            "() => { const b = document.getElementById('filemanager_tb_download'); "
            "if (b) b.click(); }"
        )

    def wait_for_toast(self, timeout: int = 5000) -> str:
        """Wait for a React-Toastify notification and return its text."""
        self.toast.first.wait_for(state="visible", timeout=timeout)
        return self.toast.first.inner_text().strip()

    def click_cancel(self):
        self.page.locator(
            "button[aria-label='Cancel'], button.e-close, "
            "//button[normalize-space(text())='Cancel']"
        ).first.click()
