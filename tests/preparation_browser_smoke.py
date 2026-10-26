"""Read-only browser checks against the running REAL project. Never approves."""
import argparse
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(Path(tempfile.gettempdir()) / "labready-browser-tools"))


def main():
    from playwright.sync_api import expect, sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()
    expect.set_options(timeout=60000)
    artifacts = ROOT / ".labready/runtime"
    artifacts.mkdir(parents=True, exist_ok=True)
    target = ROOT / ".labready/practicals/python-data"
    existed = target.exists()
    for endpoint in ("/_stcore/health", "/"):
        with urlopen(args.url + endpoint, timeout=5) as response:
            assert response.status == 200
    print("PASS: Real project health and root return HTTP 200.", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1050})
            page.goto(args.url)
            expect(page.get_by_role("heading", name="LabReady", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Prepare this computer", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Approve and prepare", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Inspect and propose preparation", exact=True).click()
            expect(page.get_by_role("heading", name="Inspection findings", exact=True)).to_be_visible()
            expect(page.get_by_text("Exact target: " + str(target), exact=True)).to_be_visible()
            if not existed:
                expect(page.get_by_text("NOT PREPARED", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Approve and prepare", exact=True)).to_be_enabled()
                assert not target.exists(), "Inspection unexpectedly created the practical environment"
            print("PASS: Actual local inspection and concrete actions precede approval; no preparation executed.", flush=True)
            field = page.get_by_role("textbox", name="Required local Python version", exact=True)
            field.fill("3.11")
            field.press("Tab")
            expect(page.get_by_role("button", name="Approve and prepare", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Inspect and propose preparation", exact=True).click()
            expect(page.get_by_text("MANUAL ATTENTION REQUIRED", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Fictional fallback options", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Approve and prepare", exact=True)).to_have_count(0)
            print("PASS: Unsupported interpreter blocks execution and exposes explicitly fictional fallback options.", flush=True)
            field.fill("3.12")
            field.press("Tab")
            expect(page.get_by_role("heading", name="Fictional fallback options", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Inspect and propose preparation", exact=True).click()
            if not existed:
                expect(page.get_by_text("NOT PREPARED", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Approve and prepare", exact=True)).to_be_enabled()
            page.get_by_role("heading", name="Prepare this computer", exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(artifacts / "preparation-ui.png"), full_page=True)
            assert target.exists() == existed, "Read-only browser checks changed the managed environment"
            print("PASS: Changing requirements invalidates the old plan and results. Approval was deliberately left pending.", flush=True)
            print(f"Screenshot: {artifacts / 'preparation-ui.png'}", flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
