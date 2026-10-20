"""Local application smoke test; headless browser never takes the user's screen."""

import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("url")
parser.add_argument("--browser")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=args.browser)
    page = browser.new_page(
        viewport={"width": 1440, "height": 1100}, device_scale_factor=1
    )
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(args.url)
    page.screenshot(path=str(root / ".evidence/welcome.png"), full_page=True)
    page.get_by_role("button", name="合成サンプルで試す").click()
    page.locator("#workbench").wait_for(state="visible", timeout=45000)
    page.locator("#busy").wait_for(state="hidden")
    page.screenshot(path=str(root / ".evidence/workbench.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    print(
        page.evaluate(
            'JSON.stringify({width:innerWidth,doc:document.documentElement.scrollWidth,items:[...document.querySelectorAll("body *")].map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(e=>e.right>innerWidth)})'
        )
    )
    print(
        json.dumps(
            {
                "title": page.title(),
                "text": page.locator("#result-status").inner_text(),
                "errors": errors,
            },
            ensure_ascii=False,
        )
    )
    browser.close()
