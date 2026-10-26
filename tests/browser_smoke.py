"""Opt-in live browser verification in an isolated project copy.

Requires Playwright and installed Chrome; never changes the project's data.
Run from the project root: python tests/browser_smoke.py
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Optional temporary install used by the workshop verification environment.
sys.path.append(str(Path(tempfile.gettempdir()) / "labready-browser-tools"))

from app import DEMO_REQUEST


def main():
    from playwright.sync_api import expect, sync_playwright
    expect.set_options(timeout=240000)

    artifacts = Path(tempfile.mkdtemp(prefix="labready-browser-artifacts-"))
    with tempfile.TemporaryDirectory(prefix="labready-browser-project-", ignore_cleanup_errors=True) as folder:
        project = Path(folder)
        assert project.resolve().parent == Path(tempfile.gettempdir()).resolve()
        for file in ROOT.glob("*.py"):
            shutil.copy2(file, project / file.name)
        shutil.copy2(ROOT / "SKILL.md", project / "SKILL.md")
        shutil.copytree(ROOT / "data", project / "data")
        shutil.copytree(ROOT / ".streamlit", project / ".streamlit")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ)
        env["OLLAMA_MODEL"] = "gemma3:4b"
        with (artifacts / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", str(project / "streamlit_app.py"),
                 "--server.headless=true", f"--server.port={port}", "--server.address=127.0.0.1",
                 "--browser.gatherUsageStats=false"], cwd=project, env=env, stdout=log,
                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                base = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 40
                while True:
                    try:
                        with urlopen(base + "/_stcore/health", timeout=2) as response:
                            assert response.status == 200
                        break
                    except OSError:
                        if time.monotonic() >= deadline or process.poll() is not None:
                            raise RuntimeError("Streamlit failed to start; inspect " + str(artifacts / "server.log"))
                        time.sleep(.2)
                print("PASS: Streamlit startup and health endpoint.", flush=True)
                with sync_playwright() as p:
                    browser = p.chromium.launch(channel="chrome", headless=True)
                    page = browser.new_page(viewport={"width": 1400, "height": 1050})
                    page.set_default_timeout(240000)
                    page.goto(base)
                    expect(page.get_by_role("heading", name="LabReady", exact=True)).to_be_visible()
                    expect(page.get_by_text("Demonstration data — not verified college availability.", exact=True)).to_be_visible()
                    expect(page.get_by_text("Local model · gemma3:4b", exact=True)).to_be_visible()
                    expect(page.get_by_role("heading", name="Know what will work before you book.", exact=True)).to_be_visible()
                    page.screenshot(path=str(artifacts / "initial-desktop.png"), full_page=True)
                    field = page.get_by_role("textbox", name="Session request or follow-up")

                    def reset():
                        page.get_by_role("button", name="New session", exact=True).click()
                        expect(field).to_have_value("")
                        expect(page.locator(".lab-card")).to_have_count(0)

                    def complete_check():
                        page.get_by_role("button", name="Load example", exact=True).click()
                        expect(field).to_have_value(DEMO_REQUEST)
                        page.get_by_role("button", name="Check readiness", exact=True).click()
                        expect(page.get_by_role("heading", name="All checked labs blocked", exact=True)).to_be_visible()

                    page.get_by_role("button", name="Load example", exact=True).click()
                    expect(field).to_have_value(DEMO_REQUEST)
                    expect(page.locator(".lab-card")).to_have_count(0)
                    print("PASS: Load example fills input without checking.", flush=True)
                    page.get_by_role("button", name="Check readiness", exact=True).click()
                    expect(page.get_by_role("heading", name="All checked labs blocked", exact=True)).to_be_visible()
                    expect(page.locator(".lab-card").filter(has=page.get_by_text("Lab A", exact=True))).to_contain_text("42 working / 60 required")
                    expect(page.locator(".lab-card").filter(has=page.get_by_text("Lab C", exact=True))).to_contain_text("Python 3.10")
                    expect(page.locator(".lab-card .badge.ready").first).to_be_visible()
                    page.get_by_text("How this was checked", exact=True).click()
                    expect(page.get_by_text("1. Model / validated agent · model requested", exact=True)).to_be_visible()
                    page.screenshot(path=str(artifacts / "results-desktop.png"), full_page=True)
                    print("PASS: Actual Gemma-backed readiness, blockers, alternatives, and trace.", flush=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=str(artifacts / "results-mobile.png"), full_page=True)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"), "Mobile layout overflows horizontally"
                    page.set_viewport_size({"width": 1400, "height": 1050})

                    reset()
                    field.fill("Check a Python 3.12 practical for 60 students.")
                    page.get_by_role("button", name="Check readiness", exact=True).click()
                    expect(page.get_by_role("heading", name="Incomplete / error", exact=True)).to_be_visible()
                    expect(page.locator(".lab-card")).to_have_count(0)
                    print("PASS: Missing-information request is incomplete, not assumed ready.", flush=True)
                    field.fill("Use 2026-10-27 from 10:00 to 12:00.")
                    page.get_by_role("button", name="Check readiness", exact=True).click()
                    expect(page.get_by_role("heading", name="All checked labs blocked", exact=True)).to_be_visible()
                    expect(page.locator(".lab-card .badge.ready").first).to_be_visible()
                    print("PASS: Missing information clarifies; follow-up completes using conversation history.", flush=True)

                    booking_path = project / "data" / "bookings.json"
                    data = json.loads(booking_path.read_text(encoding="utf-8"))
                    data["bookings"].append({"id": "browser-fixture", "lab_id": "lab-b", "date": "2026-10-27", "start": "12:00", "end": "17:00"})
                    booking_path.write_text(json.dumps(data), encoding="utf-8")
                    # Same conversation: a repeated check must reread changed data.
                    complete_check()
                    expect(page.get_by_text("No feasible alternative found.", exact=True)).to_be_visible()
                    expect(page.locator(".lab-card .badge.ready")).to_have_count(0)
                    print("PASS: Changed booking affects the next check; no availability cache.", flush=True)

                    booking_path.write_text('{"bookings":', encoding="utf-8")
                    page.get_by_role("button", name="Check readiness", exact=True).click()
                    expect(page.get_by_role("heading", name="Incomplete / error", exact=True)).to_be_visible()
                    expect(page.locator(".lab-card")).to_have_count(0)
                    expect(page.get_by_text("Availability is unknown. No successful check for this request; previous results are not shown.", exact=True)).to_be_visible()
                    page.screenshot(path=str(artifacts / "failure-desktop.png"), full_page=True)
                    print("PASS: Failed new request removes prior cards and marks availability unknown.", flush=True)
                    browser.close()
            finally:
                if os.name == "nt" and process.poll() is None:
                    # The Windows venv launcher can own a second Python process.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, check=False)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    print(f"Browser artifacts: {artifacts}", flush=True)


if __name__ == "__main__":
    main()
