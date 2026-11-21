"""Browser UI smoke test, grounded against a real local HTTP Convexa server."""

from pathlib import Path
import os, re, requests, socket, subprocess, sys, tempfile, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "screenshots"
OUTPUT.mkdir(exist_ok=True)


def main():
    html = (ROOT / "web/index.html").read_text()
    html = re.sub(r'<link rel="stylesheet"[^>]*>', "", html)
    html = re.sub(r'<script defer src="[^\"]+"></script>', "", html)
    js = "\n".join(
        (ROOT / "web" / f).read_text() for f in ("samples.js", "main.js", "enhancements.js")
    )
    js = js.replace("location.pathname", "(window.__virtualPath||location.pathname)")
    # no CSS.escape needed for synthetic local node ids, but Chromium supports it
    with tempfile.TemporaryDirectory(prefix="convexa-ui-") as directory:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["CONVEXA_DATA_DIR"] = directory
        proc = subprocess.Popen(
            [sys.executable, "app.py", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(60):
                try:
                    if requests.get(base + "/api/health", timeout=0.25).ok:
                        break
                except requests.RequestException:
                    time.sleep(0.1)
            session = requests.Session()

            def relay(path, options):
                data = options.get("body")
                if isinstance(data, list):
                    data = bytes(data)
                resp = session.request(
                    options.get("method", "GET"),
                    base + path,
                    headers=options.get("headers", {}),
                    data=data,
                    timeout=30,
                )
                return {
                    "status": resp.status_code,
                    "text": resp.text,
                    "contentType": resp.headers.get("content-type", "application/json"),
                }

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"]
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900}, device_scale_factor=1
                )
                page.set_default_timeout(6500)
                print("browser created", flush=True)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.expose_function("relayApi", relay)
                print("set content", flush=True)
                page.set_content(html)
                page.add_style_tag(content=(ROOT / "web/styles.css").read_text())
                page.add_style_tag(content=(ROOT / "web/enhancements.css").read_text())
                page.evaluate("""() => {
                  window.__virtualPath='/';window.history.pushState=(_a,_b,path)=>{window.__virtualPath=path};
                  window.fetch=async(path,options={})=>{
                    const safe={...options};
                    if(safe.body instanceof Blob)safe.body=Array.from(new Uint8Array(await safe.body.arrayBuffer()));
                    const reply=await window.relayApi(String(path),safe);
                    return new Response(reply.text,{status:reply.status,headers:{'Content-Type':reply.contentType}});
                  };
                }""")
                print("add script", flush=True)
                page.add_script_tag(content=js)
                print("script loaded", flush=True)
                page.wait_for_timeout(200)
                print("initial page errors:", len(errors), flush=True)
                page.wait_for_timeout(350)
                assert "Good ideas" in page.locator("h1").first.inner_text()
                print("landing passed", flush=True)
                page.locator('a[href="/why-convexa"]').first.click()
                assert page.locator("h1").first.inner_text() == "Why Convexa?"
                page.screenshot(path=str(OUTPUT / "why-public.png"), full_page=True)
                print("why passed", flush=True)
                page.get_by_role("button", name="Get started").first.click()
                page.get_by_role("button", name="Create an account").click()
                page.locator("#email").fill("tester@example.org")
                page.locator("#password").fill("StrongPassword123!")
                page.locator("#auth-form button[type=submit]").click()
                page.wait_for_timeout(450)
                print("auth submitted", flush=True)
                assert page.locator(".page-title").first.inner_text() == "Your knowledge"
                page.get_by_role("button", name="Add knowledge").click()
                page.locator('[data-command="capture-tab"][data-value="youtube"]').click()
                page.locator('#capture-form input[name="title"]').fill("Convexa Database Lecture")
                page.locator('#capture-form input[name="url"]').fill(
                    "https://www.youtube.com/watch?v=jfKfPfyJRdk"
                )
                page.locator('#capture-form textarea[name="transcript"]').fill(
                    "00:00:42 A database system stores information.\n00:01:25 Normalization reduces data redundancy."
                )
                page.locator('#capture-form button[type="submit"]').click()
                page.wait_for_timeout(500)
                page.locator(".entry-title").first.click()
                page.wait_for_timeout(250)
                assert page.locator(".source-grid").count() == 1
                assert page.locator(".transcript-segment").count() == 2
                page.screenshot(path=str(OUTPUT / "youtube-desktop.png"), full_page=True)
                page.locator("#transcript-filter").fill("normalization")
                assert page.locator(".transcript-segment:visible").count() == 1
                page.locator(".transcript-segment:visible").click()
                assert "start=85" in page.locator("#convexa-video").get_attribute("src")
                page.get_by_role("button", name="Your knowledge").first.click()
                page.get_by_role("button", name="Add knowledge").click()
                page.locator('[data-command="capture-tab"][data-value="file"]').click()
                page.locator('#capture-form input[name="title"]').fill("Graph Algorithms Notes")
                page.locator("#capture-file").set_input_files(
                    {
                        "name": "graph.txt",
                        "mimeType": "text/plain",
                        "buffer": b"Breadth-first search explores a graph by levels.",
                    }
                )
                page.locator('#capture-form button[type="submit"]').click()
                page.wait_for_timeout(450)
                page.locator("#global-search").fill("breadth-first search")
                page.locator("#global-search").press("Enter")
                page.wait_for_timeout(350)
                assert "Graph Algorithms" in page.locator(".entry-title").first.inner_text()
                page.screenshot(path=str(OUTPUT / "search-desktop.png"), full_page=True)
                page.get_by_role("button", name="ARIA assistant").click()
                assert page.locator("#ask-form textarea").is_visible()
                page.screenshot(path=str(OUTPUT / "aria-desktop.png"), full_page=True)
                page.get_by_role("button", name="Settings").click()
                assert page.locator("#ai-settings-form").count() == 1
                page.locator("#key-groq").fill("gsk_example_unusable")
                page.locator("#ai-settings-form").get_by_role(
                    "button", name="Save connections"
                ).click()
                page.wait_for_timeout(400)
                assert "Saved" in page.locator("body").inner_text()
                page.screenshot(path=str(OUTPUT / "settings-desktop.png"), full_page=True)
                page.get_by_role("button", name="Focus timer").click()
                page.locator("#custom-timer").fill("18")
                page.locator("#custom-timer-form").get_by_role("button", name="Set minutes").click()
                assert page.locator("#timer-face").inner_text() == "18:00"
                page.get_by_role("button", name="Knowledge map").click()
                page.wait_for_timeout(400)
                assert page.locator(".map-node").count() == 2
                page.locator(".map-node").first.get_by_role("button", name="Connect").click()
                page.locator(".map-node").nth(1).get_by_role("button", name="Select").click()
                page.wait_for_timeout(320)
                assert "SAVED LINKS · 1" in page.locator(".map-side").inner_text()
                # Drag a real knowledge card and confirm its position was saved via HTTP.
                map_node = page.locator(".map-node").first
                old_x = float(map_node.get_attribute("data-x"))
                pos = map_node.locator(".map-node-title").bounding_box()
                sx = pos["x"] + pos["width"] / 2
                sy = pos["y"] + pos["height"] / 2
                page.mouse.move(sx, sy)
                page.mouse.down()
                page.mouse.move(sx + 38, sy + 22, steps=8)
                page.mouse.up()
                page.wait_for_timeout(250)
                saved_x = float(map_node.get_attribute("data-x"))
                assert abs(saved_x - old_x) > 20, "Map drag did not move node"
                stored = session.get(base + "/api/mindmap").json()["nodes"]
                assert any(
                    n["item_id"] == map_node.get_attribute("data-map-id")
                    and abs(n["x"] - saved_x) < 1
                    for n in stored
                ), "Map position not persisted"
                page.screenshot(path=str(OUTPUT / "mindmap-desktop.png"), full_page=True)
                page.get_by_role("button", name="Why Convexa").click()
                assert page.locator(".why-index").count() == 1
                page.screenshot(path=str(OUTPUT / "why-workspace.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator(".mobile-menu-btn").click()
                page.get_by_role("button", name="Knowledge map").click()
                page.wait_for_timeout(200)
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth+3"
                ), "Horizontal overflow on mobile"
                assert page.locator(".map-viewport").count() == 1
                page.screenshot(path=str(OUTPUT / "mindmap-mobile.png"), full_page=True)
                page.locator(".mobile-menu-btn").click()
                assert "open" in page.locator(".sidebar").get_attribute("class")
                page.locator('.sidebar [data-command="view"][data-value="ask"]').click()
                page.wait_for_timeout(200)
                assert page.locator("#ask-form textarea").is_visible()
                page.screenshot(path=str(OUTPUT / "aria-mobile.png"), full_page=True)
                assert not errors, errors
                print(
                    "BROWSER REDESIGN: landing, why, auth, youtube, transcript timestamp, file search, ARIA, Settings credentials, custom focus, mind map connect, mobile menu: PASS"
                )
                print("BROWSER PAGE ERRORS:", len(errors))
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
