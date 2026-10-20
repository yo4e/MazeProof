"""Exercise the actual UI in an isolated headless browser; no desktop takeover.

Run: .venv/bin/python scripts/e2e.py [--browser /path/to/headless/chromium]
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.samples import demo_model, demo_route, render  # noqa: E402
from playwright.sync_api import sync_playwright, expect  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser")
    args = parser.parse_args()
    evidence = ROOT / ".evidence"
    evidence.mkdir(exist_ok=True)
    problem = evidence / "problem.png"
    solution = evidence / "solution.png"
    render(demo_model()).save(problem)
    render(demo_model(), demo_route()).save(solution)
    pdf = evidence / "pair.pdf"
    render(demo_model()).save(
        pdf, "PDF", save_all=True, append_images=[render(demo_model(), demo_route())]
    )
    bad = evidence / "broken.png"
    bad.write_bytes(b"not an image")
    server = subprocess.Popen(
        [sys.executable, "-m", "mazeproof", "serve"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    checks = []
    started = time.monotonic()
    try:
        line = server.stdout.readline().strip()
        if not line.startswith("MazeProof: "):
            raise AssertionError("Server did not start: " + line)
        url = line.removeprefix("MazeProof: ")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=args.browser)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1100}, accept_downloads=True
            )
            page = context.new_page()
            errors = []
            requests = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("request", lambda r: requests.append(r.url))
            page.goto(url)
            page.screenshot(path=str(evidence / "welcome.png"), full_page=True)
            page.locator("#problem-file").set_input_files(str(problem))
            page.locator("#solution-file").set_input_files(str(solution))
            page.locator("#import-submit").click()
            expect(page.locator("#workbench")).to_be_visible(timeout=45000)
            expect(page.locator("#busy")).to_be_hidden()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            expect(page.locator("#approve")).to_be_disabled()
            checks.append("PNG pair upload -> unconfirmed, approval unavailable")
            page.locator("#tab-solution").click()
            expect(page.locator("#unknown-count")).to_have_text("15")
            page.get_by_text("座標で境界を編集", exact=True).click()
            # Resolve every red-occluded boundary separately, using the visible
            # coordinate controls. No direct mutation of app state.
            while page.locator("#unknown-list button").count():
                page.locator("#unknown-list button").first.click()
                page.locator("#edge-resolve").click()
            expect(page.locator("#unknown-count")).to_have_text("0")
            page.locator("#confirm-review").check()
            page.locator("#approve").click()
            expect(page.locator("#result-status")).to_have_text(
                "条件付き PASS", timeout=45000
            )
            checks.append("15 explicit boundary confirmations -> conditional PASS")
            page.screenshot(path=str(evidence / "confirmed.png"), full_page=True)
            with page.expect_download() as saved:
                page.locator("#save-project").click()
            project_path = evidence / "work.mazeproof"
            saved.value.save_as(project_path)
            project = json.loads(project_path.read_text())
            assert project["result"]["recognition"]["assurance"] == "human_confirmed"
            for selector, name in [
                ("#save-report", "report.json"),
                ("#save-html", "report.html"),
                ("#save-model", "model.json"),
                ("#save-overlay", "overlay.png"),
            ]:
                with page.expect_download() as saved:
                    page.locator(selector).click()
                saved.value.save_as(evidence / name)
            assert (
                json.loads((evidence / "report.json").read_text())["overallStatus"]
                == "PASS"
            )
            assert "human_confirmed" in (evidence / "report.html").read_text()
            assert (evidence / "overlay.png").read_bytes().startswith(b"\x89PNG")
            checks.append("Project, JSON/HTML report, model, overlay downloads")
            # A wall across the route invalidates approval immediately; undo/redo
            # do not revive old confirmation.
            page.locator("#tab-problem").click()
            page.locator("#edge-field").select_option("verticalWalls")
            page.locator("#edge-row").fill("0")
            page.locator("#edge-col").fill("1")
            page.locator("#edge-toggle").click()
            expect(page.locator("#result-status")).to_have_text("変更あり・再確認")
            expect(page.locator("#confirm-review")).not_to_be_checked()
            page.locator("#evaluate").click()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            expect(page.locator("#issues")).to_contain_text("ROUTE_WALL_CROSSING")
            page.locator("#confirm-review").check()
            page.locator("#approve").click()
            expect(page.locator("#result-status")).to_have_text("FAIL")
            page.locator("#undo").click()
            expect(page.locator("#result-status")).to_have_text("変更あり・再確認")
            page.locator("#redo").click()
            expect(page.locator("#result-status")).to_have_text("変更あり・再確認")
            page.locator("#undo").click()
            page.locator("#evaluate").click()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            checks.append(
                "Wall edit -> approval revoked -> FAIL; undo/redo require fresh review"
            )
            # Trace route through the actual canvas.
            page.locator("#tab-solution").click()
            page.locator("#clear-route").click()
            page.locator('[data-tool="route"]').click()
            box = page.locator("#canvas").bounding_box()
            for point in demo_route():
                page.locator("#canvas").click(
                    position={
                        "x": (24 + (point["col"] + 0.5) * 72) * box["width"] / 337,
                        "y": (24 + (point["row"] + 0.5) * 72) * box["height"] / 337,
                    }
                )
            page.locator("#route-reviewed").check()
            page.locator("#confirm-review").check()
            page.locator("#approve").click()
            expect(page.locator("#result-status")).to_have_text("条件付き PASS")
            checks.append(
                "Clear red route -> trace all cells on canvas -> approve PASS"
            )
            # Confirmed source change cannot silently retain approval.
            page.get_by_text("格子・切り出し・回転", exact=True).click()
            page.locator("#reanalyze").click()
            page.locator("#dialog-no").click()
            expect(page.locator("#result-status")).to_have_text("条件付き PASS")
            page.locator("#x1").fill("0")
            page.locator("#reanalyze").click()
            page.locator("#dialog-yes").click()
            expect(page.locator("#busy")).to_be_hidden(timeout=45000)
            expect(page.locator("#result-status")).to_have_text("変更あり・再確認")
            page.locator("#x1").fill("312")
            checks.append(
                "Failed reanalysis clears old PASS; original work remains recoverable"
            )
            page.locator("#reanalyze").click()
            page.locator("#dialog-yes").click()
            expect(page.locator("#busy")).to_be_hidden(timeout=45000)
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            checks.append(
                "Cancel reanalysis preserves work; confirmed reanalysis resets approval"
            )
            page.locator("#reset").click()
            page.locator("#dialog-no").click()
            expect(page.locator("#workbench")).to_be_visible()
            page.locator("#reset").click()
            page.locator("#dialog-yes").click()
            page.locator("#project-file").set_input_files(str(project_path))
            expect(page.locator("#workbench")).to_be_visible(timeout=45000)
            expect(page.locator("#busy")).to_be_hidden()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            checks.append("Reopen approved project -> fresh confirmation required")
            # Bad input recovery and sequential import.
            page.locator("#reset").click()
            page.locator("#dialog-yes").click()
            page.locator("#problem-file").set_input_files(str(bad))
            page.locator("#import-submit").click()
            expect(page.locator("#busy")).to_be_hidden(timeout=45000)
            expect(page.locator("#welcome")).to_be_visible()
            expect(page.locator("#message")).to_contain_text("PNG")
            page.locator("#problem-file").set_input_files(str(pdf))
            page.locator("#solution-file").set_input_files(str(pdf))
            page.locator("#problem-page").fill("1")
            page.locator("#solution-page").fill("2")
            page.locator("#import-submit").click()
            expect(page.locator("#workbench")).to_be_visible(timeout=45000)
            expect(page.locator("#busy")).to_be_hidden()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            expect(page.locator("#observation-notes")).to_contain_text("PDF")
            checks.append("Corrupt-image recovery -> explicit PDF pages 1/2 imported")
            # Cancellation under deterministic transport delay. Result must not
            # overwrite the prior screen even if the server eventually finishes.
            page.locator("#reset").click()
            page.locator("#dialog-yes").click()

            def delay(route):
                time.sleep(0.8)
                try:
                    route.continue_()
                except Exception:
                    pass

            page.route("**/api/demo", delay)
            page.locator("#demo").click()
            page.locator("#cancel").click()
            expect(page.locator("#welcome")).to_be_visible()
            expect(page.locator("#busy")).to_be_hidden()
            page.unroute("**/api/demo")
            page.wait_for_timeout(1000)
            expect(page.locator("#workbench")).to_be_hidden()
            page.locator("#demo").click()
            expect(page.locator("#workbench")).to_be_visible(timeout=45000)
            expect(page.locator("#busy")).to_be_hidden()
            checks.append(
                "Cancelled load cannot replace workspace; subsequent demo recovers"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(evidence / "mobile.png"), full_page=True)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), "Mobile horizontal overflow"
            checks.append("390px responsive layout without horizontal page overflow")
            assert not errors, errors
            assert all(u.startswith(url.split("/#")[0]) for u in requests), requests
            checks.append("No JavaScript errors and no external HTTP requests")
            browser.close()
        summary = {
            "checks": checks,
            "count": len(checks),
            "seconds": round(time.monotonic() - started, 2),
            "browser": "headless Chromium",
            "desktopUsed": False,
        }
        (evidence / "e2e.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    main()
