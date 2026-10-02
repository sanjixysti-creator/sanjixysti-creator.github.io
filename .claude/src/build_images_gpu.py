#!/usr/bin/env python3
"""Make og.png (1200x630 link preview) and apple-touch-icon.png (180x180) for the standalone Used GPU Check site.

The result card in the preview is a real screenshot of the built checker, so the numbers on it are the app's own.
Run build_gpu.py first.
"""
import base64
import functools
import http.server
import json
import os
import pathlib
import threading

from playwright.sync_api import sync_playwright

from build_gpu import APP_FONTS, INDIGO, OUT, mark_shapes
from build_site import font_faces

HERE = pathlib.Path(__file__).resolve().parent
SITE_ROOT = OUT.parent  # .../site
STORE = 'gpu-check-v1'

# A sample listing that shows off the read: a local seller, a payment app and a price far below typical.
SAMPLE = {'v': 1, 'card': 'RX 9070 XT', 'ask': 380, 'typ': 640,
          'a': {'platform': 'local', 'pay': 'app', 'feedback': 'few'}, 'extras': [], 'seq': 0, 'sort': 'new', 'saved': []}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


CARD_FONTS = [f for f in APP_FONTS if f[1] in ('chakra-petch', 'public-sans')]
MARK_LIGHT = f'<svg viewBox="0 0 40 40" aria-hidden="true">{mark_shapes("#fff", INDIGO, INDIGO)}</svg>'


def card_html(panel_b64):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_faces(CARD_FONTS)}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{position:relative;background:{INDIGO};color:#fff;font-family:'Public Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.bg{{position:absolute;inset:0;background:
  radial-gradient(780px 520px at 80% 50%, rgba(255,255,255,.17), rgba(255,255,255,0) 68%),
  linear-gradient(135deg,#5148E8 0%,#4338CA 46%,#291F8C 100%)}}
.left{{position:absolute;left:72px;top:0;bottom:0;width:590px;display:flex;flex-direction:column;justify-content:center;gap:30px}}
.brand{{display:flex;align-items:center;gap:22px}}
.brand svg{{width:96px;height:96px;flex:none}}
.brand h1{{font:700 84px/0.98 'Chakra Petch','Arial Narrow',Arial,sans-serif;letter-spacing:.03em;text-transform:uppercase;white-space:nowrap}}
.tag{{font:600 35px/1.25 'Public Sans',system-ui,sans-serif;max-width:520px;text-wrap:balance;color:rgba(255,255,255,.95)}}
.pill{{align-self:flex-start;background:#fff;color:#2B2394;font:700 21px/1 'Public Sans',system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase;padding:15px 26px;border-radius:999px}}
.panel{{position:absolute;right:50px;top:50%;height:560px;transform:translateY(-50%) rotate(2deg);filter:drop-shadow(0 22px 30px rgba(10,6,60,.55))}}
</style></head><body>
<div class="bg"></div>
<div class="left">
  <div class="brand">{MARK_LIGHT}<h1>Used GPU<br>Check</h1></div>
  <p class="tag">Check a used graphics card listing before you pay.</p>
  <span class="pill">Free risk and price check</span>
</div>
<img class="panel" alt="" src="data:image/png;base64,{panel_b64}">
</body></html>"""


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}}
html,body{{width:180px;height:180px;overflow:hidden}}
body{{background:linear-gradient(135deg,#5148E8,#4338CA 50%,#2F2599);display:grid;place-items:center}}
svg{{width:150px;height:150px}}
</style></head><body>{MARK_LIGHT}</body></html>"""


def main():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SITE_ROOT)))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = launch(p)

        # 1. Real result card from the built page, transparent around the rounded corners, sample listing only.
        ctx = browser.new_context(viewport={'width': 1200, 'height': 1000}, device_scale_factor=2, color_scheme='light')
        ctx.add_init_script("try { localStorage.setItem('%s', %s); } catch (e) {}" % (STORE, json.dumps(json.dumps(SAMPLE))))
        pg = ctx.new_page()
        pg.goto(f'http://127.0.0.1:{port}/gpu-check/')
        pg.wait_for_timeout(500)
        pg.evaluate('document.fonts.ready')
        pg.add_style_tag(content='html,body{background:transparent!important}'
                                 '#riskCard .btn-row,#riskCard .safety-line,#riskCard #saveForm,#riskCard #riskAlert,#riskCard #reasonsMore,#toast{display:none!important}')
        pg.evaluate("window.scrollTo(0, 0)")
        pg.wait_for_timeout(250)
        box = pg.locator('#riskCard').bounding_box()
        panel_png = pg.screenshot(clip={'x': box['x'], 'y': box['y'], 'width': box['width'], 'height': box['height']},
                                  omit_background=True)
        (HERE / 'panel-og-gpu.png').write_bytes(panel_png)
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
    print('card panel', box['width'], 'x', box['height'])


if __name__ == '__main__':
    main()
