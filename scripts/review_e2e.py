"""Actual-browser regressions for approval, slow saves, and accepted cancels."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

from playwright.async_api import (
    async_playwright,
    expect,
    TimeoutError as BrowserTimeout,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.samples import demo_model, render  # noqa: E402
from mazeproof.server import LocalServer  # noqa: E402
from mazeproof.workspace import inspect_sources  # noqa: E402


async def main(browser_path):
    evidence = ROOT / ".evidence" / "review-regressions"
    evidence.mkdir(parents=True, exist_ok=True)
    problem = evidence / "problem.png"
    render(demo_model()).save(problem)
    server = LocalServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks, errors = [], []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True, executable_path=browser_path
            )
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(server.origin + "/#" + server.token)

            async def upload():
                await page.locator("#problem-file").set_input_files(str(problem))
                await page.locator("#import-submit").click()
                await expect(page.locator("#workbench")).to_be_visible(timeout=45000)
                await expect(page.locator("#busy")).to_be_hidden()
                details = page.locator("details").filter(
                    has=page.locator("#edge-field")
                )
                if not await details.evaluate("(e) => e.open"):
                    await page.get_by_text("座標で境界を編集", exact=True).click()
                await page.locator("#edge-field").select_option("verticalWalls")
                await page.locator("#edge-row").fill("0")
                await page.locator("#edge-col").fill("1")

            async def reset():
                async with page.expect_response("**/api/close") as response:
                    await page.locator("#reset").click()
                    await page.locator("#dialog-yes").click()
                assert (await response.value).status == 200
                await expect(page.locator("#welcome")).to_be_visible()

            async def warning():
                return await page.evaluate("""() => {
                  const e = new Event("beforeunload", {cancelable: true});
                  window.dispatchEvent(e); return e.defaultPrevented;
                }""")

            await upload()
            for selector, filename in (
                ("evaluate", None),
                ("save-project", "undo.mazeproof"),
                ("save-report", "undo-report.json"),
                ("save-html", "undo-report.html"),
            ):
                await page.locator("#confirm-review").check()
                await page.locator("#approve").click()
                await expect(page.locator("#result-status")).to_have_text(
                    "条件付き PASS"
                )
                await page.locator("#edge-toggle").click()
                await page.locator("#undo").click()
                await expect(page.locator("#confirm-review")).not_to_be_checked()
                if filename:
                    async with page.expect_download() as download:
                        await page.locator("#" + selector).click()
                    await (await download.value).save_as(str(evidence / filename))
                    text = (evidence / filename).read_text()
                    if selector == "save-html":
                        assert "recognized_unconfirmed" in text
                        assert "human_confirmed" not in text
                    else:
                        result = json.loads(text)
                        if selector == "save-project":
                            result = result["result"]
                        assert result["overallStatus"] == "NEEDS_REVIEW"
                else:
                    await page.locator("#evaluate").click()
                await expect(page.locator("#result-status")).to_have_text("確認待ち")
                checks.append(
                    f"Unsynced edit/undo remains unconfirmed through {selector}"
                )

            # Hold a genuine export response; all edit/navigation controls stay locked.
            started, release = asyncio.Event(), asyncio.Event()

            async def slow_export(route):
                response = await route.fetch()
                started.set()
                await release.wait()
                await route.fulfill(response=response)

            await page.route("**/api/export", slow_export, times=1)
            async with page.expect_download() as download:
                await page.locator("#save-project").click()
                await asyncio.wait_for(started.wait(), 10)
                assert await page.locator("#workbench").evaluate("(e) => e.inert")
                await expect(page.locator("#reset")).to_be_disabled()
                for selector in ("edge-toggle", "undo"):
                    try:
                        await page.locator("#" + selector).click(timeout=200)
                    except BrowserTimeout:
                        pass
                    else:
                        raise AssertionError(
                            f"{selector} remained interactive during save"
                        )
                release.set()
            await (await download.value).save_as(str(evidence / "slow-save.mazeproof"))
            saved = json.loads((evidence / "slow-save.mazeproof").read_text())
            assert saved["edits"]["problem"]["model"]["verticalWalls"][0][1] is False
            await expect(page.locator("#busy")).to_be_hidden()
            assert not await warning()
            await page.locator("#edge-toggle").click()
            assert await warning()
            dialogs = []

            async def accept_dialog(dialog):
                dialogs.append(dialog.type)
                await dialog.accept()

            page.on("dialog", accept_dialog)
            await page.reload()
            await expect(page.locator("#welcome")).to_be_visible()
            assert dialogs == ["beforeunload"], dialogs
            checks.append(
                "Slow save locks edits/reset; subsequent edit warns on actual reload"
            )

            await upload()

            async def fail_export(route):
                await route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({"error": "TEST_EXPORT_FAILURE"}),
                )

            await page.route("**/api/export", fail_export, times=1)
            await page.locator("#save-project").click()
            await expect(page.locator("#message")).to_contain_text(
                "TEST_EXPORT_FAILURE"
            )
            await expect(page.locator("#busy")).to_be_hidden()
            assert await warning()
            await page.locator("#edge-toggle").click()
            async with page.expect_download() as download:
                await page.locator("#save-project").click()
            await (await download.value).save_as(str(evidence / "save-retry.mazeproof"))
            saved = json.loads((evidence / "save-retry.mazeproof").read_text())
            assert saved["edits"]["problem"]["model"]["verticalWalls"][0][1] is True
            checks.append(
                "Export failure retains unsaved edits and permits a correct retry"
            )
            await reset()

            baseline = set(server.workspaces)
            entered, finish = threading.Event(), threading.Event()

            def gated(sources):
                entered.set()
                if not finish.wait(10):
                    raise AssertionError("Missing worker release")
                return inspect_sources(sources)

            with patch("mazeproof.workspace.inspect_sources", side_effect=gated):
                await page.locator("#problem-file").set_input_files(str(problem))
                await page.locator("#import-submit").click()
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    async with page.expect_response("**/api/import-cancel") as response:
                        await page.locator("#cancel").click()
                    assert (await response.value).status == 200
                finally:
                    finish.set()
                assert await asyncio.to_thread(server.operation_lock.acquire, True, 35)
                server.operation_lock.release()
            await expect(page.locator("#welcome")).to_be_visible()
            assert set(server.workspaces) == baseline
            assert not any(r["state"] == "pending" for r in server.imports.values())
            await upload()
            checks.append(
                "Cancel after server acceptance reclaims result; next import works"
            )
            await reset()

            baseline = set(server.workspaces)
            # The server has already produced a result, but the browser has not read it.
            ready, deliver = asyncio.Event(), asyncio.Event()

            async def late_import(route):
                response = await route.fetch()
                ready.set()
                await deliver.wait()
                try:
                    await route.fulfill(response=response)
                except Exception:
                    pass  # The browser cancelled this request.

            await page.route("**/api/import", late_import, times=1)
            await page.locator("#problem-file").set_input_files(str(problem))
            await page.locator("#import-submit").click()
            await asyncio.wait_for(ready.wait(), 10)
            async with page.expect_response("**/api/import-cancel"):
                await page.locator("#cancel").click()
            deliver.set()
            await expect(page.locator("#welcome")).to_be_visible()
            assert set(server.workspaces) == baseline
            assert not any(r["state"] == "pending" for r in server.imports.values())
            await upload()
            checks.append(
                "Cancel after result creation discards late result and frees quota"
            )
            await reset()

            baseline = set(server.workspaces)

            async def lost_claim(route):
                await route.fetch()  # Claim committed; acknowledgement is lost.
                await route.abort()

            await page.route("**/api/import-claim", lost_claim, times=1)
            await page.locator("#problem-file").set_input_files(str(problem))
            async with page.expect_response("**/api/import-cancel"):
                await page.locator("#import-submit").click()
            await expect(page.locator("#busy")).to_be_hidden()
            assert set(server.workspaces) == baseline
            await upload()
            checks.append(
                "Lost claim acknowledgement releases owned result and permits retry"
            )
            assert not errors, errors
            (evidence / "result.json").write_text(
                json.dumps({"checks": checks, "pageErrors": errors}, indent=2)
            )
            print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))
            await context.close()
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser")
    asyncio.run(main(parser.parse_args().browser))
