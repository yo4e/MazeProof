"""Real browser file round trips, strict imports, and failed-save recovery.

Run in an environment that permits an isolated HTTP server and headless browser.
All input images are generated fixtures; no user files or existing server used.
"""
import asyncio
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mazeproof.samples import demo_model, render  # noqa: E402
from mazeproof.server import LocalServer  # noqa: E402
from mazeproof.workspace import MAX_PROJECT_BYTES  # noqa: E402
from playwright.async_api import async_playwright, expect  # noqa: E402


def large_pair(folder):
    n = 250
    model = {
        "schemaVersion": "mazeproof.maze/1", "width": n, "height": n,
        "horizontalWalls": [[True] * n for _ in range(n + 1)],
        "verticalWalls": [[True] * (n + 1) for _ in range(n)],
        "entrance": {"row": 0, "col": 0, "side": "N"},
        "exit": {"row": n - 1, "col": 0, "side": "S"},
    }
    route = []
    for r in range(n):
        route.extend({"row": r, "col": c} for c in (range(n) if r % 2 == 0 else range(n - 1, -1, -1)))
        for c in range(1, n):
            model["verticalWalls"][r][c] = False
        if r + 1 < n:
            model["horizontalWalls"][r + 1][n - 1 if r % 2 == 0 else 0] = False
    model["horizontalWalls"][0][0] = model["horizontalWalls"][n][0] = False
    paths = []
    for role in ("problem", "solution"):
        path = folder / (role + "-large.png")
        image = render(model, route if role == "solution" else None, cell=10, margin=8, thickness=3)
        image.save(path, compress_level=0)
        image.close()
        assert path.stat().st_size < 25 * 1024**2
        paths.append(path)
    return paths


