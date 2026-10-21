"""Exercise the static demo at a project subpath or at the public Pages URL."""

import argparse
import functools
import hashlib
import http.server
import json
from pathlib import Path
import shutil
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def capture(page, path):
    # Full-page captures otherwise place sticky UI at the current scroll offset.
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(path), full_page=True)


def exercise(url, output):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        errors = []
        requests = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method, request.url)))
        response = page.goto(url, wait_until='networkidle')
        assert response.ok, response.status
        expect(page.locator('body')).to_have_attribute('data-ready', 'true')
        expect(page.locator('.demo-banner')).to_be_visible()
        assert page.locator('input[type=file]').count() == 0
        assert page.locator('form').count() == 0
        expect(page.locator('#result')).to_be_hidden()
        initial = page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()')
        page.locator('#overlay').uncheck()
        assert page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()') != initial
        page.locator('#overlay').check()
        assert page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()') == initial
        page.locator('#zoom').click()
        expect(page.locator('#zoom')).to_have_attribute('aria-pressed', 'true')
        assert page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()') != initial
        page.locator('#zoom').click()
        page.locator('#advance').click()
        expect(page.locator('#result-title')).to_contain_text('通り道は1通り')
        assert page.locator('.checks .failed').count() == 0
        page.locator('#report-button').click()
        expect(page.locator('#report')).to_be_visible()
        page.locator('#report-button').click()
        expect(page.locator('#report')).to_be_hidden()
        page.locator('#reset').click()
        expect(page.locator('#result')).to_be_hidden()
        capture(page, output / 'desktop.png')

        for case, failures in [('wall', 3), ('gap', 1)]:
            page.locator(f'[data-case={case}]').click()
            before = page.locator('#original').evaluate('(canvas) => canvas.toDataURL()')
            before_overlay = page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()')
            page.locator('#problem').click()
            expect(page.locator('#problem')).to_have_attribute('aria-pressed', 'true')
            assert page.locator('#original').evaluate('(canvas) => canvas.toDataURL()') != before
            page.locator('#solution').click()
            page.locator('#advance').click()
            assert page.locator('.checks .failed').count() == failures
            expect(page.locator('#result')).to_be_visible()
            page.locator('#advance').click()
            assert page.locator('.checks .failed').count() == 0
            assert page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()') != before_overlay
            after = page.locator('#original').evaluate('(canvas) => canvas.toDataURL()')
            assert (before == after) == (case == 'wall')
            if case == 'gap':
                expect(page.locator('#source-label')).to_have_text('用意した修正後の画像')
            page.locator('#report-button').click()
            expect(page.locator('#report')).to_be_visible()
            capture(page, output / f'{case}-corrected.png')
            page.locator('#reset').click()
            expect(page.locator('#result')).to_be_hidden()
            expect(page.locator('#report')).to_be_hidden()
            assert page.locator('#original').evaluate('(canvas) => canvas.toDataURL()') == before
            assert page.locator('#recognized').evaluate('(canvas) => canvas.toDataURL()') == before_overlay

        # Repeated cycles and switching never carry a previous result into a new case.
        for _ in range(2):
            for case in ('normal', 'wall', 'gap'):
                page.locator(f'[data-case={case}]').click()
                expect(page.locator('#result')).to_be_hidden()
                page.locator('#advance').click()
                if case != 'normal':
                    page.locator('#advance').click()
                page.locator('#advance').click()
                expect(page.locator('#result')).to_be_hidden()
        page.reload(wait_until='networkidle')
        expect(page.locator('[data-case=normal]')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#result')).to_be_hidden()

        # Keyboard, persistent demo notice, and mobile layout/interaction.
        page.locator('[data-case=wall]').focus()
        page.keyboard.press('Enter')
        expect(page.locator('[data-case=wall]')).to_have_attribute('aria-pressed', 'true')
        page.set_viewport_size({'width': 375, 'height': 812})
        page.locator('#zoom').click()
        page.locator('#advance').click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#result').scroll_into_view_if_needed()
        assert page.locator('.demo-banner').bounding_box()['y'] == 0
        capture(page, output / 'mobile.png')
        page.locator('#advance').click()
        assert page.locator('.checks .failed').count() == 0
        for width in (320, 768, 1024):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        links = page.locator('a[href^="https://"]').evaluate_all('(links) => [...new Set(links.map(a => a.href))]')
        expected = {
            'https://github.com/yo4e/MazeProof',
            'https://github.com/yo4e/MazeProof/releases/tag/v0.2.1',
            'https://github.com/yo4e/MazeProof/blob/v0.2.1/docs/LOCAL_MCP.md',
        }
        assert set(links) == expected
        expect(page.locator('.next-actions a.primary')).to_have_attribute(
            'href', 'https://github.com/yo4e/MazeProof/releases/tag/v0.2.1'
        )
        if url.startswith('https:'):
            for link in links:
                assert page.request.get(link).ok, link
        assert not errors, errors
        assert all(method == 'GET' for method, _ in requests)
        assert not any('/api/' in target or '127.0.0.1' in target and url.startswith('https:') for _, target in requests)

        # A failed image must produce an explanation, not apparently valid results.
        failure = browser.new_page()
        failure.route('**/assets/gap.png', lambda route: route.abort())
        failure.goto(url)
        expect(failure.locator('[role=alert]')).to_contain_text('読み込めませんでした')
        expect(failure.locator('#advance')).to_be_disabled()
        expect(failure.locator('#result')).to_be_hidden()
        failure.unroute('**/assets/gap.png')
        failure.reload(wait_until='networkidle')
        expect(failure.locator('body')).to_have_attribute('data-ready', 'true')
        expect(failure.locator('#advance')).to_be_enabled()
        browser.close()
    (output / 'result.json').write_text(json.dumps({'url': url, 'success': True, 'cases': 3, 'widths': [320, 375, 768, 1024, 1440], 'links': links, 'consoleErrors': errors, 'noUploadsOrApiRequests': True, 'resetReloadAndFailureRecovery': True}, ensure_ascii=False, indent=2) + '\n')
    print('Static demo: three cases, correction/reset, keyboard, mobile, links, read-only requests and failure recovery passed.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    parser.add_argument('--output', type=Path, default=ROOT / '.evidence/demo')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.url:
        exercise(args.url, args.output)
        return
    with tempfile.TemporaryDirectory() as temp:
        site = Path(temp) / 'MazeProof'
        shutil.copytree(ROOT / '_site', site)
        fingerprint = {str(p.relative_to(site)): hashlib.sha256(p.read_bytes()).hexdigest() for p in site.rglob('*') if p.is_file()}
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=temp)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            exercise(f'http://127.0.0.1:{server.server_port}/MazeProof/', args.output)
            assert fingerprint == {str(p.relative_to(site)): hashlib.sha256(p.read_bytes()).hexdigest() for p in site.rglob('*') if p.is_file()}
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
