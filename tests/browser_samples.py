"""Exercise editable capture samples through the real app and upload API."""

from pathlib import Path
import os, socket, subprocess, sys, tempfile, time, urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as data:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    env = {**os.environ, "CONVEXA_DATA_DIR": data}
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/health")
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/login")
            page.get_by_role("button", name="Create an account").click()
            page.locator("#email").fill("sample@example.org")
            page.locator("#password").fill("StrongPassword123!")
            page.locator("#auth-form button[type=submit]").click()
            page.get_by_role("button", name="Add knowledge").wait_for()
            for kind in ["note", "youtube", "web", "chat", "file", "code"]:
                page.get_by_role("button", name="Add knowledge").click()
                page.locator(f'[data-command="capture-tab"][data-value="{kind}"]').click()
                page.get_by_role("button", name="Use sample", exact=True).click()
                assert page.locator("[name=title]").input_value()
                assert page.locator("[name=body]").input_value()
                assert page.evaluate("state.items.length") == [
                    "note",
                    "youtube",
                    "web",
                    "chat",
                    "file",
                    "code",
                ].index(kind)
                if kind == "youtube":
                    assert "6Iu45VZGQDk" in page.locator("[name=url]").input_value()
                    assert page.locator("[name=transcript]").input_value() == ""
                if kind == "file":
                    assert (
                        page.locator("#capture-file").evaluate("(e)=>e.files[0].name")
                        == "dbms-sample-notes.txt"
                    )
                if kind == "note":
                    page.locator("[name=title]").fill("My edited sample")
                    page.once("dialog", lambda d: d.dismiss())
                    page.get_by_role("button", name="Use sample", exact=True).click()
                    assert page.locator("[name=title]").input_value() == "My edited sample"
                page.locator("#capture-submit").click()
                page.locator("#capture-form").wait_for(state="detached")
            page.locator('[data-command="view"][data-value="map"]').click()
            page.locator('.map-node').first.wait_for()
            assert page.locator('.map-lines line').count() == 0
            cards = page.locator('.map-node')
            cards.nth(0).locator('[data-command="map-link"]').click()
            cards.nth(1).locator('[data-command="map-link"]').click()
            page.locator('[data-command="map-unlink"]').wait_for()
            assert page.locator('.map-lines line.manual').count() == 1
            page.reload()
            page.locator('[data-command="view"][data-value="map"]').click()
            page.locator('[data-command="map-unlink"]').wait_for()
            page.locator('[data-command="map-unlink"]').click()
            page.locator('[data-command="map-unlink"]').wait_for(state="detached")
            assert page.locator('.map-lines line').count() == 0
            page.locator('[data-command="map-suggestions"]').click()
            assert page.locator('.map-lines line').count() > 0
            page.locator('[data-command="map-suggestions"]').click()
            assert page.locator('.map-lines line').count() == 0
            page.locator('[data-command="view"][data-value="settings"]').click()
            assert "Not configured" in page.locator('.settings-layout').inner_text()
            page.on('dialog', lambda d: d.accept())
            page.locator('[data-command="test-ai"]').click()
            page.get_by_role('heading', name='Last connection test').wait_for()
            assert "No cloud chat provider configured" in page.locator('.settings-layout').inner_text()
            page.locator('[data-command="view"][data-value="all"]').click()
            page.locator("#global-search").fill("Atomicity")
            page.locator("#global-search").press("Enter")
            page.locator(".entry-title").filter(
                has_text="DBMS sample document: relational databases"
            ).wait_for()
            page.locator(".entry-title").filter(
                has_text="DBMS sample document: relational databases"
            ).click()
            assert "Atomicity" in page.locator(".detail-content").first.inner_text()
            page.get_by_role("button", name="Edit item", exact=True).click()
            assert page.get_by_role("button", name="Use sample", exact=True).count() == 0
            page.locator("[data-command=close-modal]").first.click()
            page.get_by_role("button", name="Add knowledge").click()
            page.locator('[data-command="capture-tab"][data-value="voice"]').click()
            assert page.get_by_role("button", name="Use sample", exact=True).count() == 0
            page.locator('[data-command="capture-tab"][data-value="youtube"]').click()
            page.get_by_role("button", name="Use sample", exact=True).click()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
            print(
                "PASS: all six samples save; document extracts and searches; drafts protected; edit/voice excluded; mobile fits; no JS errors"
            )
    finally:
        proc.terminate()
        proc.wait(timeout=5)