async def main():
    folder = ROOT / ".evidence" / "file-contracts"
    folder.mkdir(parents=True, exist_ok=True)
    problem = folder / "problem.png"
    render(demo_model()).save(problem)
    server = LocalServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks, errors, sizes = [], [], {}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()
            page.set_default_timeout(180000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(server.origin + "/#" + server.token)

            async def file(selector, text, name="fixture.json"):
                await page.locator("#message").evaluate("e=>{e.textContent='';e.hidden=true;}")
                await page.locator(selector).set_input_files({"name": name, "mimeType": "application/json", "buffer": text.encode()})

            async def warning():
                return await page.evaluate("""() => {const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}""")

            async def save(path):
                async with page.expect_download() as downloading:
                    await page.locator("#save-project").click()
                await (await downloading.value).save_as(str(path))

            raw = json.dumps(demo_model())
            duplicate = raw.replace('"width": 4', '"width":99,"\\u0077idth":4')
            await page.locator("#problem-file").set_input_files(str(problem))
            await file("#reference-file", duplicate)
            await page.locator("#import-submit").click()
            await expect(page.locator("#message")).to_contain_text("重複")
            await expect(page.locator("#welcome")).to_be_visible()
            assert not server.workspaces
            await file("#reference-file", raw)
            await page.locator("#import-submit").click()
            await expect(page.locator("#workbench")).to_be_visible()
            await expect(page.locator("#busy")).to_be_hidden()
            checks.append("Duplicate escaped reference rejected before import; valid reference recovers")

            # A genuine saved file and an unsaved edit; invalid imports must not
            # revoke/replace either the server workspace or the browser edits.
            small = folder / "small.mazeproof"
            await save(small)
            await page.get_by_text("座標で境界を編集", exact=True).click()
            await page.locator("#edge-field").select_option("verticalWalls")
            await page.locator("#edge-row").fill("0")
            await page.locator("#edge-col").fill("1")
            await page.locator("#edge-toggle").click()
            assert await warning()
            before = set(server.workspaces)
            canvas = await page.locator("#canvas").evaluate("e=>e.toDataURL()")
            duplicate_project = small.read_text().replace('"uniqueRequired":true', '"uniqueRequired":false,"\\u0075niqueRequired":true')
            assert duplicate_project != small.read_text()
            for selector, text in (
                ("#project-file", duplicate_project),
                ("#batch-project-file", '{"schemaVersion":"mazeproof.batch/1","items":[],"items":[]}'),
            ):
                await file(selector, text)
                await expect(page.locator("#message")).to_contain_text("重複")
                await expect(page.locator("#workbench")).to_be_visible()
                assert set(server.workspaces) == before
                assert await warning()
                assert await page.locator("#canvas").evaluate("e=>e.toDataURL()") == canvas
            checks.append("Duplicate single/batch files leave current unsaved edits intact")
            await page.screenshot(path=str(folder / "duplicate-preserved.png"), full_page=True)

            downloads = []
            page.on("download", lambda d: downloads.append(d.suggested_filename))
            with patch("mazeproof.workspace.MAX_PROJECT_BYTES", 1):
                await page.locator("#save-project").click()
                await expect(page.locator("#message")).to_contain_text("保存できません")
                await expect(page.locator("#busy")).to_be_hidden()
                assert not downloads
                assert await warning()
            await save(folder / "recovered.mazeproof")
            assert not await warning()
            checks.append("Oversized save emits no download and keeps unsaved warning; retry succeeds")

            # Existing indented v1 files still open, with fresh review required.
            await file("#project-file", json.dumps(json.loads(small.read_text()), indent=2), "legacy.mazeproof")
            await expect(page.locator("#message")).to_contain_text("復元しました")
            await expect(page.locator("#result-status")).to_have_text("確認待ち")
            assert all(not w.snapshot()["approved"] for w in server.workspaces.values())
            checks.append("Legacy indented v1 project restores without inheriting approval")
            await page.locator("#reset").click()
            await page.locator("#dialog-yes").click()
            await expect(page.locator("#welcome")).to_be_visible()

            # 250x250, long red route, many uncertain boundaries, ~18MiB each.
            # No decoder mocks or result injection. This failed at 72MiB before.
            large_problem, large_solution = large_pair(folder)
            await page.locator("#problem-file").set_input_files(str(large_problem))
            await page.locator("#solution-file").set_input_files(str(large_solution))
            await page.locator("#reference-file").set_input_files([])
            await page.locator("#import-submit").click()
            await expect(page.locator("#workbench")).to_be_visible(timeout=180000)
            await expect(page.locator("#busy")).to_be_hidden(timeout=180000)
            # This deliberately dense snake is outside reliable auto-grid
            # estimation. Set both grids using the supported user controls.
            for role in ("problem", "solution"):
                await page.locator("#tab-" + role).click()
                if not await page.locator("#grid-details").evaluate("e=>e.open"):
                    await page.locator("#grid-details summary").click()
                for key, value in {"cols": 250, "rows": 250, "x0": 8, "y0": 8, "x1": 2508, "y1": 2508}.items():
                    await page.locator("#" + key).fill(str(value))
                async with page.expect_response("**/api/import-claim", timeout=180000) as claimed:
                    await page.locator("#reanalyze").click()
                    await page.locator("#dialog-yes").click()
                assert (await claimed.value).status == 200
                await expect(page.locator("#busy")).to_be_hidden(timeout=180000)
            await expect(page.locator("#cols")).to_have_value("250")
            await expect(page.locator("#rows")).to_have_value("250")
            large = folder / "large.mazeproof"
            await save(large)
            assert 72 * 1024**2 < large.stat().st_size <= MAX_PROJECT_BYTES
            old = next(iter(server.workspaces.values()))
            digest = old.digest()
            sizes = {"sourceBytes": [p.stat().st_size for p in (large_problem, large_solution)], "savedBytes": large.stat().st_size, "limit": MAX_PROJECT_BYTES, "routeLength": len(old.edits["solution"]["model"]["route"]), "unknowns": len(old.observations["solution"]["unknowns"])}
            assert sizes["routeLength"] == 62500 and sizes["unknowns"] > 60000
            await page.locator("#message").evaluate("e=>{e.textContent='';e.hidden=true;}")
            await page.locator("#project-file").set_input_files(str(large))
            await expect(page.locator("#message")).to_contain_text("復元しました", timeout=180000)
            await expect(page.locator("#busy")).to_be_hidden()
            await expect(page.locator("#result-status")).to_have_text("確認待ち")
            restored = [w for w in server.workspaces.values() if w is not old]
            assert len(restored) == 1
            assert restored[0].digest() == digest
            assert not restored[0].snapshot()["approved"]
            checks.append("Real large PNG pair -> save above 72MiB -> strict browser read -> HTTP restore; edits match, review required")
            await page.screenshot(path=str(folder / "large-restored.png"), full_page=True)
            assert not errors, errors
            await context.close()
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        (folder / "result.json").write_text(json.dumps({"checks": checks, "sizes": sizes, "pageErrors": errors}, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"checks": checks, "sizes": sizes, "pageErrors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
