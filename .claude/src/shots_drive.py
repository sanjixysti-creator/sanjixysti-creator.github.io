#!/usr/bin/env python3
"""Takes the review screenshots of the built Drive Rate page into review/. Run build_drive.py first."""
import functools, http.server, os, pathlib, threading
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / 'review'
OUT.mkdir(exist_ok=True)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def fill(pg, **vals):
    for k, v in vals.items():
        pg.fill('#' + k, str(v))


def scroll_to(pg, sel, pad=16):
    pg.evaluate("(a) => { document.documentElement.style.scrollBehavior = 'auto'; const r = document.querySelector(a[0]).getBoundingClientRect(); window.scrollTo(0, scrollY + r.top - a[1]); }", [sel, pad])
    pg.wait_for_timeout(200)


TYPICAL = dict(pay=14, miles=5, minutes=20)          # take it
EXTREME = dict(pay=1, miles=100000, minutes=100000)  # a huge loss
# name, scheme, width, height, steps
SHOTS = [
    ('first-visit-390-light', 'light', 390, 844, []),
    ('first-visit-390-dark', 'dark', 390, 844, []),
    ('first-visit-320-light', 'light', 320, 640, []),
    ('empty-390-light', 'light', 390, 844, [('click', '#exampleClear')]),
    ('typical-390-light', 'light', 390, 844, [('fill', TYPICAL), ('scroll', '#dash')]),
    ('typical-390-dark', 'dark', 390, 844, [('fill', TYPICAL), ('scroll', '#dash')]),
    ('typical-320-light', 'light', 320, 700, [('fill', TYPICAL), ('scroll', '#dash')]),
    ('borderline-390-light', 'light', 390, 844, [('fill', dict(pay=10, miles=4, minutes=20)), ('scroll', '#dash')]),
    ('extreme-320-light', 'light', 320, 700, [('fill', EXTREME), ('scroll', '#dash')]),
    ('extreme-390-dark', 'dark', 390, 844, [('fill', EXTREME), ('scroll', '#dash')]),
    ('desktop-1280-light', 'light', 1280, 900, [('fill', TYPICAL)]),
    ('desktop-1280-dark', 'dark', 1280, 900, [('fill', TYPICAL)]),
    ('desktop-1280-light-full', 'light', 1280, 900, [('fill', TYPICAL), ('full', None)]),
    ('phone-390-light-full', 'light', 390, 844, [('fill', TYPICAL), ('open', None), ('full', None)]),
    ('phone-390-dark-full', 'dark', 390, 844, [('fill', TYPICAL), ('open', None), ('full', None)]),
    ('phone-320-light-full', 'light', 320, 700, [('fill', TYPICAL), ('open', None), ('full', None)]),
]


def main():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE / 'site')))
    url = 'http://127.0.0.1:%d/drive-rate/' % httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    errs = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
        for name, scheme, w, h, steps in SHOTS:
            ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1, timezone_id='America/Los_Angeles', locale='en-US')
            pg = ctx.new_page()
            pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto(url)
            pg.wait_for_timeout(400)
            pg.evaluate('document.fonts.ready')
            full = False
            for kind, arg in steps:
                if kind == 'click':
                    pg.click(arg)
                elif kind == 'fill':
                    fill(pg, **arg)
                elif kind == 'open':
                    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
                elif kind == 'scroll':
                    scroll_to(pg, arg)
                elif kind == 'full':
                    full = True
                    pg.add_style_tag(content='#bar{display:none!important}')
            pg.wait_for_timeout(250)
            pg.screenshot(path=str(OUT / (name + '.png')), full_page=full)
            ctx.close()
        browser.close()
    httpd.shutdown()
    print('shots:', len(SHOTS), 'errors:', errs[:4])


if __name__ == '__main__':
    main()
