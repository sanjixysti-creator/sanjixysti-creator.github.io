#!/usr/bin/env python3
"""Make og.png (1200x630 link preview) and apple-touch-icon.png (180x180) for the standalone Drive Rate site.

The verdict panel in the preview is a real screenshot of the built calculator in its first-visit state, so the numbers on it
are the app's own. Run build_drive.py first.
"""
import base64
import functools
import http.server
import os
import pathlib
import threading

from playwright.sync_api import sync_playwright

from build_drive import MARK_ON_RED, OUT
from build_site import APP_FONTS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SITE_ROOT = OUT.parent  # .../site


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


CARD_FONTS = [f for f in APP_FONTS if f[1] in ('big-shoulders-display', 'public-sans')]

MARK_LIGHT = f'<svg viewBox="0 0 40 40" aria-hidden="true">{MARK_ON_RED}</svg>'

# The panel is tall, so the preview keeps the verdict, both readings and the pay needed box, not the receipt or buttons.
HIDE = '#dash .btn-row, #dash #stub, #dash #offerAlert { display: none !important; }'


def card_html(panel_b64):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_faces(CARD_FONTS)}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{position:relative;background:#BE123C;color:#fff;font-family:'Public Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.bg{{position:absolute;inset:0;background:
  radial-gradient(760px 520px at 80% 52%, rgba(255,255,255,.16), rgba(255,255,255,0) 68%),
  linear-gradient(135deg,#D3174A 0%,#BE123C 46%,#7F0E2D 100%)}}
.left{{position:absolute;left:72px;top:0;bottom:0;width:560px;display:flex;flex-direction:column;justify-content:center;gap:30px}}
.brand{{display:flex;align-items:center;gap:20px}}
.brand svg{{width:92px;height:92px;flex:none}}
.brand h1{{font:800 100px/1 'Big Shoulders Display','Arial Narrow',Arial,sans-serif;letter-spacing:.02em;text-transform:uppercase;white-space:nowrap}}
.tag{{font:600 36px/1.25 'Public Sans',system-ui,sans-serif;max-width:520px;text-wrap:balance;color:rgba(255,255,255,.96)}}
.pill{{align-self:flex-start;background:#fff;color:#7F0E2D;font:700 21px/1 'Public Sans',system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase;padding:15px 26px;border-radius:999px}}
.panel{{position:absolute;right:60px;top:50%;width:440px;transform:translateY(-50%) rotate(2.2deg);filter:drop-shadow(0 22px 30px rgba(40,0,12,.55))}}
</style></head><body>
<div class="bg"></div>
<div class="left">
  <div class="brand">{MARK_LIGHT}<h1>Drive Rate</h1></div>
  <p class="tag">Is this offer worth it? See the real pay per hour.</p>
  <span class="pill">Free offer checker</span>
</div>
<img class="panel" alt="" src="data:image/png;base64,{panel_b64}">
</body></html>"""


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}}
html,body{{width:180px;height:180px;overflow:hidden}}
body{{background:linear-gradient(135deg,#D3174A,#BE123C 50%,#8F1030);display:grid;place-items:center}}
svg{{width:148px;height:148px}}
</style></head><body>{MARK_LIGHT}</body></html>"""


def main():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SITE_ROOT)))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = launch(p)

        # 1. Real verdict panel from the built page, transparent around the rounded corners, first-visit numbers only.
        ctx = browser.new_context(viewport={'width': 1200, 'height': 900}, device_scale_factor=2, color_scheme='light')
        pg = ctx.new_page()
        pg.goto(f'http://127.0.0.1:{port}/drive-rate/')
        pg.wait_for_timeout(400)
        pg.evaluate('document.fonts.ready')
        pg.add_style_tag(content='html,body{background:transparent!important}' + HIDE)
        pg.wait_for_timeout(200)
        box = pg.locator('#dash').bounding_box()
        panel_png = pg.screenshot(clip={'x': box['x'], 'y': box['y'], 'width': box['width'], 'height': box['height']},
                                  omit_background=True)
        (HERE / 'panel-og-drive.png').write_bytes(panel_png)
        ctx.close()

        # 2. Link preview card.
        ctx = browser.new_context(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(card_html(base64.b64encode(panel_png).decode('ascii')), wait_until='load')
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / 'og.png'), clip={'x': 0, 'y': 0, 'width': 1200, 'height': 630})
        ctx.close()

        # 3. Home screen icon.
        ctx = browser.new_context(viewport={'width': 180, 'height': 180}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(icon_html(), wait_until='load')
        pg.screenshot(path=str(OUT / 'apple-touch-icon.png'), clip={'x': 0, 'y': 0, 'width': 180, 'height': 180})
        ctx.close()
        browser.close()
    httpd.shutdown()
    for name in ('og.png', 'apple-touch-icon.png'):
        print(name, os.path.getsize(OUT / name), 'bytes')


if __name__ == '__main__':
    main()
