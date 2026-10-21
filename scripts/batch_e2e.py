"""Exercise the complete batch UI in an isolated headless browser."""

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.samples import demo_model, demo_route, render  # noqa: E402
from PIL import ImageDraw  # noqa: E402
from playwright.sync_api import sync_playwright, expect  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser")
    args = parser.parse_args()
    evidence = ROOT / ".evidence" / "batch"
    evidence.mkdir(parents=True, exist_ok=True)
    image = render(demo_model())
    paths = []
    for i in range(100):
        path = evidence / f"maze-{i + 1:03d}.png"
        image.save(path)
        paths.append(str(path))
    broken = evidence / "broken.png"
    broken.write_bytes(b"broken PNG")
    faint = image.copy()
    ImageDraw.Draw(faint).line((96, 168, 130, 168), fill=(160, 160, 160), width=7)
    faint_path = evidence / "faint.png"
    faint.save(faint_path)
    blocked_model = copy.deepcopy(demo_model())
    blocked_model["verticalWalls"][0][1] = True
    blocked = evidence / "blocked.png"
    render(blocked_model).save(blocked)
    solution = evidence / "solution.png"
    render(demo_model(), demo_route()).save(solution)
    pdf = evidence / "pair.pdf"
    image.save(
        pdf, "PDF", save_all=True, append_images=[render(demo_model(), demo_route())]
    )
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
        assert line.startswith("MazeProof: "), line
        url = line.removeprefix("MazeProof: ")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=args.browser)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, accept_downloads=True
            )
            requests, errors = [], []
            context.on("request", lambda r: requests.append(r.url))
            context.on(
                "page",
                lambda page: page.on(
                    "pageerror", lambda error: errors.append(str(error))
                ),
            )
            page = context.new_page()
            page.goto(url)
            with context.expect_page() as opened:
                page.locator("#help-link").click()
            guide = opened.value
            expect(guide).to_have_title("使い方 — MazeProof")
            assert guide.evaluate("window.opener === null")
            assert "#" not in guide.url
            guide.get_by_role("link", name="トップへ戻る", exact=True).click()
            expect(guide.locator("#welcome")).to_be_visible()
            guide.locator("#demo").click()
            expect(guide.locator("#workbench")).to_be_visible(timeout=45000)
            guide.close()
            checks.append(
                "Guide Home returns to a usable top page without resetting the original tab"
            )

            def new_batch(files):
                page.locator("#batch-start").click()
                page.locator("#batch-problems").set_input_files(files)

            def stop_batch():
                page.locator("#reset").click()
                page.locator("#dialog-yes").click()
                expect(page.locator("#welcome")).to_be_visible()

            # A launcher URL enters batch setup directly, with a usable private
            # session. A new tab must not reset the original page or server.
            launch_page = context.new_page()
            launch_page.goto(url.replace("/#", "/batch#"))
            expect(launch_page.locator("#batch-setup")).to_be_visible()
            expect(launch_page.locator("#welcome")).not_to_be_visible()
            assert "#" not in launch_page.url
            launch_page.locator("#batch-problems").set_input_files(paths[0])
            launch_page.locator("#batch-run-new").click()
            expect(launch_page.locator("#batch-counts")).to_contain_text(
                "確認待ち 1", timeout=45000
            )
            expect(page.locator("#welcome")).to_be_visible()
            launch_page.locator("#reset").click()
            launch_page.locator("#dialog-yes").click()
            expect(launch_page.locator("#welcome")).to_be_visible()
            launch_page.close()
            checks.append("Launcher entry opens batch setup and imports with a valid session")

            new_batch(paths[:5] + [str(broken), str(faint_path), str(blocked)])
            page.locator("#batch-solutions").set_input_files(str(solution))
            expect(page.locator("#batch-draft-count")).to_contain_text("解答あり 0")
            page.get_by_label("1件目の解答画像", exact=True).select_option("0")
            expect(page.locator("#batch-draft-count")).to_contain_text("解答あり 1")
            page.screenshot(path=str(evidence / "pairing.png"), full_page=True)

            def slow(route):
                time.sleep(0.8)
                route.continue_()

            page.route("**/api/batch-item", slow, times=1)
            page.locator("#batch-run-new").click()
            page.locator("#batch-pause").click()
            expect(page.locator("#batch-progress")).to_contain_text(
                "未処理が 7 件", timeout=45000
            )
            with page.expect_download() as download:
                page.locator("#batch-save").click()
            partial_path = evidence / "partial.mazeproof-batch"
            download.value.save_as(partial_path)
            partial = json.loads(partial_path.read_text())
            assert len(partial["items"]) == 8
            assert sum("project" in item for item in partial["items"]) == 1
            checks.append(
                "Pause after active item; all completed and queued inputs saved"
            )
            page.locator("#batch-resume").click()
            expect(page.locator("#batch-progress")).to_contain_text(
                "読み込みが終わりました", timeout=90000
            )
            expect(page.locator("#batch-counts")).to_contain_text("確認待ち 7")
            expect(page.locator("#batch-counts")).to_contain_text("エラー 1")
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 0")
            page.locator("#batch-filter").select_option("suspect")
            expect(page.locator("#batch-result-rows")).to_contain_text("faint.png")
            page.locator("#batch-filter").select_option("all")
            page.screenshot(path=str(evidence / "mixed-list.png"), full_page=True)
            checks.append(
                "Mixed pair, faint-wall provisional failure, ambiguous grid and corrupt input remain distinct"
            )

            row = page.locator("#batch-result-rows tr").nth(0)
            row.get_by_role("button", name="確認する", exact=True).click()
            expect(page.locator("#approve")).to_be_disabled()
            page.locator("#tab-solution").click()
            page.get_by_text("座標で境界を編集", exact=True).click()
            while page.locator("#unknown-list button").count():
                page.locator("#unknown-list button").first.click()
                page.locator("#edge-resolve").click()
            page.locator("#confirm-review").check()
            page.locator("#approve").click()
            expect(page.locator("#result-status")).to_have_text("条件付き PASS")
            page.locator("#batch-back").click()
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 1")
            page.locator("#batch-result-rows tr").nth(4).get_by_role(
                "button", name="確認する", exact=True
            ).click()
            page.locator("#batch-back").click()
            page.locator("#batch-result-rows tr").nth(0).get_by_role(
                "button", name="確認する", exact=True
            ).click()
            expect(page.locator("#result-status")).to_have_text("条件付き PASS")
            checks.append(
                "Per-item explicit approval survives navigation beyond the former four-item cache"
            )
            # Undo before any synchronization must not revive the old approval
            # through list navigation or the subsequent batch export.
            page.locator("#tab-problem").click()
            page.locator("#edge-field").select_option("verticalWalls")
            page.locator("#edge-row").fill("0")
            page.locator("#edge-col").fill("1")
            page.locator("#edge-toggle").click()
            page.locator("#undo").click()
            page.locator("#batch-back").click()
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 0")
            with page.expect_download() as download:
                page.locator("#batch-save").click()
            undo_path = evidence / "undo.mazeproof-batch"
            download.value.save_as(undo_path)
            undo_saved = json.loads(undo_path.read_text())
            assert (
                undo_saved["items"][0]["project"]["result"]["overallStatus"]
                == "NEEDS_REVIEW"
            )
            page.locator("#batch-result-rows tr").nth(0).get_by_role(
                "button", name="確認する", exact=True
            ).click()
            expect(page.locator("#result-status")).to_have_text("確認待ち")
            page.locator("#confirm-review").check()
            page.locator("#approve").click()
            expect(page.locator("#result-status")).to_have_text("条件付き PASS")
            checks.append(
                "Unsynced edit/undo stays unconfirmed through batch navigation and save"
            )
            # Change an approved wall; list/export must never retain that PASS.
            page.locator("#tab-problem").click()
            page.locator("#edge-field").select_option("verticalWalls")
            page.locator("#edge-row").fill("0")
            page.locator("#edge-col").fill("1")
            page.locator("#edge-toggle").click()
            page.locator("#batch-back").click()
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 0")
            with page.expect_download() as download:
                page.locator("#batch-save").click()
            saved_path = evidence / "edited.mazeproof-batch"
            download.value.save_as(saved_path)
            saved = json.loads(saved_path.read_text())
            assert (
                saved["items"][0]["project"]["edits"]["problem"]["model"][
                    "verticalWalls"
                ][0][1]
                is True
            )
            for control, filename in [
                ("batch-report-json", "report.json"),
                ("batch-report-html", "report.html"),
            ]:
                with page.expect_download() as download:
                    page.locator("#" + control).click()
                download.value.save_as(evidence / filename)
            report = json.loads((evidence / "report.json").read_text())
            assert report["counts"]["pass"] == 0 and report["counts"]["error"] == 1
            assert report["items"][5]["result"] is None
            checks.append(
                "Unsaved edit synchronizes before navigation, batch save and JSON/HTML reports"
            )

            stop_batch()
            # Deliberately forge a result; loading is not an approval path.
            saved["items"][0]["project"]["result"]["overallStatus"] = "PASS"
            saved["items"][0]["project"]["result"]["recognition"]["assurance"] = (
                "human_confirmed"
            )
            forged = evidence / "forged.mazeproof-batch"
            forged.write_text(json.dumps(saved))
            page.locator("#batch-project-file").set_input_files(str(forged))
            expect(page.locator("#batch-progress")).to_contain_text("未処理が 8 件")
            with page.expect_download() as download:
                page.locator("#batch-report-json").click()
            pending_report = evidence / "pending-report.json"
            download.value.save_as(pending_report)
            assert all(
                item["result"] is None
                for item in json.loads(pending_report.read_text())["items"]
            )
            page.locator("#batch-resume").click()
            expect(page.locator("#batch-progress")).to_contain_text(
                "読み込みが終わりました", timeout=90000
            )
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 0")
            page.locator("#batch-result-rows tr").nth(0).get_by_role(
                "button", name="確認する", exact=True
            ).click()
            expect(page.locator("#issues")).to_contain_text("ROUTE_WALL_CROSSING")
            page.locator("#batch-back").click()
            checks.append(
                "Restore keeps edits but ignores forged saved PASS; pending report has no trusted results"
            )
            # File setters can target hidden inputs; wait for editor sync and
            # list navigation just as a person opening the picker would.
            expect(page.locator("#batch-list")).to_be_visible()
            expect(
                page.get_by_label("6件目の問題を差し替え", exact=True)
            ).to_be_enabled()
            page.get_by_label("6件目の問題を差し替え", exact=True).set_input_files(
                paths[6]
            )
            try:
                expect(page.locator("#confirm-dialog")).to_be_visible(timeout=5000)
            except AssertionError:
                page.screenshot(
                    path=str(evidence / "replace-failure.png"), full_page=True
                )
                raise AssertionError(
                    {
                        "message": page.locator("#message").text_content(),
                        "errors": errors,
                    }
                ) from None
            page.locator("#dialog-yes").click()
            expect(page.locator("#batch-progress")).to_contain_text("未処理が 1 件")
            page.locator("#batch-resume").click()
            expect(page.locator("#batch-progress")).to_contain_text(
                "読み込みが終わりました", timeout=45000
            )
            expect(page.locator("#batch-counts")).to_contain_text("エラー 0")
            page.locator("#batch-result-rows tr").nth(7).get_by_role(
                "button", name="一覧から除く", exact=True
            ).click()
            page.locator("#dialog-no").click()
            expect(page.locator("#batch-total")).to_have_text("8 件")
            checks.append(
                "Replace an error image and continue; cancelled removal preserves the row"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(evidence / "mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})

            stop_batch()
            new_batch([str(pdf)])
            page.locator("#batch-solutions").set_input_files(str(pdf))
            page.get_by_label("1件目の解答画像", exact=True).select_option("0")
            page.get_by_label("1件目の解答ページ", exact=True).fill("2")
            page.locator("#batch-run-new").click()
            expect(page.locator("#batch-list")).to_be_visible()
            expect(page.locator("#batch-progress")).to_contain_text(
                "読み込みが終わりました", timeout=45000
            )
            expect(page.locator("#batch-result-rows")).to_contain_text("p.2")
            checks.append("Explicit PDF problem/solution pages are preserved")
            page.locator("#batch-result-rows tr").first.get_by_role(
                "button", name="一覧から除く", exact=True
            ).click()
            page.locator("#dialog-yes").click()
            expect(page.locator("#batch-total")).to_have_text("0 件")
            page.locator("#reset").click()
            expect(page.locator("#welcome")).to_be_visible()
            expect(page.locator("#batch-list")).to_be_hidden()
            checks.append("Removing the final row returns cleanly to the top page")
            new_batch(paths)
            page.route("**/api/batch-item", lambda route: route.abort(), times=1)
            page.locator("#batch-run-new").click()
            expect(page.locator("#batch-list")).to_be_visible()
            expect(page.locator("#batch-progress")).to_contain_text(
                "読み込みが終わりました", timeout=180000
            )
            expect(page.locator("#batch-counts")).to_contain_text("確認待ち 99")
            expect(page.locator("#batch-counts")).to_contain_text("エラー 1")
            page.locator("#batch-retry").click()
            expect(page.locator("#batch-counts")).to_contain_text(
                "確認待ち 100", timeout=180000
            )
            expect(page.locator("#batch-counts")).to_contain_text("エラー 0")
            expect(page.locator("#batch-counts")).to_contain_text("条件付き PASS 0")
            page.locator("#batch-result-rows tr").first.get_by_role(
                "button", name="確認する", exact=True
            ).click()
            expect(page.locator("#workbench")).to_be_visible()
            page.locator("#batch-back").click()
            page.screenshot(path=str(evidence / "hundred.png"))
            checks.append(
                "100 real image imports, including retry after a connection failure, finish without unapproved PASS or losing the first workspace"
            )
            assert not errors, errors
            assert all(u.startswith(url.split("/#")[0]) for u in requests), requests
            checks.append(
                "No JavaScript errors or external requests; 390px layout stays within viewport"
            )
            browser.close()
        result = {
            "checks": checks,
            "count": len(checks),
            "seconds": round(time.monotonic() - started, 2),
            "desktopUsed": False,
        }
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    main()
